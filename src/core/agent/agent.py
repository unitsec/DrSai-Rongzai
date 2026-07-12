from typing import (
    AsyncGenerator, 
    List, 
    Sequence, 
    Dict, 
    Any, 
    Callable, 
    Awaitable, 
    Union, 
    Optional, 
    Tuple,
    Self,
    Mapping,
    )

import asyncio
from loguru import logger
import uuid
import json
import os
import base64
import ast
import shutil

from pydantic import BaseModel

from autogen_core import CancellationToken, FunctionCall
from autogen_core.tools import (
    BaseTool, 
    Workbench,
    StaticWorkbench,
    FunctionTool,
    ToolSchema)
from autogen_core.memory import Memory
from autogen_core.model_context import ChatCompletionContext
from autogen_core.models import (
    ChatCompletionClient,
    CreateResult,
    FunctionExecutionResultMessage,
    FunctionExecutionResult,
    LLMMessage,
    UserMessage,
    AssistantMessage,
    SystemMessage,
    RequestUsage
)


from autogen_agentchat.agents._assistant_agent import AssistantAgentConfig
from autogen_agentchat.base import Handoff as HandoffBase
from autogen_agentchat.base import Response, TaskResult
from autogen_agentchat.messages import (
    AgentEvent,
    ChatMessage,
    HandoffMessage,
    MemoryQueryEvent,
    StopMessage,
    ToolCallExecutionEvent,
    ToolCallRequestEvent,
    ToolCallSummaryMessage,
    UserInputRequestedEvent,
    StructuredMessageFactory
)
from drsai.modules.managers.messages import (
    BaseChatMessage,
    BaseAgentEvent,
    TaskEvent, 
    AgentLogEvent,
    ModelClientStreamingChunkEvent,
    ThoughtEvent,
    TextMessage,
    MultiModalMessage,
    FileInfo,
    FilesContent,
    FilesEvent,
    Image,
    )
from autogen_ext.tools.mcp import StdioServerParams, mcp_server_tools

from drsai import HepAIChatCompletionClient
from drsai.modules.managers.database import DatabaseManager
from drsai.modules.baseagent import DrSaiAgent
# from drsai.configs import CONST
from drsai.modules.managers.datamodel import (
    # UserInput,
    Thread,
)
from drsai.modules.managers.datamodel.types import Response as DBResponse

from ...configs.constants import tools_dir
from ...configs.prompt import intention_system_message

# tools
from .reply_function import (
    get_data_handle_info,
    verify_data_handle_info,
    cif_3D_visualization,

)

# database
from ..datasets.datamodel import ToolsStatus, ToolsRunStatus

# read lst
from src.utils.read_lst import prune_lst_keep_main

here = os.path.dirname(os.path.abspath(__file__))

class RongZaiAgent(DrSaiAgent):
    """通过多工具进行优化"""
    def __init__(
        self,
        name: str,
        model_client: ChatCompletionClient = None,
        tools: List[BaseTool[Any, Any] | Callable[..., Any] | Callable[..., Awaitable[Any]]] | None = None,
        workbench: Workbench | None = None,
        handoffs: List[HandoffBase | str] | None = None,
        model_context: ChatCompletionContext | None = None,
        description: str = "An agent that provides assistance with ability to use tools.",
        system_message: (
            str | None
        ) = "You are a helpful AI assistant. Solve tasks using your tools. Reply with TERMINATE when the task has been completed.",
        model_client_stream: bool = True,
        reflect_on_tool_use: bool | None = None,
        tool_call_summary_format: str = "{result}",
        output_content_type: type[BaseModel] | None = None,
        output_content_type_format: str | None = None,
        memory: Sequence[Memory] | None = None,
        metadata: Dict[str, str] | None = None,
        memory_function: Callable = None,
        # allow_reply_function: bool = False,
        reply_function: Callable = None,
        db_manager: DatabaseManager = None,
        **kwargs,
            ):
        
        super().__init__(
            name=name, 
            model_client=model_client,
            tools=tools,
            workbench=workbench,
            handoffs=handoffs,
            model_context=model_context,
            description=description,
            system_message=system_message,
            model_client_stream=model_client_stream,
            reflect_on_tool_use=reflect_on_tool_use,
            tool_call_summary_format=tool_call_summary_format,
            output_content_type=output_content_type,
            output_content_type_format=output_content_type_format,
            memory=memory,
            metadata=metadata,
            memory_function=memory_function,
            reply_function=reply_function,
            db_manager=db_manager,
            **kwargs,
            )

        # 工作目录
        self._data_dir = kwargs.get("data_dir", None)
        if self._data_dir is None:
            raise ValueError("需要提供RUN和CIF文件所在data目录.")
        
        # 其他初始化
        self._GSASII_Workbench = kwargs.get("GSASII_Workbench", None)
        self._PDF_Workbench = kwargs.get("PDF_Workbench", None)
        self._AIndex_Workbench = kwargs.get("AIndex_Workbench", None)
        self._NPD_Simulator_Workbench = kwargs.get("NPD_Simulator_Workbench", None)
        self._sleep_time = kwargs.get("sleep_time", 10)

        #保存最新的精修后cif文件和gpx文件路径，用于最后的导出
        self.cif_paths = []
        self.gpx_path = ""

    async def pause(self) -> None:
        """Pause the agent by setting the paused state."""
        logger.info(f"Pausing {self.name}...")

        self.is_paused = True
        # self._paused.set()

    async def resume(self) -> None:
        """Resume the agent by clearing the paused state."""
        self.is_paused = False
        # self._paused.clear()

    async def close(self) -> None:
        """Clean up resources used by the agent.

        This method:
          ...
        """
        logger.info(f"Closing {self.name}...")
        
        # Close the model client.
        await self._model_client.close()

        # TODO: 进一步开发save_state
        AgentState: Mapping[str, Any] = await self.save_state()
        # 保存状态到数据库
        response: Response = self._db_manager.get(
            Thread, 
            filters={"user_id": self._user_id,"thread_id": self._thread_id},
            return_json=False
            )
        if response.status and response.data:
            thread: Thread = response.data[0]
            thread.state = json.dumps(AgentState)
            response: DBResponse = self._db_manager.upsert(thread)
            if not response.status:
                raise RuntimeError(f"Failed to create thread: {response.message}")
    
    def upload_file(self, file_path: str, purpose: str = "user_data") -> str:
        """上传文件到图床接口
        Args:
            file_path (str): 文件路径
            purpose (str): 上传用途，默认为"user_data"

        Returns:
            str: 上传后的URL
        """
        from openai import OpenAI
        client = OpenAI(
            api_key=self._model_client._client.api_key,
            base_url="https://aiapi.ihep.ac.cn/apiv2"
        )

        file_obj = client.files.create(
                file=open(file_path, "rb"),
                purpose=purpose
            )
        return f"https://aiapi.ihep.ac.cn/apiv2/files/{file_obj.id}/preview"

    def copy_gpx_to_gsa_folder(self, gpx_path: str, gsa_path: str) -> str:
        """将 gpx 文件复制到 gsa 文件所在文件夹并重命名
        Args:
            gpx_path (str): gpx 文件的路径
            gsa_path (str): gsa 文件的路径

        Returns:
            str: 复制后的 gpx 文件路径
        """
        try:
            # 获取 gsa 文件的目录
            gsa_dir = os.path.dirname(gsa_path)
            # 获取 gsa 文件的名称（不包含扩展名）
            gsa_name = os.path.splitext(os.path.basename(gsa_path))[0]
            # 构建新的 gpx 文件路径
            new_gpx_path = os.path.join(gsa_dir, f"{gsa_name}.gpx")
            # 复制文件
            shutil.copy2(gpx_path, new_gpx_path)
            logger.info(f"已将 gpx 文件复制到: {new_gpx_path}")
            return new_gpx_path
        except Exception as e:
            logger.error(f"复制 gpx 文件失败: {e}")
            return gpx_path

    def copy_cif_files_to_gsa_folder(self, cif_paths_list: List[str], gsa_path: str) -> List[str]:
        """将精修后的 cif 文件复制到 gsa 文件所在文件夹
        Args:
            cif_paths_list (List[str]): 精修后的 cif 文件路径列表
            gsa_path (str): gsa 文件的路径

        Returns:
            List[str]: 复制后的 cif 文件路径列表
        """
        new_cif_paths = []
        try:
            # 获取 gsa 文件的目录
            gsa_dir = os.path.dirname(gsa_path)
            
            for cif_file in cif_paths_list:
                if not os.path.exists(cif_file):
                    logger.warning(f"CIF 文件不存在: {cif_file}")
                    new_cif_paths.append(cif_file)
                    continue
                
                # 获取 cif 文件的原始文件名
                cif_filename = os.path.basename(cif_file)
                # 构建新的 cif 文件路径
                new_cif_path = os.path.join(gsa_dir, cif_filename)
                
                # 复制文件
                shutil.copy2(cif_file, new_cif_path)
                logger.info(f"已将 CIF 文件复制到: {new_cif_path}")
                new_cif_paths.append(new_cif_path)
        except Exception as e:
            logger.error(f"复制 CIF 文件失败: {e}")
            # 如果出错，返回原始路径列表
            return cif_paths_list
        
        return new_cif_paths

    def get_fetch_file_Workbench(self) -> StaticWorkbench:
        if hasattr(get_data_handle_info, "__doc__") and get_data_handle_info.__doc__ is not None:
            description = get_data_handle_info.__doc__
        else:
            description = ""
        return StaticWorkbench([FunctionTool(get_data_handle_info, description=description)])
    
    def get_tools_args(self, tool_type: str, file_args: Dict):
        try:
            if tool_type == "handle_diffraction":
                gsas_ii_args = {}
                # print("file_args:",file_args)
                gsas_ii_args['gsa_path'] = file_args.get('gsa_path', '')
                gsas_ii_args['instprm_path'] = file_args.get('instprm_path', '')
                gsas_ii_args['cif_paths'] = file_args.get('cif_paths', [])
                gsas_ii_args['refine_params'] = file_args.get('refine_params', {})
                gsas_ii_args['refine_idx'] = file_args.get('refine_idx', 0)
                gsas_ii_args['gpx_path'] = file_args.get('gpx_path', '')
                gsas_ii_args['task_id'] = str(uuid.uuid4())
                gsas_ii_args['thread_id'] = self._thread_id + "_" + self._user_id
                gsas_ii_args['use_constraints'] = True
                return gsas_ii_args
            elif tool_type == "handle_pdf":
                pdf_args = {
                    "data_file": file_args["g_r_files"][0],
                    "structure_files": file_args["cif_files"],
                    "task_id": str(uuid.uuid4()),
                    "thread_id": self._thread_id + "_" + self._user_id,
                }
                pdf_args.update(file_args["pdf_params"])
                return pdf_args
            elif tool_type == "handle_AIndex":
                AIndex_args = {}
                for i in range(len(file_args["groups"])):
                    group_id = file_args["groups"][i]
                    arguments = {
                            "pattern_file": file_args["txt_files"][i],
                            "task_id": str(uuid.uuid4()),
                            "thread_id": self._thread_id + "_" + self._user_id,
                        }
                    AIndex_args[group_id] = arguments
                return AIndex_args
            elif tool_type == "handle_NPD_Simulator":
                NPD_Simulator_args = {}
                for i in range(len(file_args["groups"])):
                    group_id = file_args["groups"][i]
                    arguments = {
                            "structure_file": file_args["cif_files"][0],
                            "instprm_path": file_args["instprm_files"][i],
                            "task_id": str(uuid.uuid4()),
                            "thread_id": self._thread_id + "_" + self._user_id,
                    }
                    NPD_Simulator_args[group_id] = arguments
                return NPD_Simulator_args
            else:
                raise ValueError(f"Unsupported tool type: {tool_type}")
        except Exception as e:
            import traceback
            traceback.print_exc()

    def get_gsas_ii_info(self, diffraction_outputs: Dict) -> str:
        diffraction = f"## 中子衍射精修结果\n\n"
        rwp = diffraction_outputs["refinement_results"]["rwp"]
        cell_parameters = diffraction_outputs["refinement_results"]["cell_parameters"]
        length_a = cell_parameters[0]["length_a"]
        length_b = cell_parameters[0]["length_b"]
        length_c = cell_parameters[0]["length_c"]
        angle_alpha = cell_parameters[0]["angle_alpha"]
        angle_beta = cell_parameters[0]["angle_beta"]
        angle_gamma = cell_parameters[0]["angle_gamma"]
        volume = cell_parameters[0]["volume"]
        refine_cif_files = diffraction_outputs["refinement_results"]["refined_cif_files"]
        refine_cif_urls = {}
        for i, refine_cif_file in enumerate(refine_cif_files):
            refine_cif_url = self.upload_file(file_path=refine_cif_file)
            refine_cif_file_png = cif_3D_visualization(refine_cif_file)
            refine_cif_file_png_url = self.upload_file(file_path=refine_cif_file_png[0])
            refine_cif_urls["refine_cif_url"] = refine_cif_file_png_url
        output_files = diffraction_outputs["output_files"]
        neutron_refinement_plot_url = self.upload_file(diffraction_outputs["plot_path"])
        diffraction += f"### 精修后的结构文件\n\n"
        for refine_cif_url, refine_cif_file_png_url in refine_cif_urls.items():
            diffraction += f"{i+1}. {refine_cif_url}:\n\n![image.png]({refine_cif_file_png_url})\n\n"
        diffraction += f"### 精修后的晶格参数\n\n"
        diffraction += f"a: {length_a}\n"
        diffraction += f"b: {length_b}\n"
        diffraction += f"c: {length_c}\n"
        diffraction += f"α: {angle_alpha}\n"
        diffraction += f"β: {angle_beta}\n"
        diffraction += f"γ: {angle_gamma}\n"
        diffraction += f"体积: {volume}\n\n"
        diffraction += f"### 精修后的Rwp\n\n{rwp}\n\n"
        diffraction += f"### 精修后的中子衍射图像\n\n![image.png]({neutron_refinement_plot_url})\n\n"
        return diffraction

    def assess_gsas_ii_results(self, current_result):
        need_further_refinement = False
        refinement_message = ""
        if current_result.status == "error":
            refinement_message = f"## 中子衍射第{current_result.group_id}组精修失败，请检查输入参数。\n\n"
        else:
            rwp = current_result.refinement_results["rwp"]
            if rwp > 0.1:
                need_further_refinement = True
                refinement_message = f"## 精修后的Rwp大于0.1，可能需要进一步精修。\n\n"
            else:
                refinement_message = f"## 精修后的Rwp为{rwp:.4f}，精修效果良好。\n\n"
        
        return need_further_refinement, refinement_message
        
    def get_file_base64(self, file_path: str):
        """获取知识库文件的base64编码"""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'rb') as file:
                    file_base64 = base64.b64encode(file.read()).decode('utf-8')
                # file_obj = upload_to_hepai_filesystem(file_path=file_path)
                return file_base64
            else:
                print(f"警告: 文件 {file_path} 不存在")
                return None
        except Exception as e:
            print(f"读取文件时出错: {e}")
            return None
    
    
    
    # TODO: 改成CLS和@classmethod
    async def on_agent_stream(
        self, 
        cancellation_token: CancellationToken,
        system_messages: List[SystemMessage] = [],
        workbench: StaticWorkbench | None = None,
        model_client: HepAIChatCompletionClient | None = None,
        message_queue: asyncio.Queue = None,
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        """
        Process the incoming messages with the assistant agent and yield events/responses as they happen.
        """

        try:
            # Gather all relevant state here
            agent_name = self.name
            model_context = self._model_context
            memory = self._memory
            # system_messages = system_messages
            # workbench = workbench
            handoff_tools = self._handoff_tools
            handoffs = self._handoffs
            # model_client = self._model_client
            model_client_stream = self._model_client_stream
            reflect_on_tool_use = self._reflect_on_tool_use
            tool_call_summary_format = self._tool_call_summary_format
            output_content_type = self._output_content_type
            format_string = self._output_content_type_format

            # # STEP 1: Add new user/handoff messages to the model context
            # await self._add_messages_to_context(
            #     model_context=model_context,
            #     messages=messages,
            # )

            # # STEP 2: Update model context with any relevant memory
            inner_messages: List[BaseAgentEvent | BaseChatMessage] = []
            for event_msg in await self._update_model_context_with_memory(
                memory=memory,
                model_context=model_context,
                agent_name=agent_name,
            ):
                inner_messages.append(event_msg)
                if message_queue is not None:
                    await message_queue.put(event_msg)
                else:
                    yield event_msg

            # STEP 3: Run the first inference
            model_result = None
            async for inference_output in self._call_llm(
                model_client=model_client,
                model_client_stream=model_client_stream,
                system_messages=system_messages,
                model_context=model_context,
                workbench=workbench,
                handoff_tools=handoff_tools,
                agent_name=agent_name,
                cancellation_token=cancellation_token,
                output_content_type=output_content_type,
            ):
                if self.is_paused or cancellation_token.is_cancelled():
                    raise asyncio.CancelledError()
                
                if isinstance(inference_output, CreateResult):
                    model_result = inference_output
                else:
                    # Streaming chunk event
                    if message_queue is not None:
                        await message_queue.put(inference_output)
                    else:
                        yield inference_output

            assert model_result is not None, "No model result was produced."

            # --- NEW: If the model produced a hidden "thought," yield it as an event ---
            if model_result.thought:
                thought_event = ThoughtEvent(content=model_result.thought, source=agent_name)
                if message_queue is not None:
                        await message_queue.put(thought_event)
                else:
                    yield thought_event
                inner_messages.append(thought_event)

            # Add the assistant message to the model context (including thought if present)
            await model_context.add_message(
                AssistantMessage(
                    content=model_result.content,
                    source=agent_name,
                    thought=getattr(model_result, "thought", None),
                )
            )

            # STEP 4: Process the model output
            async for output_event in self._process_model_result(
                model_result=model_result,
                inner_messages=inner_messages,
                cancellation_token=cancellation_token,
                agent_name=agent_name,
                system_messages=system_messages,
                model_context=model_context,
                workbench=workbench,
                handoff_tools=handoff_tools,
                handoffs=handoffs,
                model_client=model_client,
                model_client_stream=model_client_stream,
                reflect_on_tool_use=reflect_on_tool_use,
                tool_call_summary_format=tool_call_summary_format,
                tool_call_summary_prompt=self._tool_call_summary_prompt,
                output_content_type=output_content_type,
                format_string=format_string,
            ):
                if self.is_paused or cancellation_token.is_cancelled():
                    raise asyncio.CancelledError()
                if message_queue is not None:
                        await message_queue.put(output_event)
                else:
                    yield output_event

        except asyncio.CancelledError:
            # If the task is cancelled, we respond with a message.
            cancellederror = Response(
                chat_message=TextMessage(
                    content="The task was cancelled by the user.",
                    source=self.name,
                    metadata={"internal": "yes"},
                ),
                inner_messages=inner_messages,
            )
            if message_queue is not None:
                await message_queue.put(cancellederror)
            else:
                yield cancellederror
        except Exception as e:
            logger.error(f"Error in {self.name}: {e}")
            import traceback
            print(traceback.format_exc())

            # yield StopMessage(source=self.name, content=f"An error occurred while executing the task: {e}",)
            # add to chat history
            await model_context.add_message(
                AssistantMessage(
                    content=f"An error occurred while executing the task: {e}",
                    source=self.name
                )
            )
            error_response = Response(
                chat_message=StopMessage(
                    content=f"An error occurred while executing the task: {e}",
                    source=self.name,
                    metadata={"internal": "no"},
                ),
                inner_messages=inner_messages,
            )
            if message_queue is not None:
                await message_queue.put(error_response)
            else:
                yield error_response
        finally:
            pass

    async def get_mcp_json_result(self, tool_name: str, arguments: Dict, workbench: StaticWorkbench) -> Dict:
        # print('arguments:', arguments)
        ToolResult = await workbench.call_tool(
            name = tool_name,
            arguments = arguments)
        # ToolResult_json = json.loads(ToolResult.result[0].content)[0]["text"]
        try:
            print("Hello,I'm trying.")
            json_results = json.loads(ToolResult.result[0].content)
            if isinstance(json_results, list):
                json_result = json_results[0]
                if isinstance(json_result, dict) and 'type' in json_result:
                    if json_result['type'] == 'text':
                        text_content = json_result['text']
                        # 检查text内容是否为有效JSON
                        if text_content.strip().startswith('{') or text_content.strip().startswith('['):
                            try:
                                ToolResult_json = json.loads(text_content)
                            except json.JSONDecodeError:
                                # 如果不是有效JSON，当作错误信息处理
                                ToolResult_json = {"state": "completed", "status": "error", "result": text_content}
                        else:
                            # 不是JSON格式，当作错误信息处理
                            ToolResult_json = {"state": "completed", "status": "error", "result": text_content}
                    else:
                        ToolResult_json = {"state": "completed", "status": "error", "result": "Unexpected response type"}
                else:
                    ToolResult_json = {"state": "completed", "status": "error", "result": "Invalid response format"}
            else:
                ToolResult_json = {"state": "completed", "status": "error", "result": "Response is not a list"}
        except Exception as e:
            print("Sorry, It failed.")
            import traceback
            traceback.print_exc()
            ToolResult_json = {"state": "completed", "status": "error", "result": str(e)}
        return ToolResult_json
    
    async def on_tools_stream(
        self, 
        cancellation_token: CancellationToken,
        workbench: StaticWorkbench | None = None,
        tool_name: str | None = None,
        tool_type: str|None = None,
        tool_args: Dict[str, Any] | None = None,
        message_queue: asyncio.Queue = None,
        sleep_time: int = 10,
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        """
        Process the incoming messages with the assistant agent and yield events/responses as they happen.
        """

        try:
            if not tool_args:
                raise ValueError(f"未为{tool_type}提供参数")
            
            model_context = self._model_context
            thread_id = self._thread_id
            user_id = self._user_id
            agent_name = self.name

            complete_response = ""
            inner_messages: List[BaseAgentEvent | BaseChatMessage] = []

            ## 查询状态库，得到GSAS-II的状态
            global_status : ToolsStatus | None = None
            response: DBResponse = self._db_manager.get(
                ToolsStatus, 
                filters={"user_id": user_id,"thread_id": thread_id},
                return_json=False
                )
            if response.status and response.data:
                global_status: ToolsStatus = response.data[0]
            else:
                raise RuntimeError(f"Failed to read global status: {response.message}")
            
            while True: 
                # 通过 MCP workbench 提交任务,并等待输出
                if global_status.gsas_ii_status == ToolsRunStatus.AWAITING_INPUT:
                    # 检测到GSAS-II空闲，提交任务并改变其状态
                    global_status.gsas_ii_status = ToolsRunStatus.RUNNING
                    response: DBResponse = self._db_manager.upsert(global_status)
                    if not response.status or not response.data:
                        raise RuntimeError(f"Failed to save user input: {response.message}")
                    
                    ToolResults = {}
                    if tool_type == "handle_diffraction":
                        if self.is_paused or cancellation_token.is_cancelled():
                            raise asyncio.CancelledError()
                        ToolResult_json = await self.get_mcp_json_result(tool_name = tool_name, arguments = tool_args, workbench = workbench)

                        # 将GSAS-II的输出存入状态库
                        global_status.gsas_ii_output = json.dumps(ToolResult_json['result'])
                        response: DBResponse = self._db_manager.upsert(global_status)
                        if not response.status or not response.data:
                            raise RuntimeError(f"Failed to save gsas_ii output: {response.message}")

                    elif tool_type == "handle_pdf":
                        if self.is_paused or cancellation_token.is_cancelled():
                            raise asyncio.CancelledError()
                        ToolResult_json = await self.get_mcp_json_result(tool_name = tool_name, arguments = tool_args, workbench = workbench)
                        print("ToolResult_json:", ToolResult_json)
                        ToolResults = {
                            "arguments": tool_args,
                            "ToolResult_json": ToolResult_json, 
                            "state": ToolResult_json["state"]}
                        message = f"中子精修任务已提交，精修PDF参数为：qmax:{tool_args['qmax']}, qdamp:{tool_args['qdamp']}, rmax:{tool_args['rmax']}, rmin:{tool_args['rmin']}...\n\n"
                        yield ModelClientStreamingChunkEvent(content=message, source=agent_name)
                        complete_response += message

                    elif tool_type == "handle_AIndex":
                        for group_id, arguments in tool_args.items():
                            if self.is_paused or cancellation_token.is_cancelled():
                                raise asyncio.CancelledError()
                            ToolResult_json = await self.get_mcp_json_result(tool_name = tool_name, arguments = arguments, workbench = workbench)
                            ToolResults[group_id] = {
                                "arguments": arguments,
                                "ToolResult_json": ToolResult_json, 
                                "state": ToolResult_json["state"]}
                            message = f"{group_id}组的中子衍射AIndex预测任务已提交...\n\n"
                            yield ModelClientStreamingChunkEvent(content=message, source=agent_name)
                            complete_response += message

                    elif tool_type == "handle_NPD_Simulator":
                        for group_id, arguments in tool_args.items():
                            if self.is_paused or cancellation_token.is_cancelled():
                                raise asyncio.CancelledError()
                            ToolResult_json = await self.get_mcp_json_result(tool_name = tool_name, arguments = arguments, workbench = workbench)
                            ToolResults[group_id] = {
                                "arguments": arguments,
                                "ToolResult_json": ToolResult_json, 
                                "state": ToolResult_json["state"]}
                            message = f"{group_id}组的中子粉末衍射模拟任务已提交...\n\n"
                            yield ModelClientStreamingChunkEvent(content=message, source=agent_name)
                        complete_response += message
            
                # 通过循环检查是否有执行结束的
                if global_status.gsas_ii_status == ToolsRunStatus.RUNNING:
                    # 检测到GSAS-II运行中，查询
                    ToolResult_json = await self.get_mcp_json_result(tool_name = tool_name, arguments = tool_args, workbench = workbench)
                    if ToolResult_json["state"] == "completed":
                        # 将GSAS-II的输出存入状态库
                        # print("看看有没有cif:", ToolResult_json['result']['refinement_results']['refined_cif_files'])
                        global_status.gsas_ii_output = json.dumps(ToolResult_json["result"])
                        response: DBResponse = self._db_manager.upsert(global_status)
                        if not response.status or not response.data:
                            raise RuntimeError(f"Failed to save gsas_ii output: {response.message}")
                        break
                
                await asyncio.sleep(sleep_time)

            global_status.gsas_ii_status = ToolsRunStatus.AWAITING_INPUT
            response: DBResponse = self._db_manager.upsert(global_status)
            if not response.status or not response.data:
                raise RuntimeError(f"Failed to save user input: {response.message}")

        except asyncio.CancelledError:
            # If the task is cancelled, we respond with a message.
            cancellederror = Response(
                chat_message=TextMessage(
                    content="The task was cancelled by the user.",
                    source=self.name,
                    metadata={"internal": "yes"},
                ),
                inner_messages=inner_messages,
            )
            if message_queue is not None:
                await message_queue.put(cancellederror)
            else:
                yield cancellederror
        except Exception as e:
            logger.error(f"Error in {self.name}: {e}")
            import traceback
            traceback.print_exc()
            # add to chat history
            await model_context.add_message(
                AssistantMessage(
                    content=f"An error occurred while executing the task: {e}",
                    source=self.name
                )
            )
            error_response = Response(
                chat_message=TextMessage(
                    content=f"An error occurred while executing the task: {e}",
                    source=self.name,
                    metadata={"internal": "no"},
                ),
                inner_messages=inner_messages,
            )
            if message_queue is not None:
                await message_queue.put(error_response)
            else:
                yield error_response
        finally:
            pass
    
    async def processor_coroutine(
            self, 
            cancellation_token: CancellationToken, 
            workbench: StaticWorkbench,
            system_message: str,
            inner_messages: List[BaseAgentEvent | BaseChatMessage],
            message_queue: asyncio.Queue):
        """独立协程处理subAgent，使用message_queue参数"""
        try:
            # 调用on_agent_stream并传入message_queue
            async for _ in self.on_agent_stream(
                cancellation_token,
                system_messages=self._system_messages+[SystemMessage(content=system_message, source=self.name)],
                workbench=workbench,
                model_client=self._model_client,
                message_queue=message_queue,  # 关键：传入队列参数
            ):
                # 这里不需要处理，因为所有消息都会自动放入队列
                pass
        except Exception as e:
            # 发生异常时将异常信息放入队列
            error_response = Response(
                chat_message=TextMessage(
                    content=f"PDF处理异常: {str(e)}",
                    source=self.name,
                    metadata={"internal": "no"},
                ),
                inner_messages=inner_messages,
            )
            await message_queue.put(error_response)
        finally:
            # 处理完成后放入结束标志
            await message_queue.put(None)  # None作为结束标志

    async def on_messages_stream(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
        ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        """
        Process the incoming messages with the assistant agent and yield events/responses as they happen.
        """
        # monitor the pause event
        if self.is_paused or cancellation_token.is_cancelled():
            yield Response(
                chat_message=TextMessage(
                    content=f"The {self.name} is paused.",
                    source=self.name,
                    metadata={"internal": "yes"},
                )
            )
            return

        # # Set up background task to monitor the pause event and cancel the task if paused.
        # async def monitor_pause() -> None:
        #     await self._paused.wait()
        #     self.is_paused = True

        # monitor_pause_task = asyncio.create_task(monitor_pause())

        try:
            
            # 获取我当前的工作状态和GSAS-II的状态，获取不到就是初始状态:我没有工作，COMPLETE状态，GSAS-II没有工作，AWAITING_INPUT状态
            response: DBResponse = self._db_manager.get(
                ToolsStatus, 
                filters={"user_id": self._user_id,"thread_id": self._thread_id},
                return_json=False
                )
            if response.status and response.data:
                global_status: ToolsStatus = response.data[0]
            else:
                global_status = ToolsStatus(
                    user_id = self._user_id,
                    thread_id = self._thread_id,
                    )
                global_status.gsas_ii_status = ToolsRunStatus.AWAITING_INPUT
                global_status.rongzai_status = ToolsRunStatus.COMPLETE
                self._db_manager.upsert(global_status)

            ###################################################################
            ### 仅测试用：打印用户输入的原始信息
            logger.info("=== 用户输入的原始信息 ===")
            for i, msg in enumerate(messages):
                logger.info(f"消息 {i + 1} - 类型: {type(msg).__name__}")
                logger.info(f"内容: {msg.content}")
                logger.info("-" * 50)
            ###################################################################
            
            
            # 获取用户上传文件的文件名
            metadata = messages[-1].metadata or {}
            attached_files_info = json.loads(metadata.get("attached_files", "[]"))
            uploaded_file_names = [
                file_info.get("name", "")
                for file_info in attached_files_info
                if isinstance(file_info, dict)
            ]
            # 将用户输入的消息加入到model_context中,此时我要标注是用户的输入
            # 下层代码做了支持，现在不需要做这一步了
            # attachment_text = ""
            # if attached_files_info:
            #     file_names = [file_info["name"] for file_info in attached_files_info]
            #     attachment_text = f"用户上传了附件文件：{'、'.join(file_names)}"

            content = messages[-1].content
            if isinstance(content, list):
                text_content = "".join(x for x in content if isinstance(x, str))
            else:
                text_content = str(content)

            text_content = " ".join(text_content.replace("\n", " ").split())
            messages[-1].content = f"user input：{text_content}".strip()
            await self._add_messages_to_context(
                model_context=self._model_context,
                messages=[messages[-1]],
            )

            # 正式开始RongzaiAgent的工作
            inner_messages: List[BaseAgentEvent | BaseChatMessage] = [] # 这个用不到，先放在这；这个每次对话都会重置
            while True: # 这里进入一个无限循环，直到大模型认为需要返回给用户信息
                # 由蓉仔根据用户的输入和当前它的状态、GSAS-II的状态来决定要做什么
                async for message in self.on_agent_stream(
                    cancellation_token,
                    system_messages=self._system_messages+[SystemMessage(content=intention_system_message)],
                    workbench=self.get_fetch_file_Workbench(),
                    model_client=self._model_client,
                    ):
                    if isinstance(message, Response):
                        inner_messages.append(message.chat_message)
                        if isinstance(message.chat_message, ToolCallSummaryMessage):
                            user_handle_info = message.chat_message.content
                            
                            # 万一模型返回了一个字符串，则需要将其转换为字典
                            if isinstance(user_handle_info, str):
                                
                                user_handle_info = ast.literal_eval(user_handle_info) 
                            message.chat_message.metadata["internal"] = "yes"
                            yield message.chat_message
                        elif isinstance(message.chat_message, HandoffMessage):
                            # yield ModelClientStreamingChunkEvent(content=message.chat_message.content, source=self.name)
                            await self._add_messages_to_context(
                                    model_context=self._model_context,
                                    messages=[message.chat_message])
                            yield message
                            return
                        elif isinstance(message.chat_message, StopMessage):
                            yield ModelClientStreamingChunkEvent(content=message.chat_message.content, source=self.name)
                            yield message
                            return 
                        else:
                            yield message
                            return

                    else:
                        yield message
                                 
                # 到这一步，说明蓉仔已经返回了结构化的输出user_handle_info,这意味后续要进行专业的数据处理，不是简单的回复信息了
                
                # #将user_handle_info更新到数据库
                # print("user_handle_info:",user_handle_info)
                # tools_status.user_handle_info = json.dumps(user_handle_info)
                # response: DBResponse = self._db_manager.upsert(tools_status)
                # if not response.status or not response.data:
                #     raise RuntimeError(f"Failed to save user input: {response.message}")
                    
                print("user_handle_info:",user_handle_info)
                # 开始判断下一步工作类型
                if user_handle_info['require_type'] == 'refine_init':
                    #告知用户开始工作
                    yield ModelClientStreamingChunkEvent(content=f"{user_handle_info['info']}\n\n", source=self.name)
                    
                    # 保存用户初始输入到状态库为了后续生成报告时读取run_id等信息
                    global_status.first_user_handle_info = json.dumps(user_handle_info)
                    response: DBResponse = self._db_manager.upsert(global_status)
                    if not response.status or not response.data:
                        raise RuntimeError(f"Failed to save user input: {response.message}")
                    
                    # 检查用户输入，并且重构格式以适用gsas工具
                    verified_dict = verify_data_handle_info(
                        data_handle_info=user_handle_info,
                        data_dir=self._data_dir,
                        user_id=self._user_id,
                        uploaded_file_names=uploaded_file_names,
                    )
                    
                    #判断检查是否通过
                    if verified_dict['status'] == 'success':
                        # 通过，根据蓉仔的决策，更新tools_status并同步到状态库，然后继续后续处理
                        global_status.gsas_ii_input = json.dumps(self.get_tools_args('handle_diffraction',verified_dict['data']))
                        global_status.verified_dict = json.dumps(verified_dict['data'])
                        global_status.report_content = verified_dict['data']["instrument_user_info"]
                        response: DBResponse = self._db_manager.upsert(global_status)
                        if not response.status or not response.data:
                            raise RuntimeError(f"Failed to save user input: {response.message}")
                    else:
                        # 未通过，告知用户错误原因，结束本次处理
                        yield Response(
                            chat_message=TextMessage(
                                content=f"{verified_dict['message']}",
                                source=self.name,
                                metadata={"internal": "no"},
                            ),
                            inner_messages=inner_messages,
                        )
                        await self._add_messages_to_context(
                                    model_context=self._model_context,
                                    messages=[TextMessage(
                                        content=f"{verified_dict['message']}",
                                        source=self.name)])
                        global_status.rongzai_status = ToolsRunStatus.COMPLETE
                        self._db_manager.upsert(global_status)
                        return
                    
                    # 根据蓉仔的决策，使用GSAS-II工具精修一次, 注意，这里精修完后，GSAS-II工具会直接把精修结果保存在状态库中
                    async for message in self.on_tools_stream(
                            cancellation_token,
                            workbench=self._GSASII_Workbench,
                            tool_name="write_info",
                            tool_type = "handle_diffraction",
                            tool_args = json.loads(global_status.gsas_ii_input), 
                            sleep_time=self._sleep_time,
                            ):
                            if isinstance(message, Response):
                                inner_messages.append(message.chat_message)
                                if isinstance(message.chat_message, HandoffMessage):
                                    yield message
                                    return
                                else:
                                    message.chat_message.metadata["internal"] = "yes"
                                    yield message.chat_message
                            else:
                                yield message
                        
                    # 第一次精修完成, 拿到GSAS-II工具精修结果，更新global_status并同步到状态库
                    response: DBResponse = self._db_manager.get(
                        ToolsStatus, 
                        filters={"user_id": self._user_id,"thread_id": self._thread_id},
                        return_json=False
                        )
                    if response.status and response.data:
                        global_status: ToolsStatus = response.data[0]
                        gsas_ii_output = global_status.gsas_ii_output
                    else:
                        raise ValueError("状态库读取失败！")
                    
                    response: DBResponse = self._db_manager.upsert(global_status)
                    if not response.status or not response.data:
                        raise RuntimeError(f"Failed to save user input: {response.message}")

                    # 将GSAS-II精修结果加入上下文
                    gsas_ii_output_json = json.loads(gsas_ii_output)
                    
                    if gsas_ii_output_json.get('status','') == 'error':
                        error_message = gsas_ii_output_json.get('error','未知错误')
                        error_position = gsas_ii_output_json.get('traceback','未知位置')
                        yield ModelClientStreamingChunkEvent(content=f"精修过程中出现错误，原因：{error_message}\n\n 报错位置：{error_position}\n\n", source=self.name)
                        await self._add_messages_to_context(
                                    model_context=self._model_context,
                                    messages=[TextMessage(
                                        content=f"精修过程中出现错误，原因：{error_message}",
                                        source=self.name)])
                        self._db_manager.upsert(global_status)
                        return
                    else:
                        #让用户看到这次精修的效果图
                        neutron_refinement_plot_url = self.upload_file(file_path=gsas_ii_output_json['plot_path'])
                        info2user = f"### ![image.png]({neutron_refinement_plot_url})\n\n"
                        yield ModelClientStreamingChunkEvent(content=info2user, source=self.name)
                    
                    # 精修完成，返回报告内容，等待下一次输入
                    if isinstance(gsas_ii_output_json, str):
                        gsas_ii_output_json = json.loads(gsas_ii_output_json)
                    
                    # 复制 gpx 文件到 gsa 文件夹并重命名
                    verified_dict = json.loads(global_status.verified_dict)
                    gsa_path = verified_dict.get('gsa_path', '')
                    gpx_path = gsas_ii_output_json.get('gpx_path', '')
                    if gsa_path and gpx_path and os.path.exists(gpx_path):
                        new_gpx_path = self.copy_gpx_to_gsa_folder(gpx_path, gsa_path)
                    
                    # 复制精修后的 cif 文件到 gsa 文件夹
                    cif_paths_list = gsas_ii_output_json.get("refinement_results", {}).get("refined_cif_files", [])
                    if gsa_path and cif_paths_list:
                        new_cif_paths = self.copy_cif_files_to_gsa_folder(cif_paths_list, gsa_path)
                    
                    gsas_ii_refine_info = "gpx after refine: " + gsas_ii_output_json['gpx_path']
                    try:
                        lst_message = prune_lst_keep_main(gsas_ii_output_json['lst_path'])
                    except Exception as e:
                        lst_message = "精修初始化完成，可以进行后续精修操作。"
                    refinement_log = gsas_ii_output_json['refinement_log']
                    image = Image.from_file(file_path=gsas_ii_output_json['plot_path'])
                    multimodal_message = MultiModalMessage(
                        source=self.name,
                        content=[
                            f"GSAS-II input: {gsas_ii_refine_info},{lst_message},refinement log: {refinement_log}；refinement image also attached; 注意这不是用户的输入，你要使用和用户最近一次输入的相同的语言或用户显示指定的语言回复，不要管其他提示词用的什么语言",
                            image
                        ])

                    await self._add_messages_to_context(
                        model_context=self._model_context,
                        messages=[multimodal_message]
                    )
                
                elif user_handle_info['require_type'] == 'refine_pause':
                    response: DBResponse = self._db_manager.upsert(global_status)
                    if not response.status or not response.data:
                        raise RuntimeError(f"Failed to save user input: {response.message}")
                    
                    
                    # 拿到精修的结果
                    response: DBResponse = self._db_manager.get(
                        ToolsStatus, 
                        filters={"user_id": self._user_id,"thread_id": self._thread_id},
                        return_json=False
                        )
                    if response.status and response.data:
                        global_status: ToolsStatus = response.data[0]
                        gsas_ii_output = global_status.gsas_ii_output
                    else:
                        raise ValueError("整理报告时未发现相关精修数据！")
                    
                    #拿到精修的图片后和精修结果一并返回给用户
                    gsas_ii_output_json = json.loads(gsas_ii_output)
                    if isinstance(gsas_ii_output_json, str):
                        gsas_ii_output_json = json.loads(gsas_ii_output_json)
                    neutron_refinement_plot_url = self.upload_file(file_path=gsas_ii_output_json['plot_path'])
                    info2user = f"### ![image.png]({neutron_refinement_plot_url})\n\n"
                    info2user += f"{user_handle_info['info']}\n\n"

                    yield ModelClientStreamingChunkEvent(content=info2user, source=self.name)
                    yield Response(
                        chat_message=TextMessage(
                            content=info2user,
                            source=self.name,
                            metadata={"internal": "yes"},
                        ),
                        inner_messages=inner_messages,
                    )
                    return

                elif user_handle_info['require_type'] == 'refine_finish':
                    # 告知用户会为他生成报告
                    message = f"好的！正在为您生成本次精修结果报告，请稍后...\n\n"
                    yield ModelClientStreamingChunkEvent(content=message, source=self.name)

                    # 根据蓉仔的决策，更新status并同步到状态库，然后继续后续处理
                    response: DBResponse = self._db_manager.get(
                        ToolsStatus, 
                        filters={"user_id": self._user_id,"thread_id": self._thread_id},
                        return_json=False
                        )
                    if response.status and response.data:
                        global_status: ToolsStatus = response.data[0]
                    else:
                        raise ValueError("整理报告时未发现相关精修数据！")
                    
                    response: DBResponse = self._db_manager.upsert(global_status)
                    if not response.status or not response.data:
                        raise RuntimeError(f"Failed to save user input: {response.message}")
                    
                    # 准备生成报告
                    report_to_user = "下面是您当前的中子衍射数据精修报告：\n\n"
                    report_to_user += global_status.report_content
                    gsas_ii_results = json.loads(global_status.gsas_ii_output)
                    gsas_ii_report_content = self.get_gsas_ii_info(
                        diffraction_outputs=gsas_ii_results)
                    report_to_user += f"\n\n{gsas_ii_report_content}\n\n"
                    ## 将报告保存到数据库
                    global_status.report_content = report_to_user
                    response: DBResponse = self._db_manager.upsert(global_status)
                    if not response.status or not response.data:
                        raise RuntimeError(f"Failed to save report content: {response.message}")
                    ## 将报告保存为文件
                    try:
                        first_user_handle_info = json.loads(global_status.first_user_handle_info)
                        run_id = first_user_handle_info.get("run_id", "")
                        beamline = first_user_handle_info.get("beamline","")
                        report_file_name = f"{beamline}/RUNdataFiles/{run_id}/output/{self._user_id}_{self._thread_id}_report.md"
                        report_file_path = os.path.join(self._data_dir, report_file_name)
                        with open(report_file_path, "w", encoding="utf-8") as f:
                            f.write(report_to_user)
                        report_file_url = self.upload_file(report_file_path)
                        report_to_user += f"\n\n报告文件已上传至{report_file_url}"
                    except:
                        pass
                    
                    for cif_path in self.cif_paths:
                        cif_base64 = self.get_file_base64(cif_path)
                
                        base64_file = FileInfo(
                            name = os.path.basename(cif_path),
                            base64_content = cif_base64,
                            description=f"cif file {os.path.basename(cif_path)} from final refinement",
                            download_method="base64"
                            )
                        
                        files=FilesContent(
                            files=[base64_file],
                            title="cif files",
                            description="cif files from final refinement",
                            )
                        
                        yield FilesEvent(
                            source=self.name,
                            content=files.model_dump(),
                            )
                        
                    gpx_base64 = self.get_file_base64(self.gpx_path)
                    
                    base64_file = FileInfo(
                            name = os.path.basename(self.gpx_path),
                            base64_content = gpx_base64,
                            description=f"gpx file {os.path.basename(self.gpx_path)} from final refinement",
                            download_method="base64"
                            )
                        
                    files=FilesContent(
                        files=[base64_file],
                        title="gpx file",
                        description=f"gpx file from final refinement",
                        )
                    
                    yield FilesEvent(
                        source=self.name,
                        content=files.model_dump(),
                        )
                    
                    yield ModelClientStreamingChunkEvent(content=report_to_user, source=self.name)
                    yield Response(
                        chat_message=TextMessage(
                            content=report_to_user,
                            source=self.name,
                            metadata={"internal": "yes"},
                        ),
                        inner_messages=inner_messages,
                    )
                    return

                elif user_handle_info['require_type'] == 'refine':
                    # 根据蓉仔的决策，更新tools_status并同步到状态库，然后继续后续处理
                    user_handle_info['cif_paths'] = json.loads(global_status.verified_dict)['cif_paths'] # 获取original_cif_paths
                    global_status.gsas_ii_input = json.dumps(self.get_tools_args('handle_diffraction',user_handle_info))
                    response: DBResponse = self._db_manager.upsert(global_status)
                    if not response.status or not response.data:
                        raise RuntimeError(f"Failed to save user input: {response.message}")

                    #将模型对接下来精修的评论输出出来
                    yield ModelClientStreamingChunkEvent(content=f"{user_handle_info['info']}\n\n", source=self.name)
                    
                    # 蓉仔认为它还需要精修，继续精修
                    # 使用GSAS-II工具精修一次, 注意，这里精修完后，GSAS-II工具会直接把精修结果保存在状态库中
                    async for message in self.on_tools_stream(
                            cancellation_token,
                            workbench=self._GSASII_Workbench,
                            tool_name="write_info",
                            tool_type = "handle_diffraction",
                            tool_args = json.loads(global_status.gsas_ii_input), 
                            sleep_time=self._sleep_time,
                            ):
                            if isinstance(message, Response):
                                inner_messages.append(message.chat_message)
                                if isinstance(message.chat_message, HandoffMessage):
                                    yield message
                                    return
                                else:
                                    message.chat_message.metadata["internal"] = "yes"
                                    yield message.chat_message
                            else:
                                yield message
                                
                    try:
                        # 精修完成，拿到GSAS-II工具精修结果, 更新rongzai_status并同步到状态库
                        response: DBResponse = self._db_manager.get(
                            ToolsStatus, 
                            filters={"user_id": self._user_id,"thread_id": self._thread_id},
                            return_json=False
                            )
                        if response.status and response.data:
                            global_status: ToolsStatus = response.data[0]
                            gsas_ii_output = global_status.gsas_ii_output
                        else:
                            raise ValueError("整理报告时未发现相关精修数据！")
                        
                        global_status.rongzai_status = ToolsRunStatus.RUNNING
                        response: DBResponse = self._db_manager.upsert(global_status)
                        if not response.status or not response.data:
                            raise RuntimeError(f"Failed to save user input: {response.message}")
                    
                        # 将GSAS-II精修结果加入上下文
                        gsas_ii_output_json = json.loads(gsas_ii_output)
                        if isinstance(gsas_ii_output_json, str):
                            gsas_ii_output_json = json.loads(gsas_ii_output_json)
                        if gsas_ii_output_json['status'] == 'error':
                            error_message = gsas_ii_output_json.get('error', '未知错误')
                            error_traceback = gsas_ii_output_json.get('traceback', '无追踪信息')
                            await self._add_messages_to_context(
                            model_context=self._model_context,
                            messages=[TextMessage(
                                content=f"GSAS-II精修失败: {error_message}\n错误详情: {error_traceback}\n你现在的状态：{global_status.rongzai_status}", 
                                source=self.name)]
                            )
                        else:
                            #让用户看到这次精修的效果图
                            neutron_refinement_plot_url = self.upload_file(file_path=gsas_ii_output_json['plot_path'])
                            info2user = f"### ![image.png]({neutron_refinement_plot_url})\n\n"
                            yield ModelClientStreamingChunkEvent(content=info2user, source=self.name)
                            
                            # 复制 gpx 文件到 gsa 文件夹并重命名
                            verified_dict = json.loads(global_status.verified_dict)
                            gsa_path = verified_dict.get('gsa_path', '')
                            gpx_path = gsas_ii_output_json.get('gpx_path', '')
                            if gsa_path and gpx_path and os.path.exists(gpx_path):
                                self.gpx_path = self.copy_gpx_to_gsa_folder(gpx_path, gsa_path)
                            
                            # 复制精修后的 cif 文件到 gsa 文件夹
                            cif_paths_list = gsas_ii_output_json.get("refinement_results", {}).get("refined_cif_files", [])
                            if gsa_path and cif_paths_list:
                                self.cif_paths = self.copy_cif_files_to_gsa_folder(cif_paths_list, gsa_path)
                            
                            gsas_ii_refine_info = "gpx after refine: " + gsas_ii_output_json['gpx_path']
                            lst_message = prune_lst_keep_main(gsas_ii_output_json['lst_path'])
                            refinement_log = gsas_ii_output_json['refinement_log']
                            image = Image.from_file(file_path=gsas_ii_output_json['plot_path'])

                            multimodal_message = MultiModalMessage(
                                source=self.name,
                                content=[
                                    f"GSAS-II input: (1){gsas_ii_refine_info}；(2)lst: {lst_message}；(3)refinement log: {refinement_log}；（4）refinement plot also attached, please check all details in the plot, as a basis for your decision-making in the next step; 注意这不是用户的输入，你要使用和用户最近一次输入的相同的语言或用户显示指定的语言回复，不要管其他提示词用的什么语言",
                                    image
                                ])

                            await self._add_messages_to_context(
                                model_context=self._model_context,
                                messages=[multimodal_message]
                            )
                    except Exception as e:
                        logger.error(f"Error in {self.name}: {e}")
                        import traceback
                        traceback.print_exc()
                        # add to chat history
                        await self._add_messages_to_context(
                            model_context=self._model_context,
                            messages=[TextMessage(content=f"出现异常报错: {e}，需要重新精修。你现在的状态：{global_status.rongzai_status}", source=self.name)]
                        )
                        

        except asyncio.CancelledError:
            # If the task is cancelled, we respond with a message.
            yield Response(
                chat_message=TextMessage(
                    content="The task was cancelled by the user.",
                    source=self.name,
                    metadata={"internal": "yes"},
                ),
                inner_messages=inner_messages,
            )
        except Exception as e:
            logger.error(f"Error in {self.name}: {e}")
            import traceback
            traceback.print_exc()
            # add to chat history
            await self._model_context.add_message(
                AssistantMessage(
                    content=f"An error occurred while executing the task: {e}",
                    source=self.name
                )
            )
            yield Response(
                chat_message=TextMessage(
                    content=f"An error occurred while executing the task: {e}",
                    source=self.name,
                    metadata={"internal": "no"},
                ),
                inner_messages=inner_messages,
            )

        finally:
            # Cancel the monitor task.
            # try:
            #     monitor_pause_task.cancel()
            #     await monitor_pause_task
            # except asyncio.CancelledError:
            #     pass
            pass
    
    @classmethod
    def _from_config(
        cls, config: AssistantAgentConfig, 
        db_manager: DatabaseManager,
        memory_function: Callable = None,
        reply_function: Callable = None,
        **kwargs,
        ) -> Self:
        """Create an assistant agent from a declarative config."""
        if config.structured_message_factory:
            structured_message_factory = StructuredMessageFactory.load_component(config.structured_message_factory)
            format_string = structured_message_factory.format_string
            output_content_type = structured_message_factory.ContentModel

        else:
            format_string = None
            output_content_type = None

        return cls(
            name=config.name,
            model_client=ChatCompletionClient.load_component(config.model_client),
            workbench=Workbench.load_component(config.workbench) if config.workbench else None,
            handoffs=config.handoffs,
            model_context=ChatCompletionContext.load_component(config.model_context) if config.model_context else None,
            tools=[BaseTool.load_component(tool) for tool in config.tools] if config.tools else None,
            memory=[Memory.load_component(memory) for memory in config.memory] if config.memory else None,
            description=config.description,
            system_message=config.system_message,
            model_client_stream=config.model_client_stream,
            reflect_on_tool_use=config.reflect_on_tool_use,
            tool_call_summary_format=config.tool_call_summary_format,
            output_content_type=output_content_type,
            output_content_type_format=format_string,
            metadata=config.metadata,
            memory_function=memory_function,
            reply_function=reply_function,
            db_manager=db_manager,
            **kwargs,
        
        )

        


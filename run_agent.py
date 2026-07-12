import sys
import json
from pathlib import Path
here = Path(__file__).parent.absolute()
# agent_path = str(here.parent)
# sys.path.append(agent_path)

import asyncio
from drsai import (
    HepAIChatCompletionClient, 
    run_backend, 
    run_console, 
    run_worker,
    DrSaiAPP
    )
from autogen_agentchat.messages import TextMessage
from autogen_core.tools import StaticWorkbench
from autogen_ext.tools.mcp import (
    StdioServerParams, 
    SseServerParams,
    mcp_server_tools)
from drsai.modules.managers.database import DatabaseManager
# from src.core.agent.reply_function import action_reply_function
from src.core.agent.agent_config import DataAgentHandoff
from drsai.modules.components.model_client.anthropic import _MODEL_INFO
from src.core.agent.agent import RongZaiAgent
from autogen_core.model_context import (
    BufferedChatCompletionContext,)

from dotenv import load_dotenv
import os
load_dotenv(dotenv_path=os.path.join(here, ".env"), override=True)
data_dir = os.getenv("WORKER_SPACE", "")
parent_path = os.path.dirname(os.path.abspath(__file__))
appdir = os.path.join(parent_path, "tmp/drsai")
os.makedirs(appdir, exist_ok=True)
db_file = Path(appdir) / "drsai.db"
db_uri = f"sqlite:///{db_file.as_posix()}"
VIP_USER_LIST = os.getenv("VIP_USER_LIST", "").split(",") if os.getenv("VIP_USER_LIST") else []

WORKER_PORT = int(os.getenv("RONGZAI_WORKER_PORT", "42812"))
MCP_SSE_URL = os.getenv("RONGZAI_MCP_SSE_URL", "http://127.0.0.1:42501/sse")
WORKER_NAME = os.getenv("RONGZAI_WORKER_NAME", "DrSai-Rongzai")
AGENT_INSTANCE_NAME = os.getenv("RONGZAI_AGENT_INSTANCE_NAME", "DrSai_Rongzai")
HEPAI_BASE_URL = os.getenv("RONGZAI_HEPAI_BASE_URL", "https://aiapi.ihep.ac.cn/apiv2")
HEPAI_ANTHROPIC_BASE_URL = os.getenv("RONGZAI_HEPAI_ANTHROPIC_BASE_URL", "https://aiapi.ihep.ac.cn/apiv2/anthropic")
LOGO_PATH = os.getenv(
    "RONGZAI_LOGO_PATH",
    str((here / "src/configs/resized_rzera_logo.png").resolve()),
)
WORKER_AUTHOR = os.getenv("RONGZAI_WORKER_AUTHOR", "opensource@localhost")
WORKER_DESCRIPTION = os.getenv(
    "RONGZAI_WORKER_DESCRIPTION",
    "Rongzai - Powder neutron diffraction refinement assistant",
)
WORKER_EXAMPLE = os.getenv(
    "RONGZAI_WORKER_EXAMPLE",
    "请帮我完成一次粉末中子衍射谱精修，输入包含数据文件和初始结构文件。",
)
PERMISSION = os.getenv(
    "RONGZAI_PERMISSION",
    "groups: rongzai; users: ; owner: opensource@localhost",
)


def _normalize_users(users: list[str]) -> list[str]:
    return [u.strip() for u in users if u and u.strip()]

print(f"PERMISSION: {PERMISSION}")

llm_mode_config = {
    "minimax": "minimax/minimax-m2.7",
    "磐石": "scienceone/s1-base-ultra",
    "gpt-5": "openai/gpt-5",
    "gpt-4.1": "openai/gpt-4.1",
    "default": "openai/gpt-5"
}

async def get_GSASII_Workbench() -> StaticWorkbench:
    tools = []
    tools.extend(await mcp_server_tools(SseServerParams(
        url = MCP_SSE_URL,
        # url="http://202.122.37.163:42851/sse",
        timeout = 30,
    )))
    return StaticWorkbench(tools)

async def create_agent(
        api_key: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        db_manager: DatabaseManager | None = None,
        defult_config_name: str | None = "default",
    ) -> RongZaiAgent:
    selected_mode = defult_config_name or "default"
    selected_model = llm_mode_config.get(selected_mode, llm_mode_config["default"])
    print(
        f"[LLM_SELECT] mode={selected_mode}, model={selected_model},"
        f"thread_id={thread_id}, user_id={user_id}",
        flush=True,
    )

    if selected_mode == "minimax" or selected_mode == "磐石":
        model_client = HepAIChatCompletionClient(
            model=selected_model,
            api_key=os.getenv("HEPAI_API_KEY", ""),
            base_url=HEPAI_ANTHROPIC_BASE_URL,
            model_info=_MODEL_INFO["claude-sonnet-4-5"],
            max_tokens=60000
        )
    else:
        model_client = HepAIChatCompletionClient(
        model=selected_model,
        api_key=os.getenv("HEPAI_API_KEY", ""),
        base_url=HEPAI_BASE_URL,
    )

    try:
        GSASII_Workbench = await asyncio.wait_for(get_GSASII_Workbench(), timeout=60)
    except asyncio.TimeoutError:
        raise Exception("获取 Workbench 超时，请检查服务器连接")
    tool_info = ""
    for tool in GSASII_Workbench._tools:
        tool_info += f"{tool.name}({tool.description})\n"
    return RongZaiAgent(
        AGENT_INSTANCE_NAME,
        # model_client=model_client_qwen3_235b_a22b,
        model_client=model_client,
        handoffs=[DataAgentHandoff(target="user", description="在无法完成相关操作时，需要向用户询问你需要的信息。")],
        system_message=f"""一定注意，除非用户明确要求，用户用什么语言（如英文、中文、日文等），你就用相同的语言，不需要管系统提示词用的什么语言！你是一个擅长中子衍射数据精修的科研狗。 你可以使用以下工具：\n{tool_info}。</no_think>""",
        description=f"""中子衍射数据精修的专家。""",
        model_context=BufferedChatCompletionContext(buffer_size = 50), # 限制最多2、50条消息
        data_dir = data_dir,
        GSASII_Workbench = GSASII_Workbench,
        sleep_time = 3,
        thread_id=thread_id,
        db_manager=db_manager,
        user_id=user_id,
    )

if __name__ == "__main__":
    
    asyncio.run(
        run_worker(
            # 智能体注册信息
            agent_name=WORKER_NAME,
            author=WORKER_AUTHOR,
            permission=PERMISSION,
            description = WORKER_DESCRIPTION,
            version = "0.1.0",
            logo=LOGO_PATH,
            # 智能体实体
            agent_factory=create_agent, 
            # 后端服务配置
            port = WORKER_PORT, 
            history_mode = "backend",
            # 智能体数据库地址
            engine_uri = db_uri,
            # 数据库及文件存储目录
            base_dir = appdir, 
            examples = [WORKER_EXAMPLE],
            agent_config = llm_mode_config,
            defult_config_name = "default",
            # 是否注册到HepAI智能体平台
            no_register=False,
            # 是否注册为OpenWebUI的pipeline
            enable_openwebui_pipeline=True, 
            # 使用backend/frontend的api_key
            use_api_key_mode = "frontend"
        )
    )


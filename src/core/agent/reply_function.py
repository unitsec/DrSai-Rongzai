# -*- coding: utf-8 -*-
import glob
import os, asyncio, json

# Model client
from drsai import HepAIChatCompletionClient, CancellationToken
from drsai import AssistantAgent

# messages
from autogen_core.models import (
    ChatCompletionClient,
    CreateResult,
    FunctionExecutionResultMessage,
    FunctionExecutionResult,
    LLMMessage,
    UserMessage,
    AssistantMessage,
    SystemMessage,
    RequestUsage,
)
from autogen_agentchat.base import Handoff
from autogen_agentchat.messages import (
    AgentEvent,
    ChatMessage,
    HandoffMessage,
    MemoryQueryEvent,
    ModelClientStreamingChunkEvent,
    TextMessage,
    ToolCallExecutionEvent,
    ToolCallRequestEvent,
    ToolCallSummaryMessage,
    UserInputRequestedEvent,
    ThoughtEvent
)

# tools
from autogen_core import FunctionCall
from drsai import (
    BaseTool,
    FunctionTool,
    StaticWorkbench, 
    Workbench, 
    ToolResult,
    ToolSchema
)

# threading
# from drsai import Thread, ThreadsManager

# others
from typing import List, Dict, Any, Union, AsyncGenerator, Optional
import uuid
import traceback
from datetime import datetime
import re

# ASE
from ase.io import read
from ase.visualize.plot import plot_atoms
import matplotlib.pyplot as plt
import warnings

def get_data_handle_info(
        require_type: str|None = None,
        beamline: str|None = None,
        run_id: str|None = None,
        detector: str|None = None,
        cifs_upload: List[str]|None=None,
        cifs_datasets: List[str]|None=None,
        gsa_path: str = "",
        inst_path: str = "",
        gpx_path: str = "",
        refine_params: Dict = {},
        refine_idx: int = 0,
        info: str|None = None,
) -> Dict[str, str]:
    '''
    下面是你需要输出的结构化参数及其含义
        require_type: 
            你请求的执行类型, 有"refine_init", "refine", "refine_pause", "refine_finish"四种类型
                “refine_init”会根据用户输入找到精修需要的文件，然后启动GSAS工具进行衍射数据精修的初始化，将衍射数据/仪器参数/晶体结构整合为一个gpx工程文件，自动计算背底然后执行一次空精修。最后将初始化结果返回给你。
                “refine”会启动GSAS工具，用你决定的精修参数，在你指定的gpx文件中进行一次精修，然后返回精修结果给你
                “refine_pause”会暂停精修并将当前精修结果返回给用户，等待用户下一步指令
                “refine_finish”会结束精修并将最终精修结果形成报告返回给用户
            一般流程是：
            1.你要先返回“refine_init”初始化精修;
            2.然后返回“refine”开始精修;
            3.然后多次返回“refine”,根据GSASII反馈的结果、你的精修知识来继续精修；
            4.当你认为已经无法精修的更好的时候，返回“refine_pause”暂停精修,等待用户指令；
            5.根据用户指令返回第3步进行“refine”精修，或者“refine_finish”结束精修。
                
        beamline:
            谱仪名称, 如BL16、BL18、BL09、BL15，BL08,BL13等。从用户输入中获取用来定位精修所需文件
        run_id: 
            需要处理的实验RUN号, 如RUN0021905; 如果用户写成run21905等格式,或者写错(如ru21905等), 需要转换成RUN0021905格式。从用户输入中获取用来定位精修所需文件
        detector: 
            用户需要处理的探测器编号,如"group5",“bank14”,"module11203"等。从用户输入中获取用来定位精修所需文件
        cifs_upload 和 cifs_datasets: 
            这两个都是cif文件列表，如["a.cif", "b.cif"];
            用户输入类型1时才会需要。你将cif文件放到cifs_upload里，意味着你要从用户作为附件上传的文件里找这个cif文件;放到cifs_datasets里，意味着你要从数据库里找这个cif文件。你需要根据用户的输入来判断用户指定的cif文件从哪找。
        gsa_path: 
            用户上传的衍射数据文件的文件名。如果用户没有上传，这里返回空字符串。这里虽然叫gsa_path，但是也可以返回其他格式的衍射数据哦，比如dat,txt等。从用户输入中获取用来定位精修所需文件
        inst_path:
            用户上传的仪器参数文件的文件名。如果用户没有上传，这里返回空字符串。
        refine_params: 
            你认为需要继续精修的参数或者用户要求你继续精修的参数,是个字典，这是你决策的关键参数，详细格式会在后面给出。
            注意如果你返回的refine_params为空的话是什么都不会精修的。 
        refine_idx: 
            下一次精修是第几轮次。你返回refine_init时这里你应该设0,后续依次递增。用户输入类型1、类型2以及GSASII工具输入的时候才需要。
            GSAS工具会根据你给的refine_idx，在执行精修或初始化后，保存一个备份的gpx文件，命名格式为"{原始gpx文件名}_{refine_idx}.gpx"，方便你精修失败后回退，重新指定精修策略。
        gpx_path: 
            准备返回给用户或者GSASII工具的gpx文件路径，用户输入类型2以及GSASII工具输入的时候才需要
            一定注意检查这个路径是对的！
        info: 
            你接下来要做什么，以及你为什么要这么做，如果要指定精修参数，需要明确出来要修哪些。
            仅在"refine_pause"时，你需要用和用户相同的语言，以表格的形式在这里返回:
                最新的lst文件内的所有信息
                所有你能修的参数有哪些，这里面你修了哪些，没修哪些，注意是所有！
                接下来的建议是什么
            

    这里详细说明一下 `refine_params` 的格式：
        它是一个字典，键是你能够精修的所有参数名称，键值的格式如下
        | 参数 | 类型 | 默认值 | 说明 |
        | `refine_cycle` | int | 1 | 精修循环次数 (Refine Cycle) |
        | `refine_background` | bool | False | 是否精修背景 |
        | `background_coeffs` | int | 3 | 背景函数系数数量 |
        | `refine_scale` | bool | False | scale |
        | `refine_cell` | bool | False | 晶胞参数 (a, b, c, α, β, γ)，启用则在精修中调整晶胞 |
        | `initial_cell` | dict/list | None | 在精修前设置晶胞初始值（见下文详细说明） |
        | `refine_absorption` | bool | False | 吸收，用于修正由吸收导致的衍射峰强度系统性偏差 |
        | `refine_instrument_alpha` | bool | False | 仪器参数alpha(仪器参数中影响最大的一个) | 
        | `refine_instrument_beta` | bool | False | 仪器参数beta-0, beta-1, beta-q |
        | `refine_instrument_sig` | bool | False | 仪器参数sig-0, sig-1, sig-2, sig-q |
        | `refine_instrument_x` | bool | False | 仪器参数X |
        | `refine_instrument_y` | bool | False | 仪器参数Y |
        | `refine_instrument_z` | bool | False | 仪器参数Z |
        | `refine_atoms` | dict | {} | 要精修的原子标签字典, 例如: {'Fe1':'XU' , 'O2': 'XUF'}或{'all': 'XU'} |
        注意：'X' 为位置，'U' 为等效各向同性温度因子，'F' 为占位率。例如 'XU' 表示同时精修位置和 U。
        | `refine_size` | bool | False | 晶粒尺寸,一般不修,除非你有特殊需求 |
        | `refine_mustrain` | bool | False | 微应变,一般不修,除非你有特殊需求|
        | `initial_mustrain` | float/list/dict | None | 在精修前设置微应变初始值，仅支持isotropic模式（见下文详细说明） |
        | `initial_atom_uiso` | dict/list/float | None | 在精修前设置原子热无序因子(Uiso)初始值，支持多种格式（见下文详细说明） |
        | `refine_phase_fraction` | bool | False | 相分数, 仅多相精修中需要 |

        参数 `initial_cell`用途与使用方法：
            - 目的：在执行任何晶胞精修之前设置相（phase）的初始晶胞数值，避免直接修改核心.
            - 单位与空间：GSAS 使用实空间晶胞参数（a, b, c 单位 Å；α, β, γ 单位为度），不是倒空间参数。
            - 支持格式：
                1. 列表（按相索引）：例如 `[{'a':5.12,'b':5.12,'c':7.23,'alpha':90,'beta':90,'gamma':120}, ...]`，第 0 项对应第 1 个 phase。
                2. 字典（按相名或索引）：例如 `{'Phase_1': {'a':...}, 0: {'a':...}}`，支持相名或数字索引（或索引的字符串形式）。
            - 行为：如果 `initial_cell` 存在，代码会在精修前把实空间参数写入 `phase.data['General']['Cell']`，采用 GSAS 内部期望的格式：
                `[refine_flag, a, b, c, alpha, beta, gamma, volume]`。
                其中 `refine_flag` 保留原先的布尔值（或设为 False），`volume` 会自动计算并写入（若能计算）。
            - 同时，如果 `refine_cell` 为 True，脚本会尝试调用 `phase.set_refinements({"Cell": True})` 来开启晶胞精修标志（若该方法可用）。

        参数 `initial_mustrain`用途与使用方法：
            - 目的：在执行微应变精修之前设置相（phase）的初始微应变数值。当拟合的衍射峰明显比实验数据宽，且无论如何精修都无法解决时，可将此值设为0来消除微应变的影响。
            - 仅支持isotropic模式（单一数值），单位为 μstrain（微应变）。
            - 支持格式：
                1. 单个数值：例如 `1000.0`，适用于单相或所有相使用相同微应变值。
                2. 列表（按相索引）：例如 `[1000.0, 1200.0]`，第 0 项对应第 1 个 phase。
                3. 字典（按相名或索引）：例如 `{'Phase_1': 1000.0, 0: 1200.0}`，支持相名或数字索引。
            - 行为：如果 `initial_mustrain` 存在，代码会在精修前把微应变参数写入 `gpx.data['Histograms'][hist.name]['Mustrain']`，仅修改参数值，保留原有的精修标志。
            - 特殊用法：当设置 `initial_mustrain: 0` 时，可以消除微应变对衍射峰宽的贡献，用于诊断衍射峰过宽的原因。

        参数 `initial_atom_uiso`用途与使用方法：
            - 目的：在执行精修之前设置相（phase）的原子热无序因子（Uiso）初始值。这对以下情况特别有用：
                当absorption和scale参数高度关联（一个增加另一个必须减小）导致精修卡顿时，将Uiso设为0来隔离这个问题。
            - 单位：Ų（平方埃），典型范围 0.005-0.15。
            - 支持格式：
                1. 字典（按原子标签）：例如 `{'Si': 0.012, 'O': 0.015, 'Fe': 0.010}`，推荐用于简单情况。
                2. 列表（按相和原子索引）：例如 `[[0.012, 0.015], [0.010, 0.014]]`，第 0 项对应第 1 个 phase。
                3. 单个数值：例如 `0.012`，应用于所有原子，最简单的方式。
        
        下面的11条专家知识优先于你的任何其他知识，每次做出精修决定前要全部考虑一遍，确保严格遵守：
        1.不修到Rwp3%以下不要返回给我。如果你多轮精修把所有能尝试的参数都尝试过，到最后Rwp没有修到5%以下，就是陷入了局部最小值，你要从最开始重新规划精修路线，重新选择精修参数。在达到目标之前，这个过程你至少要自己反复3次后才考虑问我。
        2.先从scale开始精修，一次只多开放一个参数，一个个试，直到开放所有能开放的参数。一定不要一次放开多个参数！
        3.每次精修后都要严格审查fit图上是否有任何异常（峰形、峰位、区域拟合缺失以及任何其他你认为异常的地方），Rwp是否上升或没有明显降低，refinement_log是否有报失败或报严重警告，如果有，就不要接受这次结果。不要吝啬回退！ 
        4.吸收对于中子衍射比较重要，一般是要修的,不过修的话要修完仪器参数后再修。
        5.背底一定要放在最后开放精修，并且一定要修。
        6.当精修cell无法对齐bragg峰位和实验峰位时，回退，然后用initial_cell参数设置初始晶胞参数后精修。设置的时候要考虑晶胞参数对衍射峰位置的影响规律以及对称性对晶胞参数的约束，你需要多回退几次，直到你找到合适的初始晶胞参数。
        7.fit图中所有衍射峰的强度拟合好是精修的重点，要格外注意，如果有一些衍射峰强度拟合的不好，先精修位置，再精修占位，且不要精修占位为1的占位。
        8.每一步精修后确保各参数物理上合理，比如晶胞参数不能偏离太多，原子占位率不能大于1或者小于0，温度因子不能为负值等，否则就要返回上一次精修结果，重新选择精修参数。
        9.refine_cycle每次都需要根据情况改动，可以反复回退调节，目的是让每次refine的收敛结果达到最好。
        10.每次的fit图都要严格检查拟合的衍射峰是否和实验数据中的衍射峰宽度匹配，如果拟合的宽度一直大于实验峰宽度，且经过多次精修（调整size、instrument参数等）仍无法解决时，可以尝试返回到没修仪器参数之前的版本，使用initial_mustrain参数将微应变设为0，同时关闭其他所有精修，来诊断过宽的原因是否来自微应变贡献。如果设为0后fit图中峰宽比原来窄了(无论Rw等是否改善)，则说明需要保持这个改动；如果仍无改善，则原因可能在于其他因素（如仪器分辨率、背底拟合等）。
        11.当absorption参数和scale参数高度关联，导致精修振荡或卡顿时（表现为Rwp无法持续改善或反复变化），可以尝试使用 `initial_atom_uiso: 0` 将所有原子热无序因子设为0
        12.如果是多相精修，建议先精修相分数，再精修其他参数。

    '''
    return {
        "require_type": require_type,
        "beamline":beamline,
        "run_id": run_id,
        "detector":detector,
        "cifs_upload":cifs_upload,
        "cifs_datasets": cifs_datasets,
        "gsa_path": gsa_path,
        "inst_path": inst_path,
        "refine_params": refine_params,
        "refine_idx": refine_idx,
        "gpx_path": gpx_path,
        "info": info
    }

def validate_gsas_refine_params(refine_params: Dict) -> Dict:
        """验证GSAS精修参数格式，确保order值不重复"""
        validated_params = refine_params.copy()
        
        # 定义参数的有效范围
        min_order = 1
        max_order = 6
        min_cycle = 0
        max_cycle = 5
        
        valid_ranges = {
            "refine_background": {"order": (min_order, max_order), "cycles": (min_cycle, max_cycle)},
            "refine_cell": {"order": (min_order, max_order), "cycles": (min_cycle, max_cycle)},
            "refine_scale": {"order": (min_order, max_order), "cycles": (min_cycle, max_cycle)},
            "refine_instrument": {"order": (min_order, max_order), "cycles": (min_cycle, max_cycle)},
            "refine_absorption": {"order": (min_order, max_order), "cycles": (min_cycle, max_cycle)},
            "refine_atoms": {"order": (min_order, max_order), "cycles": (min_cycle, max_cycle)},
        }
        
        # 收集所有order值用于重复检查
        order_values = []
        
        for param_name, param_value in refine_params.items():
            if param_name in valid_ranges:
                # 验证参数格式 [顺序, 循环次数]
                if not isinstance(param_value, list) or len(param_value) != 2:
                    raise ValueError(f"参数 {param_name} 格式错误，应为 [顺序, 循环次数]")
                
                order, cycles = param_value
                if not isinstance(order, int) or not isinstance(cycles, int):
                    raise ValueError(f"参数 {param_name} 的顺序和循环次数必须为整数")
                
                # 验证范围
                if order < min_order or order > max_order:
                    raise ValueError(f"参数 {param_name} 的顺序应在 {min_order}-{max_order} 范围内")
                
                if cycles < min_cycle or cycles > max_cycle:
                    raise ValueError(f"参数 {param_name} 的循环次数应在 {min_cycle}-{max_cycle} 范围内")
                
                # 检查order值是否重复
                if order in order_values:
                    raise ValueError(f"精修顺序值 {order} 重复，所有精修模块的顺序必须唯一")
                order_values.append(order)
        
        return validated_params

def verify_data_handle_info(
        data_handle_info: Dict[str, str],
        data_dir: str,
    user_id: str = "",
    uploaded_file_names: List[str] | None = None,
    upload_user_files_root: str = "",
) -> Dict[str, Any]:
    """
    验证数据处理信息是否合法
    Args:
        data_handle_info: 数据处理信息字典
        data_dir: 用户数据所在的目录
    Returns:
        data: 验证后的处理信息字典，包括各个需要处理数据的文件绝对路径
    """

    # print(f"DEBUG: 接收到的数据信息: {json.dumps(data_handle_info, indent=2, ensure_ascii=False)}")

    try:
        status = "success"
        message = ""
        data = {}
        # 直接使用传入的data_handle_info，在其基础上补充信息
        verified_info = data_handle_info.copy()
        uploaded_file_names = uploaded_file_names or []

        def find_uploaded_file(file_name: str) -> str:
            if not file_name or not user_id:
                return ""
            if os.path.isabs(file_name) and os.path.exists(file_name):
                return file_name

            root = upload_user_files_root
            if not root:
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
                root = os.path.join(project_root, "tmp/drsai_ui/files/user")

            user_upload_dir = os.path.join(root, user_id)
            if not os.path.exists(user_upload_dir):
                return ""

            target_name = os.path.basename(file_name).lower()
            for current_root, _, files in os.walk(user_upload_dir):
                for file in files:
                    if file.lower() == target_name:
                        return os.path.join(current_root, file)
            return ""

        # gsa_path / inst_path 只要有值，就按“上传文件”优先查找
        uploaded_gsa_path = find_uploaded_file(data_handle_info.get("gsa_path", ""))
        uploaded_inst_path = find_uploaded_file(data_handle_info.get("inst_path", ""))

        # cifs_upload / cifs_datasets 分开处理
        cifs_upload = data_handle_info.get("cifs_upload", None) or []
        cifs_datasets = data_handle_info.get("cifs_datasets", None) or []
        if len(cifs_upload) == 0 and len(cifs_datasets) == 0:
            status = "error"
            message = "我没有获取到cif文件列表, 请告诉我是哪些cif文件"
            return {"status": status, "message": message, "data": data}

        # 默认值，上传模式下可能没有实验信息
        verified_info["instrument_user_info"] = ""

        # gsa/数据库cif 走数据库时才依赖 run_id；instprm 仅依赖 beamline + detector
        need_run_lookup = (not uploaded_gsa_path) or bool(cifs_datasets)
        need_inst_lookup = not uploaded_inst_path

        run_dir = None
        beamline = data_handle_info.get("beamline")
        run_id = data_handle_info.get("run_id")
        cif_file_dir = ""

        if need_run_lookup:
            if not beamline:
                status = "error"
                message = "我没有获取到谱仪名称，请指定，如BL16、BL18、BL09、BL15等"
                return {"status": status, "message": message, "data": data}
            if not run_id:
                status = "error"
                message = "我没有获取到RUN号，请指定"
                return {"status": status, "message": message, "data": data}

            run_data_dir = os.path.join(data_dir, f"{beamline}/RUNdataFiles")
            if os.path.exists(run_data_dir):
                for folder in os.listdir(run_data_dir):
                    if run_id.lower() in folder.lower():
                        run_dir = os.path.join(run_data_dir, folder)
                        break

            if run_dir is None or not os.path.exists(run_dir):
                status = "error"
                message = f"我关于谱仪{beamline}的数据库中没有{run_id},请确认你提供的谱仪名称和RUN号是否正确，或将数据上传"
                return {"status": status, "message": message, "data": data}

            exp_json_path = os.path.join(run_dir, "experiment.json")
            if os.path.exists(exp_json_path):
                verified_info["instrument_user_info"] = get_experiment_info(run_dir)

            cif_file_dir = os.path.join(run_dir, "cifFiles")

        # 仅查找仪器参数文件时不需要 run_id，但需要 beamline
        if need_inst_lookup and not beamline:
            status = "error"
            message = "我没有获取到谱仪名称，请指定，如BL16、BL18、BL09、BL15等"
            return {"status": status, "message": message, "data": data}

        detector = data_handle_info.get("detector", None)
        if need_inst_lookup and  not detector:
            status = "error"
            message = "我没有获取到探测器编号，请告诉我"
            return {"status": status, "message": message, "data": data}

        # gsa：上传优先，否则走数据库
        if uploaded_gsa_path and os.path.exists(uploaded_gsa_path):
            verified_info["gsa_path"] = uploaded_gsa_path
        else:
            if run_dir is None:
                status = "error"
                message = "需要从数据库查找衍射数据文件时，必须提供正确的RUN号"
                return {"status": status, "message": message, "data": data}
            gsa_file = os.path.join(run_dir, f"{os.path.basename(run_dir).upper()}_{detector}.gsa")
            if not os.path.exists(gsa_file):
                status = "error"
                message = f"我没有在{run_id}下找到{os.path.basename(run_dir).upper()}_{detector}.gsa文件，请检查探测器编号是否正确，或数据是否上传完整"
                return {"status": status, "message": message, "data": data}
            verified_info["gsa_path"] = gsa_file

        # instprm：上传优先，否则走数据库
        if uploaded_inst_path and os.path.exists(uploaded_inst_path):
            verified_info["instprm_path"] = uploaded_inst_path
        else:
            pattern = os.path.join(os.path.join(data_dir, beamline, "instrumentFiles"), f"*{detector}*.instprm")
            matches = glob.glob(pattern)
            if matches:
                verified_info["instprm_path"] = matches[0]
            else:
                status = "error"
                message = f"我没有找到{detector}对应的仪器参数文件(.instprm)，请上传或检查探测器编号"
                return {"status": status, "message": message, "data": data}

        # cif_upload：仅从上传目录解析
        cif_paths = []
        for cif_file in cifs_upload:
            cif_name = os.path.basename(cif_file)
            uploaded_cif_path = find_uploaded_file(cif_name)
            if uploaded_cif_path and os.path.exists(uploaded_cif_path):
                cif_paths.append(uploaded_cif_path)
            else:
                status = "error"
                message = f"上传的cif文件 {cif_file} 不存在或未找到，请确认是否已上传"
                return {"status": status, "message": message, "data": data}

        # cif_datasets：仅从数据库解析
        if cifs_datasets and not cif_file_dir:
            status = "error"
            message = "需要从数据库查找cif文件时，必须提供正确的RUN号"
            return {"status": status, "message": message, "data": data}

        for cif_file in cifs_datasets:
            cif_file_path = os.path.join(cif_file_dir, cif_file)
            if os.path.exists(cif_file_path):
                cif_paths.append(cif_file_path)
            else:
                status = "error"
                message = f"数据库cif文件 {cif_file} 不存在或路径不正确"
                return {"status": status, "message": message, "data": data}
        verified_info["cif_paths"] = cif_paths

    except Exception as e:
        import traceback
        status = "error"
        message = f"数据处理失败: {str(e)}\n{traceback.format_exc()}"
        data = {}
        print(f"数据处理失败: {str(e)}\n{traceback.format_exc()}")
    
    return {"status": status, "message": message, "data": verified_info}


def get_experiment_info(run_dir: str) -> str:
        # experiment.json信息
        with open(os.path.join(run_dir, "experiment.json"), "r") as f:
            exp_dict = json.load(f)
        try:
            sample_symbol = exp_dict["sample_correction"]["sample_name"]
        except:
            sample_symbol = "unknown"
        user = exp_dict["user_name"]
        institute = exp_dict["institute"]
        sample_run_id = exp_dict["sample_run"][0]
        beamline = exp_dict["beamline"]
        start_time = exp_dict["start_time"]
        end_time = exp_dict["end_time"]
        v_run = exp_dict["v_run"][0]
        sampleBG_run = exp_dict["sampleBG_run"][0]
        wave_max = exp_dict["wave_max"]
        wave_min = exp_dict["wave_min"]
        norm_name = "monitor"
        if exp_dict["norm_by_pc"]:
            norm_name = "proton_charge"
        title_prompt = f"""
# 实验报告

**用户：** {user}
**单位：** {institute}
**谱仪：** {beamline}

## 中子衍射数据分析报告

### 实验信息

**样品化学式：** {sample_symbol}

**实验RUN号：** {sample_run_id}

**实验时间：** {start_time} --- {end_time}

**所选择的刻度数据分别是：**

- 钒: {v_run}
- 空盒： {sampleBG_run}

**波长范围：** {wave_min}到{wave_max}埃

**归一条件：** {norm_name}
"""
        return title_prompt

def cif_3D_visualization(
    cif_files: str | List[str], 
    ) -> List[str]:
    """
    cif_files: Path to a single CIF file, directory containing CIF files, or list of CIF file paths
    """
    # 抑制ASE的CIF解析警告
    warnings.filterwarnings("ignore", module="ase.io.cif")
    
    # 处理输入参数，统一转换为文件列表
    if isinstance(cif_files, str):
        if os.path.isdir(cif_files):
            # 如果是目录，获取目录下所有CIF文件
            file_list = [os.path.join(cif_files, f) for f in os.listdir(cif_files) if f.endswith(".cif")]
        elif os.path.isfile(cif_files) and cif_files.endswith(".cif"):
            # 如果是单个CIF文件
            file_list = [cif_files]
        else:
            raise ValueError("Input must be a directory or CIF file")
    elif isinstance(cif_files, (list, tuple)):
        # 如果是文件列表
        file_list = [f for f in cif_files if f.endswith(".cif")]
    else:
        raise TypeError("cif_files must be a string (file/directory path) or list of file paths")
    
    # 遍历所有CIF文件
    png_outputs = []
    for cif_path in file_list:
        filename = os.path.basename(cif_path)
        output = os.path.dirname(cif_path)
        
        try:
            # 读取CIF文件
            atoms = read(cif_path)
            
            # 创建图像
            fig = plt.figure(figsize=(10, 8))
            ax = fig.add_subplot(111)
            plot_atoms(atoms, ax=ax, rotation="10x,20y,30z")
            
            # 生成输出文件名（保留原文件名，仅替换扩展名）
            output_name = os.path.splitext(filename)[0] + ".png"
            output_path = os.path.join(output, output_name)
            
            # 保存图像
            fig.savefig(output_path, dpi=300, bbox_inches='tight')
            plt.close(fig)
            
            print(f"成功处理: {filename} -> {output_name}")
            png_outputs.append(output_path)
            
        except Exception as e:
            print(f"处理失败: {filename} | 错误: {str(e)}")
            
    
    print("所有CIF文件处理完成！")
    return png_outputs

async def generate_dataset(
        result: Dict[str, Any],
        user_task: str,
        arguments: Dict[str, Any],
        model_client: HepAIChatCompletionClient,
        agent_name: str,
        run_id: str,
        cancellation_token: CancellationToken,
) -> AsyncGenerator[Union[CreateResult, ModelClientStreamingChunkEvent, Dict], None]:
    '''
    将执行的结果转化为数据集，上传到对应的数据空间中.
    处理后的数据包括：
    {
        "dataset_name": "****",
        "data_type": 2,
        "summary": "****",
        "researchField": "****",
        "size": 16858561952,
        "files": [
            {
                "name": "****",
                "url": "****",
                "summary": "****",
                "size": "****",
                "filePath": "****"
            },
            
            ]
    }
    需要补充datasetId、dataVerseCode、summary、card、researchField等信息
    '''
    result["datasetId"] = uuid.uuid4().hex
    result["dataVerseCode"] = run_id
    get_info_prompt = f'''我之前的任务是{user_task}。处理的数据集参数为：{json.dumps(arguments, indent=4)}\n。然后处理得到的数据为：\n{json.dumps(result, indent=4)}
现在我需要将处理的数据进行详细的总结，总结的要求如下：
1.summary字段：根据处理需求、处理方法、处理结果进行总结。
2.card字段：对数据集的描述，包括数据来源（特别需要说明处理的数据集ID，所属的数据空间ID，处理的数据集名称）、数据类型和格式、数据大小、数据处理过程、数据使用范围等。
3.researchField字段：使用数据集的研究领域，2-3个关键词即可，必须同时包括中文和英文。

请注意,你输出的格式必须为：

**summary**: 
对数据的总结
**card**: 
数据集的描述
**researchField**: 
数据集的研究领域中英文关键词

除了以上的格式外不要输出其他的内容
''' 
    yield ModelClientStreamingChunkEvent(content="正在总结处理后的数据集信息，请稍后...\n\n", source=agent_name)
    async for chunk in model_client.create_stream(
            messages=[UserMessage(source="user", content=get_info_prompt)],
            cancellation_token=cancellation_token
        ):
        if isinstance(chunk, CreateResult):
            model_result = chunk
        else:
            yield chunk
    
    # 对输出内容进行正则表达式匹配，提取出summary、card、researchField字段
    result["card"] = ""
    pattern = r"\*\*summary\*\*:\s*(.*?)\s*\*\*card\*\*:\s*(.*?)\s*\*\*researchField\*\*:\s*(.*)"
    match = re.search(pattern, model_result.content, re.DOTALL)
    if match:
        summary = match.group(1).strip()
        card = match.group(2).strip()
        research_field = match.group(3).strip()
        # print("summary:", summary)
        # print("card:", card)
        # print("researchField:", research_field)
        result["summary"] = summary
        result["card"] = card
        result["researchField"] = research_field
    yield result

async def generate_report(
        group_id: str,
        result: Dict[str, Any],
        result_log: str,
        backgroud_info: str,
        user_task: str,
        arguments: Dict[str, Any],
        model_client: HepAIChatCompletionClient,
        agent_name: str,
        cancellation_token: CancellationToken,
) -> AsyncGenerator[Union[CreateResult, ModelClientStreamingChunkEvent], None]:
    '''
    将执行的结果转化为报告
    '''
    report_prompt = f'''你是一个将GSAS-II中子衍射精修结果转换为报告的助手，你必须按照以下的格式对得到的信息进行整理。

### 第{group_id}组GSAS-II中子衍射精修结果

#### 精修要求

基于{user_task}总结的精修要求，清晰说明精修的要求

#### 精修后结果

基于精修结果{result}展示以下内容：

- **Rw：** 精修结果中的rwp_values

- **空间群：** 精修后的空间群，如果精修结果中没有则直接为None

- **晶胞参数：** 条理清晰，且完整地展示精修结果中的每个相地晶胞参数，如果精修结果中没有则直接为None

- **精修后的图像：**

![image.png](refinement_plot.png的url, 格式如：https://aiapi.ihep.ac.cn/apiv2/files/file-e6f65091e7/preview)

#### 精修后产生的文件列表

以以下格式展示：
| 文件名 | 文件url | 文件路径 | 文件说明 |
| ---- | ---- | ---- | ---- |


#### 精修log分析

基于以下信息总结第{group_id}组GSAS-II中子衍射精修过程中可能存在的一些问题，并给出相应的建议：
背景任务：{backgroud_info}；
精修中的参数：{arguments}；
精修中的log：{result_log}

注意：但是最后一定要说明所以评论来自于AI，请谨慎参考。
    '''
    yield ModelClientStreamingChunkEvent(content="正在生成报告，请稍后...\n\n", source=agent_name)
    async for chunk in model_client.create_stream(
            messages=[UserMessage(source="user", content=report_prompt)],
            cancellation_token=cancellation_token
        ):
        yield chunk

def get_groups_dict(run_dir:str, run_id:str) -> Dict[str, str]:
    groups_dict = {}
    for file in os.listdir(run_dir):
        if file.startswith(run_id.upper()+"_group") and file.endswith(".gsa"):
            group_id = file.split("_")[1].split(".")[0].upper()
            gsa_file = os.path.join(run_dir, file)
            if group_id in groups_dict:
                groups_dict[group_id]["gsa_file"] = gsa_file
            else:
                groups_dict[group_id] = {"gsa_file": gsa_file}
    return groups_dict

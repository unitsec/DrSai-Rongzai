import os
import logging
import sys
import io
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import GSASIIscriptable as G2sc
import re,shutil
from datetime import datetime
import multiprocessing,queue
import traceback
from glob import glob

from typing import List, Tuple, Dict, Union

from mcp.server.fastmcp import FastMCP
mcp=FastMCP(
    name="GSASII_Refinement_Tool",
    instructions="A tool for refining neutron diffraction data and generating refined structure files.",
    port = 42501, # for transport = "sse" to start a server-sent events (SSE) server
    )

def setup_logging(output_dir):
    """配置日志系统"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(Path(output_dir) / 'refinement.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def initialize_project(neutron_data, neutron_inst, cif_files, output_dir):
    """初始化GSAS-II项目并添加中子数据"""
    logger = logging.getLogger(__name__)

    logger.info("步骤 1/8: 创建新的 GSAS-II 项目")
    gpx = G2sc.G2Project(newgpx=Path(output_dir) / 'neutron_refinement.gpx')
    logger.info("✓ 项目创建成功")

    # 添加中子数据
    if not (neutron_data and neutron_inst):
        raise ValueError("必须提供中子数据和仪器参数文件")

    logger.info("步骤 2/8: 清理数据文件中的NaN值")
    # 对 GSAS 原生格式文件（.gsa/.gda/.raw）保持原样，避免丢失 BANK/头信息。
    # 对纯文本三列数据（x y e）执行 NaN 过滤后再导入。
    try:
        if isinstance(neutron_data, (str, Path)):
            neutron_data = str(neutron_data)
            ext = Path(neutron_data).suffix.lower()

            if ext in {'.gsa', '.gda', '.raw'}:
                logger.info(f"  检测到GSAS原生格式({ext})，跳过重写，仅做文件可读性检查")
                if not Path(neutron_data).exists():
                    raise ValueError(f"数据文件不存在: {neutron_data}")
                if Path(neutron_data).stat().st_size <= 0:
                    raise ValueError(f"数据文件为空: {neutron_data}")
            else:
            # 读取原始文件
                logger.info(f"  读取原始数据文件: {neutron_data}")
                with open(neutron_data, 'r') as f:
                    lines = f.readlines()

                logger.info(f"  文件总行数: {len(lines)}")

                # 寻找有效数据开始位置并过滤NaN值
                valid_data_lines = []
                data_started = False

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # 检查是否为数据行（包含数字）
                    parts = line.split()
                    if len(parts) >= 3:  # 至少需要3列数据
                        try:
                            # 尝试解析所有列为浮点数
                            values = [float(part) for part in parts[:3]]  # 只取前3列
                            # 检查是否包含NaN
                            if not any(np.isnan(values)):
                                valid_data_lines.append(line)
                                data_started = True
                        except ValueError:
                            # 如果转换失败，可能是文件头，继续寻找数据
                            if data_started:
                                # 如果已经开始数据部分但遇到非数值行，可能是数据结束
                                break
                            continue

                if not valid_data_lines:
                    raise ValueError("输入文件中未找到任何有效三列数据行")

                logger.info(f"  从原始文件中提取了 {len(valid_data_lines)} 行有效数据")

                # 创建临时文件保存有效数据。使用 .xye 扩展名以匹配文本读取器。
                temp_dir = Path(output_dir) / 'temp'
                temp_dir.mkdir(exist_ok=True)
                clean_data_file = temp_dir / 'cleaned_neutron_data.xye'

                with open(clean_data_file, 'w') as f:
                    for line in valid_data_lines:
                        f.write(line + '\n')

                neutron_data = str(clean_data_file)
                logger.info(f"  已创建清理后的数据文件: {clean_data_file}")

    except Exception as e:
        logger.error(f"GSA文件数据处理失败: {str(e)}")
        raise ValueError(f"无法处理GSA文件中的NaN值: {str(e)}")

    logger.info("✓ 数据清理完成")

    logger.info("步骤 3/8: 添加中子粉末衍射数据")
    hist = gpx.add_powder_histogram(neutron_data, neutron_inst)
    logger.info(f"  添加中子数据: {neutron_data}")
    logger.info("✓ 数据添加成功")


    # 添加晶体结构
    logger.info("步骤 5/8: 添加晶体结构")
    phases = []
    if cif_files:
        for i, cif_file in enumerate(cif_files, start=1):
            logger.info(f"  添加第 {i}/{len(cif_files)} 个结构文件: {cif_file}")
            phase_name = f"Phase_{i}"
            phase = gpx.add_phase(cif_file, phasename=phase_name, histograms=[hist])
            phases.append(phase)
            logger.info(f"  ✓ 晶体结构 {i} 添加成功 (名称: {phase_name})")

    logger.info("✓ 所有晶体结构添加完成")

    # 设置最大精修循环次数
    logger.info("步骤 6/8: 设置精修控制参数")
    gpx.data['Controls']['data']['max cyc'] = 1
    logger.info("  设置最大精修循环次数: 1")
    logger.info("✓ 控制参数设置完成")

    # 步骤7：计算自动背底 -> 设固定点 -> 用Chebyschev拟合固定点并写回背景参数/通道
    logger.info("步骤 7/8: 自动背底计算并用固定点拟合背景参数")
    try:
        import GSASIIpwd as G2pwd
        from scipy import interpolate as si
        import numpy.ma as ma

        # 获取背景数据与XY数据
        bkgDict = hist.data['Background'][1]
        xydata = hist.data['data'][1]
        npts = len(xydata[0])

        # 初始化autoPrms
        bkgDict['autoPrms'] = bkgDict.get('autoPrms', {})
        bkgDict['autoPrms']['opt'] = bkgDict['autoPrms'].get('opt', 0)
        logLam = bkgDict['autoPrms'].get('logLam', min(10, float(int(10 * np.log10(max(1, npts)) ** 1.5) - 9.5) / 10.))
        bkgDict['autoPrms']['logLam'] = logLam

        # 步骤1: 计算自动背底
        bkgdata = G2pwd.autoBkgCalc(bkgDict, ma.getdata(xydata[1]))

        # 步骤2: 从自动背底中取固定点（均匀采样，约100点）
        step = max(1, npts // 100)
        try:
            xs = ma.getdata(xydata[0])
            ys = ma.getdata(bkgdata)
        except Exception:
            xs = xydata[0]
            ys = bkgdata
        bkgDict['FixedPoints'] = [tuple(pt) for pt in zip(xs[::step], ys[::step])]
        bkgDict['autoPrms']['Mode'] = 'fit'

        # 步骤3: 用OnBkgFit逻辑拟合固定点 -> 得到背景参数
        if 'FixedPoints' not in bkgDict or not len(bkgDict['FixedPoints']):
            logger.warning("  没有固定点，跳过拟合")
        else:
            # 排序并扩展范围
            bkgDict['FixedPoints'] = sorted(bkgDict['FixedPoints'], key=lambda pair: pair[0])
            X = [x for x, y in bkgDict['FixedPoints']]
            Y = [y for x, y in bkgDict['FixedPoints']]

            limits = hist.data['Limits'][1]
            if X[0] > limits[0]:
                X = [limits[0]] + X
                Y = [Y[0]] + Y
            if X[-1] < limits[1]:
                X += [limits[1]]
                Y += [Y[-1]]

            # 内插到数据网格
            xBeg = np.searchsorted(xydata[0], limits[0])
            xFin = np.searchsorted(xydata[0], limits[1])
            xdata = xydata[0][xBeg:xFin]
            ydata = si.interp1d(X, Y, bounds_error=False, fill_value=(Y[0], Y[-1]))(ma.getdata(xdata))

            # 权重和零向量
            W = [1] * len(xdata)
            Z = [0] * len(xdata)

            # 获取仪器参数
            inst = hist.data['Instrument Parameters'][0]
            inst2 = hist.data['Instrument Parameters'][1]

            # 清除仪器参数的精修标志（避免在拟合背景时改变仪器）
            def ClearInstRefineFlags(inst_dict):
                for parm in inst_dict:
                    if parm in ['U','V','W','X','Y','Z','SH/L','I(L2)/I(L1)',
                               'alpha','A','B','C','beta-0','beta-1','beta-q',
                               'sig-0','sig-1','sig-2','sig-q']:
                        if isinstance(inst_dict[parm], (list, tuple)) and len(inst_dict[parm]) > 2:
                            inst_dict[parm][2] = False

            ClearInstRefineFlags(inst)

            # 获取背景参数描述与可变列表
            bakType, bakDict, bakVary = G2pwd.SetBackgroundParms(bkgDict)

            # 检查参数点是否足够
            if len(bakVary) * 1.5 > len(X):
                logger.warning(f"  警告：要精修{len(bakVary)}个背景参数，但只有{len(X)}个点")

            # 调用 DoPeakFit 执行拟合
            controls = gpx.data['Controls']['data']
            try:
                G2pwd.DoPeakFit('LSQ', [], bkgDict, limits, inst, inst2,
                               np.array((xdata, ydata, W, Z, Z, Z)), None,
                               prevVaryList=bakVary, controls=controls)
            except Exception as e:
                logger.warning(f"  DoPeakFit 拟合失败: {e}")

            # 拟合后重新计算并写回背景到数据通道
            bakType, bakDict, bakVary = G2pwd.SetBackgroundParms(bkgDict)
            # 收集仪器参数值
            insDict = {k: inst[k][1] for k in inst}
            parmDict = {}
            parmDict.update(bakDict)
            parmDict.update(insDict)
            dataType = inst['Type'][0]
            # 计算整个数据范围的背景值并直接写回项目数据结构，确保持久化
            try:
                full_bkg = G2pwd.getBackground('', parmDict, bakType, dataType, gpx.data[hist.name]['data'][1][0], None)[0]
            except Exception:
                full_bkg = bkgdata

            try:
                # 直接写入到项目数据结构（避免局部副本问题）
                mask = ma.getmaskarray(gpx.data[hist.name]['data'][1][1]) if hasattr(gpx.data[hist.name]['data'][1][1], 'mask') else None
                gpx.data[hist.name]['data'][1][4] = ma.MaskedArray(full_bkg, mask=mask)
            except Exception:
                try:
                    gpx.data[hist.name]['data'][1][4] = full_bkg
                except Exception:
                    logger.warning('  无法写回背景到数据通道')

            # 按照 UI 的 addAutoBack 行为：克隆一个新的直方图作为背景文件并设置为 background PWDR
            try:
                base = hist.name[5:] if hasattr(hist, 'name') and hist.name.startswith('PWDR ') else (hist.name if hasattr(hist, 'name') else str(hist))
                newbase = f"Autobkg for {base}"
                newhist = gpx.clone_powder_histogram(hist.name if hasattr(hist, 'name') else hist, newbase, full_bkg)

                # clone_powder_histogram 返回的是 histogram 对象，获取其名称
                clone_name = newhist.name if hasattr(newhist, 'name') else str(newhist)

                # 将新直方图设为当前 histogram 的 background PWDR（写入完整名称）
                bg = gpx.data[hist.name]['Background']
                # clone hist 名通常以 'PWDR ' 前缀存在，确保写入该格式
                if not clone_name.startswith('PWDR '):
                    clone_name = 'PWDR ' + clone_name
                bg[1]['background PWDR'] = [clone_name, 1.0, False]

                # 关闭 computed 标志并清零系数
                try:
                    bg[0][1] = False
                    ncoeff = int(bg[0][2]) if len(bg[0]) > 2 else 0
                    if ncoeff > 0:
                        while len(bg[0]) < 3 + ncoeff:
                            bg[0].append(0.0)
                        bg[0][3:3 + ncoeff] = [0.0] * ncoeff
                except Exception:
                    pass

            except Exception as e:
                logger.warning(f"  无法创建背景直方图并设置 background PWDR: {e}")

        # 保存项目并执行一次空精修以提交更改
        try:
            gpx.save()
        except Exception:
            pass

        logger.info("  ✓ 背景拟合并写回完成")
    except Exception as e:
        logger.error(f"背景拟合流程遇到问题: {e}")

    # 步骤8：执行一次空的精修以计算统计量并持久化
    logger.info("步骤 8/8: 执行一次空精修以提交背景更改")
    try:
        gpx.do_refinements([{}])
        try:
            rwp_now = hist.get_wR()
            if rwp_now is not None:
                logger.info(f"  ✓ 空精修完成，当前Rwp: {rwp_now:.2f}%")
        except Exception:
            logger.info("  ✓ 空精修完成")
    except Exception as e:
        logger.warning(f"空精修执行失败: {str(e)}")

    logger.info("✓ 初始化计算完成")
    logger.info("\n" + "="*50)
    logger.info("项目初始化全部完成!")
    logger.info("="*50 + "\n")

    return gpx, [hist], phases

def flexible_neutron_refinement(gpx, hist, phases, output_dir, gpx_file='', refine_idx=0,refine_config=None, use_constraints=False):
    """
    灵活的中子精修函数 - 一次性精修所有启用的参数

    参数:
    gpx: GSAS-II项目对象
    hist: 历史数据对象
    phases: 相列表
    output_dir: 输出目录
    refine_config: 精修配置字典，支持以下参数:
        {
            # 基础参数
            'refine_background': True,           # 背景精修
            'background_coeffs': 3,              # 背景系数数量
            'refine_cell': True,                 # 晶胞参数精修
            'refine_scale': True,                # 标度因子精修
            'refine_absorption': False,          # 吸收参数精修

            # 仪器参数 (可以整体或单独控制)
            'refine_instrument': True,           # 整体仪器参数精修
            'refine_instrument_difc': False,     # difC
            'refine_instrument_difa': False,     # difA
            'refine_instrument_difb': False,     # difB
            'refine_instrument_zero': False,     # Zero
            'refine_instrument_alpha': False,    # alpha
            'refine_instrument_beta': False,     # beta-0, beta-1, beta-q
            'refine_instrument_sig': False,      # sig-0, sig-1, sig-2, sig-q
            'refine_instrument_x': False,        # X
            'refine_instrument_y': False,        # Y
            'refine_instrument_z': False,        # Z

            # 原子参数 (可以灵活控制)
            'refine_atoms': {},               # 要精修的原子标签字典，'all'表示所有原子
                                              # 例如: {'Fe1':'XU' , 'O2': 'XUF'}或{'all': 'XU'}
            'initial_atom_uiso': None,        # 原子热无序因子初始值：支持按原子设置
                                              # 格式: {'Fe1': 0.05, 'O2': 0.03} 或 [0.05, 0.03] 或单个值

            # 高级参数
            'refine_limits': False,              # Limits精修
            'refine_sample_displacement': False, # 样品位移
            'refine_size': False,                # 晶粒尺寸
            'refine_mustrain': False,            # 微应变
            'refine_phase_fraction': False,      # 相分数
        }
    use_constraints: 是否使用约束
    """
    logger = logging.getLogger(__name__)
    logger.info("开始一次性精修流程...")

    # 默认精修配置（全部禁用）
    default_config = {
        # 基础参数
        'refine_background': False,
        'background_coeffs': 3,
        'refine_cell': False,
        'refine_scale': False,
        'refine_absorption': False,

        # 仪器参数
        'refine_instrument': False,
        'refine_instrument_difc': False,
        'refine_instrument_difa': False,
        'refine_instrument_difb': False,
        'refine_instrument_zero': False,
        'refine_instrument_alpha': False,
        'refine_instrument_beta': False,
        'refine_instrument_sig': False,
        'refine_instrument_x': False,
        'refine_instrument_y': False,
        'refine_instrument_z': False,

        # 原子参数
        'refine_atoms': {},
        'initial_atom_uiso': None,  # 原子热无序因子初始值

        # 高级参数
        'refine_limits': False,
        'refine_sample_displacement': False,
        'refine_size': False,
        'refine_mustrain': False,
        'initial_mustrain': None,  # 微应变初始值：支持 'isotropic'模式
        'refine_phase_fraction': False,
    }

    # 使用用户定义的配置或默认配置
    if refine_config is None:
        refine_config = default_config
        logger.info("使用默认精修配置（全部禁用）")
    else:
        # 合并配置，确保所有键都存在
        for key in default_config:
            if key not in refine_config:
                refine_config[key] = default_config[key]
        logger.info("使用自定义精修配置")

    # 记录启用的精修参数
    enabled_refinements = [key for key, value in refine_config.items() if value and isinstance(value, bool)]
    logger.info(f"启用的精修参数: {enabled_refinements}")

    # 如果用户提供初始晶胞参数(initial_cell)，在执行任何晶胞精修前写入 phase
    # 支持格式：列表（按相索引）或字典（按相名或索引键）
    if refine_config.get('initial_cell'):
        logger.info('检测到 initial_cell 配置，尝试写入各相的初始晶胞参数')
        init_cells = refine_config.get('initial_cell')
        import math
        for i, phase in enumerate(phases):
            cell_vals = None
            # 列表或元组形式
            if isinstance(init_cells, (list, tuple)):
                if i < len(init_cells):
                    cell_vals = init_cells[i]
            elif isinstance(init_cells, dict):
                # 支持相名或索引键
                if hasattr(phase, 'name') and phase.name in init_cells:
                    cell_vals = init_cells[phase.name]
                elif i in init_cells:
                    cell_vals = init_cells[i]
                elif str(i) in init_cells:
                    cell_vals = init_cells[str(i)]

            if cell_vals is None:
                continue

            # 允许直接传入列表/元组 [a,b,c,alpha,beta,gamma]
            try:
                if isinstance(cell_vals, (list, tuple)) and len(cell_vals) >= 6:
                    a, b, c, alpha, beta, gamma = [float(x) for x in cell_vals[:6]]
                elif isinstance(cell_vals, dict):
                    a = float(cell_vals.get('length_a', cell_vals.get('a', cell_vals.get('A'))))
                    b = float(cell_vals.get('length_b', cell_vals.get('b', cell_vals.get('B'))))
                    c = float(cell_vals.get('length_c', cell_vals.get('c', cell_vals.get('C'))))
                    alpha = float(cell_vals.get('angle_alpha', cell_vals.get('alpha', 90.0)))
                    beta = float(cell_vals.get('angle_beta', cell_vals.get('beta', 90.0)))
                    gamma = float(cell_vals.get('angle_gamma', cell_vals.get('gamma', 90.0)))
                else:
                    logger.warning(f"initial_cell: 无法解析相{i}的格式: {type(cell_vals)}")
                    continue
            except Exception as e:
                logger.warning(f"解析 initial_cell 第{i}项失败: {e}")
                continue

            # 计算体积（实空间）并写回 phase.data['General']['Cell']，保留原有 refine flag 如果存在
            try:
                ra, rb, rg = math.radians(alpha), math.radians(beta), math.radians(gamma)
                cosA, cosB, cosG = math.cos(ra), math.cos(rb), math.cos(rg)
                vol = a * b * c * math.sqrt(max(0.0, 1.0 - cosA*cosA - cosB*cosB - cosG*cosG + 2*cosA*cosB*cosG))
            except Exception:
                vol = None

            try:
                old_cell = phase.data.get('General', {}).get('Cell')
                refine_flag = False
                if isinstance(old_cell, (list, tuple)) and len(old_cell) > 0:
                    refine_flag = bool(old_cell[0])

                # 按 GSAS-II 内部格式写入: [refine_flag, a,b,c,alpha,beta,gamma, volume]
                new_cell = [refine_flag, a, b, c, alpha, beta, gamma]
                if vol is not None:
                    new_cell.append(vol)
                phase.data.setdefault('General', {})['Cell'] = new_cell
                logger.info(f"为相{i}写入初始晶胞: {new_cell}")

                # 如果配置启用了晶胞精修，确保设置相的精修标志
                if refine_config.get('refine_cell', False):
                    try:
                        phase.set_refinements({"Cell": True})
                        logger.info(f"为相{i}启用晶胞精修标志")
                    except Exception:
                        logger.debug(f"相{i}不支持 set_refinements 或设置失败，已写入数据结构但未设置标志")

            except Exception as e:
                logger.warning(f"写入相{i}初始晶胞失败: {e}")

    # 如果用户提供初始原子热无序因子(initial_atom_uiso)，在执行任何精修前写入各相的原子
    # 支持格式：字典（按原子标签或相-原子标签）、列表（按相索引）或单个数值
    if refine_config.get('initial_atom_uiso') is not None:
        logger.info('检测到 initial_atom_uiso 配置，尝试写入各相的原子热无序因子')
        init_atom_uiso = refine_config.get('initial_atom_uiso')
        
        for phase_idx, phase in enumerate(phases):
            # 获取该相的原子列表
            if 'Atoms' not in phase.data:
                logger.warning(f"  相{phase_idx}中不存在Atoms数据")
                continue
            
            atoms = phase.data['Atoms']
            if not atoms:
                logger.warning(f"  相{phase_idx}中没有原子")
                continue
            
            # 遍历该相中的所有原子
            for atom_idx, atom_data in enumerate(atoms):
                if not isinstance(atom_data, list) or len(atom_data) < 11:
                    logger.warning(f"  相{phase_idx}的原子{atom_idx}数据格式不正确，跳过")
                    continue
                
                # 获取原子标签 (atom_data[1])
                atom_label = atom_data[1]
                uiso_val = None
                
                # 根据不同的输入格式解析Uiso值
                if isinstance(init_atom_uiso, dict):
                    # 字典格式：支持相-原子标签、原子标签、相索引-原子标签等形式
                    # 优先级：精确原子标签 > 相索引+原子标签 > 全局值
                    
                    # 尝试精确原子标签匹配
                    if atom_label in init_atom_uiso:
                        uiso_val = init_atom_uiso[atom_label]
                    # 尝试相索引+原子标签组合
                    elif f"{phase_idx}:{atom_label}" in init_atom_uiso:
                        uiso_val = init_atom_uiso[f"{phase_idx}:{atom_label}"]
                    # 尝试相名+原子标签组合
                    elif hasattr(phase, 'name'):
                        key = f"{phase.name}:{atom_label}"
                        if key in init_atom_uiso:
                            uiso_val = init_atom_uiso[key]
                    
                elif isinstance(init_atom_uiso, (list, tuple)):
                    # 列表格式：按相索引和原子索引访问
                    if phase_idx < len(init_atom_uiso):
                        phase_uiso = init_atom_uiso[phase_idx]
                        if isinstance(phase_uiso, (list, tuple)):
                            if atom_idx < len(phase_uiso):
                                uiso_val = phase_uiso[atom_idx]
                        elif isinstance(phase_uiso, dict):
                            if atom_label in phase_uiso:
                                uiso_val = phase_uiso[atom_label]
                        else:
                            # 单个值应用于该相的所有原子
                            uiso_val = phase_uiso
                else:
                    # 单个数值：应用于所有原子
                    uiso_val = init_atom_uiso
                
                # 设置Uiso值
                if uiso_val is not None:
                    try:
                        uiso_float = float(uiso_val)
                        # Uiso值在atom_data[10]
                        atom_data[10] = uiso_float
                        logger.info(f"为相{phase_idx}的原子{atom_label}(索引{atom_idx})设置初始Uiso: {uiso_float:.6f}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"为相{phase_idx}的原子{atom_label}设置Uiso失败: 无法将{uiso_val}转换为数值 ({e})")
                    except Exception as e:
                        logger.warning(f"为相{phase_idx}的原子{atom_label}设置Uiso失败: {e}")

    # 如果用户提供初始微应变参数(initial_mustrain)，在执行任何微应变精修前写入
    # 仅支持isotropic模式：单个数值
    if refine_config.get('initial_mustrain') is not None:
        logger.info('检测到 initial_mustrain 配置，尝试写入各相的初始微应变参数')
        init_mustrain = refine_config.get('initial_mustrain')
        
        for i, phase in enumerate(phases):
            mustrain_val = None
            
            # 支持列表或字典形式的初始值
            if isinstance(init_mustrain, (list, tuple)):
                if i < len(init_mustrain):
                    mustrain_val = init_mustrain[i]
            elif isinstance(init_mustrain, dict):
                # 支持相名或索引键
                if hasattr(phase, 'name') and phase.name in init_mustrain:
                    mustrain_val = init_mustrain[phase.name]
                elif i in init_mustrain:
                    mustrain_val = init_mustrain[i]
                elif str(i) in init_mustrain:
                    mustrain_val = init_mustrain[str(i)]
                else:
                    # 如果没有指定具体相，则使用作为全局配置
                    mustrain_val = init_mustrain
            else:
                mustrain_val = init_mustrain

            if mustrain_val is None:
                continue

            try:
                # 转换为浮点数
                mustrain_value = float(mustrain_val)
                
                # 获取该直方图中该相对应的Mustrain数据
                # Mustrain数据位置：phase.data['Histograms'][hist.name]['Mustrain']
                if hist.name not in phase.data.get('Histograms', {}):
                    logger.warning(f"  直方图 {hist.name} 在相{i}中不存在")
                    continue
                
                if 'Mustrain' not in phase.data['Histograms'][hist.name]:
                    logger.warning(f"  直方图 {hist.name} 中的Mustrain数据不存在，跳过")
                    continue
                
                mustrain = phase.data['Histograms'][hist.name]['Mustrain']
                
                # isotropic模式：写入第一个参数值
                # Mustrain结构: [mode, [param_values], [refine_flags], ...]
                mustrain[1][0] = mustrain_value
                logger.info(f"为相{i}设置isotropic微应变初始值: {mustrain_value}")
                
            except (ValueError, TypeError) as e:
                logger.warning(f"写入相{i}初始微应变失败: 无法将{mustrain_val}转换为数值 ({e})")
            except Exception as e:
                logger.warning(f"写入相{i}初始微应变失败: {e}")

    # 构建一次性精修字典
    ref_dict = {"set": {}}

    # 0. 设置最大精修循环次数
    if refine_config.get('refine_cycle', False):
        gpx.data['Controls']['data']['max cyc'] = refine_config['refine_cycle']
        logger.info(f"设置最大精修循环次数: {gpx.data['Controls']['data']['max cyc']}")
    
    # 1. 标度因子精修
    if refine_config.get('refine_scale', False):
        logger.info("添加标度因子到精修字典")
        if "Sample Parameters" not in ref_dict["set"]:
            ref_dict["set"]["Sample Parameters"] = []
        ref_dict["set"]["Sample Parameters"].append("Scale")
    
    # 2. 背景精修
    if refine_config.get('refine_background', False):
        logger.info("添加背景参数到精修字典")
        num_coeffs = refine_config.get('background_coeffs', 3)
        ref_dict["set"]["Background"] = {"no. coeffs": num_coeffs, "refine": True}
        logger.info(f"  背景系数数量: {num_coeffs}")

    # 3. 晶胞参数精修
    if refine_config.get('refine_cell', False):
        logger.info("添加晶胞参数到精修字典")
        # 设置收敛标准
        if use_constraints:
            gpx.data['Controls']['data']['min dM/M'] = 1e-4
        else:
            gpx.data['Controls']['data']['min dM/M'] = 1e-3
        ref_dict["set"]["Cell"] = True

    

    # 4. 仪器参数精修 (支持整体或单独控制)
    instrument_params = []

    # 如果启用整体仪器参数精修
    if refine_config.get('refine_instrument', False):
        logger.info("添加整体仪器参数到精修字典")
        instrument_params.extend([
            "X", "Y",  # 仪器几何参数
            "alpha",   # 角度相关峰宽参数
            "beta-0", "beta-1", "beta-q",  # 各向异性峰形参数
            "sig-0", "sig-1", "sig-2", "sig-q"  # 峰宽分布参数
        ])
    else:
        # 单独控制各个仪器参数
        if refine_config.get('refine_instrument_difc', False):
            instrument_params.append("difC")
            logger.info("  添加 difC")
        if refine_config.get('refine_instrument_difa', False):
            instrument_params.append("difA")
            logger.info("  添加 difA")
        if refine_config.get('refine_instrument_difb', False):
            instrument_params.append("difB")
            logger.info("  添加 difB")
        if refine_config.get('refine_instrument_zero', False):
            instrument_params.append("Zero")
            logger.info("  添加 Zero")
        if refine_config.get('refine_instrument_alpha', False):
            instrument_params.append("alpha")
            logger.info("  添加 alpha")
        if refine_config.get('refine_instrument_beta', False):
            instrument_params.extend(["beta-0", "beta-1", "beta-q"])
            logger.info("  添加 beta参数")
        if refine_config.get('refine_instrument_sig', False):
            instrument_params.extend(["sig-0", "sig-1", "sig-2", "sig-q"])
            logger.info("  添加 sig参数")
        if refine_config.get('refine_instrument_x', False):
            instrument_params.append("X")
            logger.info("  添加 X")
        if refine_config.get('refine_instrument_y', False):
            instrument_params.append("Y")
            logger.info("  添加 Y")
        if refine_config.get('refine_instrument_z', False):
            instrument_params.append("Z")
            logger.info("  添加 Z")

    if instrument_params:
        ref_dict["set"]["Instrument Parameters"] = instrument_params

    # 5. 样品位移参数
    if refine_config.get('refine_sample_displacement', False):
        logger.info("添加样品位移参数到精修字典")
        if "Sample Parameters" not in ref_dict["set"]:
            ref_dict["set"]["Sample Parameters"] = []
        ref_dict["set"]["Sample Parameters"].extend(["DisplaceX", "DisplaceY"])

    # 6. 吸收参数精修
    if refine_config.get('refine_absorption', False):
        logger.info("添加吸收参数到精修字典")
        if "Sample Parameters" not in ref_dict["set"]:
            ref_dict["set"]["Sample Parameters"] = []
        ref_dict["set"]["Sample Parameters"].append("Absorption")

    # 7. 原子参数精修 (支持灵活控制)
    if refine_config.get('refine_atoms', False) and refine_config['refine_atoms']:
        logger.info("添加原子参数到精修字典")
        if 'all' in refine_config['refine_atoms']:
            for phase in phases:
                phase.set_refinements({
                    "Atoms": {
                        "all": refine_config['refine_atoms']['all']  # 例如 "XUF"
                    }
                })
        else:
            for phase in phases:
                phase.set_refinements({
                    "Atoms": refine_config['refine_atoms']  # 例如 {"Fe1": "XU", "O2": "F"}
                })

    # 8. 晶粒尺寸精修
    if refine_config.get('refine_size', False):
        logger.info("添加晶粒尺寸参数到精修字典")
        for phase in phases:
            try:
                # 设置尺寸精修
                phase.set_HAP_refinements({"Size": {"type": "isotropic", "refine": True}}, [hist.name])
            except Exception as e:
                logger.warning(f"  设置尺寸精修失败: {str(e)}")

    # 9. 微应变精修
    if refine_config.get('refine_mustrain', False):
        logger.info("添加微应变参数到精修字典")
        for phase in phases:
            try:
                # 设置微应变精修
                phase.set_HAP_refinements({"Mustrain": {"type": "isotropic", "refine": True}}, [hist.name])
            except Exception as e:
                logger.warning(f"  设置微应变精修失败: {str(e)}")

    # 10. 相分数精修
    if refine_config.get('refine_phase_fraction', False):
        logger.info("添加相分数参数到精修字典")
        for phase in phases:
            try:
                phase.set_HAP_refinements({"Scale": True}, [hist.name])
            except Exception as e:
                logger.warning(f"  设置相分数精修失败: {str(e)}")

    # 检查是否有需要精修的参数
    if not any(refine_config.values()) and not refine_config.get('initial_cell') and not refine_config.get('initial_mustrain'):
        logger.warning("没有启用任何精修参数，跳过精修")
        gpx.save(str(Path(output_dir) / f'neutron_refinement_{refine_idx}.gpx')) #备份这次的结果
        return hist.get_wR(), "没有执行任何精修"

    # 显示最终的ref_dict
    logger.info(f"精修字典: {ref_dict}")
    # 在实际执行精修前，打印/记录所有精修参数及其是否启用，便于对比
    try:
        # 使用 logger 和 print 双重输出，确保在文件日志和控制台都可见
        logger.info("即将执行的精修参数和启用状态:")
        print("即将执行的精修参数和启用状态:")
        # 列出 refine_config 中的键和值
        for key in sorted(refine_config.keys()):
            val = refine_config.get(key)
            logger.info(f"  {key}: {val}")
            print(f"  {key}: {val}")

        # 也打印即将传递给 GSAS-II 的精修字典，便于对比
        logger.info("最终将用于 GSAS-II 的精修字典:")
        print("最终将用于 GSAS-II 的精修字典:")
        logger.info(str(ref_dict))
        print(str(ref_dict))
    except Exception:
        # 不应该阻塞精修流程
        logger.exception("在打印精修参数时发生错误，但将继续执行精修")

    # 执行一次性精修
    try:
        logger.info("开始执行一次性精修...")
        
        # 截获精修过程的输出
        refinement_output = io.StringIO()
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        try:
            sys.stdout = refinement_output
            sys.stderr = refinement_output
            gpx.do_refinements([ref_dict])
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
        
        # 获取捕获的输出
        captured_output = refinement_output.getvalue()
        if captured_output:
            logger.info(f"精修过程输出:\n{captured_output}\n输出结束")
        
        final_rwp = hist.get_wR()
        if final_rwp is not None:
            logger.info(f"精修完成，最终Rwp: {final_rwp:.2f}%")

        # 备份这次结果
        gpx.save(str(Path(output_dir) / f'neutron_refinement_{refine_idx}.gpx'))
        # 手动备份 lst 文件,这么做的原因是GSAS-II会自动保存gpx同名 lst 文件，这恰好是idx-1的名字，所以需要手动备份
        original_lst = Path(output_dir) / os.path.basename(gpx_file).replace('.gpx', '.lst') if gpx_file else Path(output_dir) / 'neutron_refinement.lst'
        backup_lst = Path(output_dir) / f'neutron_refinement_{refine_idx}.lst'
        if original_lst.exists():
            shutil.copy(str(original_lst), str(backup_lst))
            logger.info(f"已备份lst文件到: {backup_lst}")
        else:
            logger.warning(f"未找到lst文件: {original_lst}")

    except Exception as e:
        logger.error(f"精修执行失败: {str(e)}")
        raise

    logger.info("一次性精修流程结束")
    return hist.get_wR(), captured_output

def safe_float(value, default=0.0):
    """安全地将值转换为浮点数"""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            # 移除可能的非数字字符，只保留数字和小数点
            import re
            clean_value = re.sub(r'[^\d.-]', '', value)
            if clean_value:
                return float(clean_value)
            else:
                return default
        else:
            return default
    except (ValueError, TypeError):
        return default

def create_refined_cif(original_cif_path, phase, rwp, output_dir):
    """
    创建精修后的CIF文件，确保为标准CIF格式
    修复原子坐标行的格式问题
    """
    logger = logging.getLogger(__name__)
    
    # 读取原始CIF文件内容
    try:
        with open(original_cif_path, 'r', encoding='utf-8') as f:
            original_content = f.readlines()
    except Exception as e:
        logger.error(f"无法读取原始CIF文件 {original_cif_path}: {str(e)}")
        return None
    
    # 获取精修后的晶胞参数
    cell = phase.get_cell()
    
    # 获取精修后的原子参数
    atoms = phase.data['Atoms']
    
    # 创建新的CIF内容
    new_content = []
    in_atom_site_block = False
    atom_site_started = False
    atom_headers = []
    atom_data_lines = []
    
    # 首先处理原始CIF文件的头部信息
    for line in original_content:
        stripped_line = line.strip()
        
        # 跳过空行和注释
        if not stripped_line or stripped_line.startswith('#'):
            new_content.append(line)
            continue
            
        # 处理晶胞参数
        if stripped_line.startswith('_cell_length_a'):
            new_content.append(f"_cell_length_a                   {cell['length_a']:.6f}\n")
        elif stripped_line.startswith('_cell_length_b'):
            new_content.append(f"_cell_length_b                   {cell['length_b']:.6f}\n")
        elif stripped_line.startswith('_cell_length_c'):
            new_content.append(f"_cell_length_c                   {cell['length_c']:.6f}\n")
        elif stripped_line.startswith('_cell_angle_alpha'):
            new_content.append(f"_cell_angle_alpha                {cell['angle_alpha']:.4f}\n")
        elif stripped_line.startswith('_cell_angle_beta'):
            new_content.append(f"_cell_angle_beta                 {cell['angle_beta']:.4f}\n")
        elif stripped_line.startswith('_cell_angle_gamma'):
            new_content.append(f"_cell_angle_gamma                {cell['angle_gamma']:.4f}\n")
        elif stripped_line.startswith('_cell_volume'):
            new_content.append(f"_cell_volume                     {cell['volume']:.4f}\n")
            
        # 检测原子位点区块开始
        elif 'loop_' in stripped_line and not atom_site_started:
            # 检查下一个行是否是原子位点相关的表头
            next_line_idx = original_content.index(line) + 1
            if next_line_idx < len(original_content):
                next_line = original_content[next_line_idx].strip()
                if next_line.startswith('_atom_site_'):
                    new_content.append(line)
                    in_atom_site_block = True
                else:
                    new_content.append(line)
            else:
                new_content.append(line)
            
        # 检测原子位点表头
        elif stripped_line.startswith('_atom_site_') and in_atom_site_block:
            atom_headers.append(stripped_line)
            new_content.append(line)
            
        # 处理原子位点数据行
        elif in_atom_site_block and not stripped_line.startswith('_') and not stripped_line.startswith('loop_'):
            # 收集原子数据行，稍后处理
            atom_data_lines.append((len(new_content), stripped_line))
            new_content.append(line)  # 先保留原始行
            
        else:
            new_content.append(line)
    
    # 如果有原子数据需要处理，重新构建原子部分
    if atom_data_lines and atom_headers:
        # 确定原子数据行的位置
        first_atom_line_idx = atom_data_lines[0][0]
        
        # 重新构建原子部分
        new_atom_content = []
        
        # 添加标准原子表头
        standard_headers = [
            '_atom_site_type_symbol',
            '_atom_site_label', 
            '_atom_site_fract_x',
            '_atom_site_fract_y', 
            '_atom_site_fract_z',
            '_atom_site_occupancy',
            '_atom_site_U_iso_or_equiv',
            '_atom_site_adp_type'
        ]
        
        # 添加loop_和表头（只添加一次）
        new_atom_content.append("loop_\n")
        for header in standard_headers:
            new_atom_content.append(f"{header}\n")
        
        # 添加精修后的原子数据
        for idx, (line_idx, original_line) in enumerate(atom_data_lines):
            parts = original_line.split()
            if len(parts) >= 1:  # 至少有一个字段（原子符号）
                atom_label = parts[0]
                
                # 查找对应的精修后原子参数
                refined_atom = None
                for atom_data in atoms:
                    if isinstance(atom_data, list) and len(atom_data) >= 8:
                        if atom_data[0] == atom_label or atom_data[1] == atom_label:
                            refined_atom = atom_data
                            break
                
                if refined_atom:
                    # 使用精修后的原子参数，确保格式标准
                    atom_name = refined_atom[0]
                    site_label = refined_atom[1] if len(refined_atom) > 1 else f"{atom_name}{idx+1}"
                    x, y, z = safe_float(refined_atom[3]), safe_float(refined_atom[4]), safe_float(refined_atom[5])
                    occ = safe_float(refined_atom[6], 1.0)
                    uiso = safe_float(refined_atom[7])
                    
                    # 构建标准CIF格式的原子行
                    new_line = f"{atom_name:<6} {site_label:<8} "
                    new_line += f"{x:.5f} {y:.5f} {z:.5f} "
                    new_line += f"{occ:.5f} {uiso:.5f} Uiso\n"
                    
                    new_atom_content.append(new_line)
                else:
                    # 没有找到精修后的参数，尝试解析原始行
                    if len(parts) >= 7:
                        # 假设原始格式：符号 标签 x y z 占位度 Uiso
                        new_line = f"{parts[0]:<6} {parts[1]:<8} "
                        new_line += f"{safe_float(parts[2]):.5f} {safe_float(parts[3]):.5f} {safe_float(parts[4]):.5f} "
                        new_line += f"{safe_float(parts[5], 1.0):.5f} {safe_float(parts[6]):.5f} Uiso\n"
                        new_atom_content.append(new_line)
        
        # 替换原子部分
        final_content = new_content[:first_atom_line_idx] + new_atom_content
        
    else:
        final_content = new_content
    
    # 添加精修信息到文件开头
    refined_content = []
    refined_content.append(f"# CIF文件精修版本 - 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    refined_content.append(f"# 精修程序: GSAS-II中子粉末衍射精修\n")
    refined_content.append(f"# 精修Rwp: {rwp:.2f}%\n")
    refined_content.append(f"# 原始文件: {os.path.basename(original_cif_path)}\n")
    refined_content.append("#\n")
    
    # 添加精修后的内容
    refined_content.extend(final_content)
    
    # 保存精修后的CIF文件
    original_name = os.path.splitext(os.path.basename(original_cif_path))[0]
    refined_cif_path = os.path.join(output_dir, f"{original_name}_gsas_refined.cif")
    
    try:
        with open(refined_cif_path, 'w', encoding='utf-8') as f:
            f.writelines(refined_content)
        
        # 验证生成的CIF文件格式
        try:
            from ase.io import read
            test_atoms = read(refined_cif_path)
            logger.info(f"精修后的CIF文件格式验证成功: {refined_cif_path}")
            
            # 额外验证：检查文件是否包含重复的loop_
            with open(refined_cif_path, 'r') as f:
                content = f.read()
                loop_count = content.count('loop_')
                if loop_count > 1:
                    logger.warning(f"警告：CIF文件中检测到 {loop_count} 个loop_语句，可能存在格式问题")
                else:
                    logger.info("CIF文件格式检查通过，无重复loop_语句")
                    
        except Exception as verify_error:
            logger.warning(f"精修后的CIF文件格式验证失败: {str(verify_error)}")
            logger.warning("文件已保存但可能需要手动调整格式")
        
        return refined_cif_path
        
    except Exception as e:
        logger.error(f"保存精修后的CIF文件失败: {str(e)}")
        return None

def save_structure_parameters(gpx, phases, output_dir):
    """保存结构参数到文件"""
    logger = logging.getLogger(__name__)
    
    for i, phase in enumerate(phases, 1):
        phase_name = f"Phase_{i}"
        
        # 获取晶胞参数
        cell = phase.get_cell()
        logger.info(f"获取到晶胞参数: {cell}")
        
        # 尝试获取ESD，如果失败就跳过
        has_esd = False
        cell_esd = None
        try:
            cell_esd_data = phase.get_cell_and_esd()
            logger.info(f"ESD数据结构: {type(cell_esd_data)}, 长度: {len(cell_esd_data) if hasattr(cell_esd_data, '__len__') else 'N/A'}")
            if len(cell_esd_data) > 1:
                cell_esd = cell_esd_data[1]
                if hasattr(cell_esd, '__getitem__') and len(cell_esd) >= 7:
                    has_esd = True
                    logger.info(f"成功获取ESD: {cell_esd}")
        except Exception as esd_error:
            logger.warning(f"无法获取{phase_name}的ESD值: {str(esd_error)}")
        
        # 获取原子参数
        atoms = phase.data['Atoms']
        logger.info(f"获取到{len(atoms)}个原子")
        
        # 创建结构参数文件
        struct_file = Path(output_dir) / f'{phase_name}_structure_params.txt'
        
        try:
            with open(struct_file, 'w', encoding='utf-8') as f:
                f.write(f"中子精修结构参数 - {phase_name}\n")
                f.write("=" * 50 + "\n\n")
                
                # 晶胞参数
                f.write("晶胞参数:\n")
                if has_esd:
                    f.write(f"a = {cell['length_a']:.6f}({cell_esd['length_a']:.6f}) Å\n")
                    f.write(f"b = {cell['length_b']:.6f}({cell_esd['length_b']:.6f}) Å\n")
                    f.write(f"c = {cell['length_c']:.6f}({cell_esd['length_c']:.6f}) Å\n")
                    f.write(f"α = {cell['angle_alpha']:.4f}({cell_esd['angle_alpha']:.6f})°\n")
                    f.write(f"β = {cell['angle_beta']:.4f}({cell_esd['angle_beta']:.6f})°\n")
                    f.write(f"γ = {cell['angle_gamma']:.4f}({cell_esd['angle_gamma']:.6f})°\n")
                    f.write(f"体积 = {cell['volume']:.4f}({cell_esd['volume']:.6f}) Å³\n\n")
                else:
                    f.write(f"a = {cell['length_a']:.6f} Å\n")
                    f.write(f"b = {cell['length_b']:.6f} Å\n")
                    f.write(f"c = {cell['length_c']:.6f} Å\n")
                    f.write(f"α = {cell['angle_alpha']:.4f}°\n")
                    f.write(f"β = {cell['angle_beta']:.4f}°\n")
                    f.write(f"γ = {cell['angle_gamma']:.4f}°\n")
                    f.write(f"体积 = {cell['volume']:.4f} Å³\n\n")
                
                # 原子参数
                f.write("原子参数:\n")
                f.write("原子名称\t位点\tx\t\ty\t\tz\t\t占有率\t\tUiso/Å²\n")
                f.write("-" * 80 + "\n")
                
                if isinstance(atoms, dict):
                    # 字典格式的原子数据
                    for atom_label, atom_data in atoms.items():
                        if isinstance(atom_data, list) and len(atom_data) >= 8:
                            atom_name = atom_data[0]
                            site = atom_data[1]
                            x, y, z = safe_float(atom_data[3]), safe_float(atom_data[4]), safe_float(atom_data[5])
                            occ = safe_float(atom_data[6], 1.0)
                            uiso = safe_float(atom_data[7])
                            f.write(f"{atom_name}\t{site}\t{x:.5f}\t{y:.5f}\t{z:.5f}\t{occ:.3f}\t\t{uiso:.5f}\n")
                elif isinstance(atoms, list):
                    # 列表格式的原子数据
                    for atom_data in atoms:
                        if isinstance(atom_data, list) and len(atom_data) >= 8:
                            atom_name = atom_data[0]
                            site = atom_data[1]
                            x, y, z = safe_float(atom_data[3]), safe_float(atom_data[4]), safe_float(atom_data[5])
                            occ = safe_float(atom_data[6], 1.0)
                            uiso = safe_float(atom_data[7])
                            f.write(f"{atom_name}\t{site}\t{x:.5f}\t{y:.5f}\t{z:.5f}\t{occ:.3f}\t\t{uiso:.5f}\n")
                
                f.write(f"\n生成时间: {__import__('datetime').datetime.now()}\n")
                
            logger.info(f"结构参数已成功保存到: {struct_file}")
            
        except Exception as save_error:
            logger.error(f"保存结构参数文件时出错: {str(save_error)}")

def print_structure_parameters(phases):
    """打印结构参数到控制台"""
    print("\n" + "=" * 60)
    print("中子精修结构参数总结")
    print("=" * 60)
    
    for i, phase in enumerate(phases, 1):
        print(f"\nPhase {i}:")
        print("-" * 40)
        
        # 晶胞参数
        cell = phase.get_cell()
        try:
            cell_esd_data = phase.get_cell_and_esd()
            # 检查ESD数据结构
            if len(cell_esd_data) > 1 and hasattr(cell_esd_data[1], '__getitem__'):
                cell_esd = cell_esd_data[1]
                has_esd = True
            else:
                has_esd = False
        except:
            has_esd = False
        
        print("晶胞参数:")
        if has_esd:
            try:
                print(f"  a = {cell['length_a']:.6f}({cell_esd['length_a']:.6f}) Å")
                print(f"  b = {cell['length_b']:.6f}({cell_esd['length_b']:.6f}) Å")
                print(f"  c = {cell['length_c']:.6f}({cell_esd['length_c']:.6f}) Å")
                print(f"  α = {cell['angle_alpha']:.4f}({cell_esd['angle_alpha']:.4f})°")
                print(f"  β = {cell['angle_beta']:.4f}({cell_esd['angle_beta']:.4f})°")
                print(f"  γ = {cell['angle_gamma']:.4f}({cell_esd['angle_gamma']:.4f})°")
                print(f"  体积 = {cell['volume']:.4f}({cell_esd['volume']:.4f}) Å³")
            except (KeyError, TypeError):
                has_esd = False
                
        if not has_esd:
            print(f"  a = {cell['length_a']:.6f} Å")
            print(f"  b = {cell['length_b']:.6f} Å")
            print(f"  c = {cell['length_c']:.6f} Å")
            print(f"  α = {cell['angle_alpha']:.4f}°")
            print(f"  β = {cell['angle_beta']:.4f}°")
            print(f"  γ = {cell['angle_gamma']:.4f}°")
            print(f"  体积 = {cell['volume']:.4f} Å³")
        
        # 原子数量统计
        atoms = phase.data['Atoms']  # 直接访问原子数据字典
        print(f"\n原子位点数量: {len(atoms)}")
        
        # 显示前几个原子的信息
        if atoms:
            print("\n主要原子位点:")
            print("  原子\t位点\tx\t\ty\t\tz\t占有率\tUiso")
            count = 0
            
            if isinstance(atoms, dict):
                # 字典格式的原子数据
                for atom_label, atom_data in atoms.items():
                    if isinstance(atom_data, list) and len(atom_data) >= 8 and count < 5:
                        atom_name = atom_data[0]
                        site = atom_data[1]
                        x, y, z = safe_float(atom_data[3]), safe_float(atom_data[4]), safe_float(atom_data[5])
                        occ = safe_float(atom_data[6], 1.0)
                        uiso = safe_float(atom_data[7])
                        print(f"  {atom_name}\t{site}\t{x:.3f}\t{y:.3f}\t{z:.3f}\t{occ:.3f}\t{uiso:.4f}")
                        count += 1
            elif isinstance(atoms, list):
                # 列表格式的原子数据
                for atom_data in atoms:
                    if isinstance(atom_data, list) and len(atom_data) >= 8 and count < 5:
                        atom_name = atom_data[0]
                        site = atom_data[1]
                        x, y, z = safe_float(atom_data[3]), safe_float(atom_data[4]), safe_float(atom_data[5])
                        occ = safe_float(atom_data[6], 1.0)
                        uiso = safe_float(atom_data[7])
                        print(f"  {atom_name}\t{site}\t{x:.3f}\t{y:.3f}\t{z:.3f}\t{occ:.3f}\t{uiso:.4f}")
                        count += 1
            
            if len(atoms) > 5:
                print(f"  ... 还有 {len(atoms) - 5} 个原子位点")

def export_neutron_results(gpx, hist, phases, output_dir, original_cif_files,refine_idx=None):
    """导出中子精修结果"""
    logger = logging.getLogger(__name__)
    
    # 首先验证数据一致性
    print("\n🔍 验证数据一致性...")
    x_data = hist.getdata('x')
    y_obs = hist.getdata('yobs')
    y_calc = hist.getdata('ycalc')
    y_bkg = hist.getdata('background')
    [tofmin, tofmax] = hist.data['Limits'][1]
    
    # 数据统计
    zero_calc = np.sum(y_calc == 0) if hasattr(y_calc, '__len__') else 0
    print(f"  数据点数: {len(x_data)}")
    print(f"  观测强度范围: {y_obs.min():.6f} - {y_obs.max():.6f}")
    print(f"  计算强度范围: {y_calc.min():.6f} - {y_calc.max():.6f}")
    print(f"  背景强度范围: {y_bkg.min():.6f} - {y_bkg.max():.6f}")
    print(f"  计算强度为0的点数: {zero_calc}/{len(y_calc)}")
    
    # 检查数据质量
    if zero_calc > len(y_calc) * 0.5:
        print("  ⚠️  警告：超过50%的计算强度为0，数据可能有问题")
    elif zero_calc > 0:
        print(f"  ℹ️  信息：{zero_calc}个点的计算强度为0，这在某些角度范围是正常的")
    else:
        print("  ✅ 所有数据点都有计算强度")
    
    # 保存详细的数据文件，包含验证信息
    data_file = Path(output_dir) / 'neutron_refinement_data_verified.csv'
    try:
        # 创建包含验证信息的CSV
        with open(data_file, 'w', encoding='utf-8') as f:
            # 写入头部信息
            f.write("# 中子精修数据验证报告\n")
            f.write(f"# 生成时间: {__import__('datetime').datetime.now()}\n")
            f.write(f"# 数据点数: {len(x_data)}\n")
            f.write(f"# 观测强度范围: {y_obs.min():.6f} - {y_obs.max():.6f}\n")
            f.write(f"# 计算强度范围: {y_calc.min():.6f} - {y_calc.max():.6f}\n")
            f.write(f"# 计算强度为0的点数: {zero_calc}/{len(y_calc)}\n")
            current_rwp = hist.get_wR()
            if current_rwp is not None:
                f.write(f"# 当前Rwp: {current_rwp:.2f}%\n")
            f.write("#\n")
            
            # 写入数据表头
            f.write("x,y_obs,y_calc,y_bkg,residual,weight,d_spacing\n")
            
            # 写入数据
            weights = hist.getdata('yweight')
            d_spacing = hist.getdata('d')
            
            for i in range(len(x_data)):
                residual = y_obs[i] - y_calc[i] if y_calc[i] != 0 else 0
                f.write(f"{x_data[i]:.3f},{y_obs[i]:.6f},{y_calc[i]:.6f},{y_bkg[i]:.6f},"
                       f"{residual:.6f},{weights[i]:.2e},{d_spacing[i]:.6f}\n")
        
        logger.info(f"验证数据已保存到: {data_file}")
        
    except Exception as e:
        logger.error(f"保存验证数据时出错: {str(e)}")
    
    # 保存原始格式的数据文件（兼容性）
    try:
        original_data_file = Path(output_dir) / 'neutron_refinement_data.csv'
        hist.Export(str(original_data_file), '.csv', 'hist')
        logger.info(f"原始格式数据已保存到: {original_data_file}")
    except Exception as e:
        logger.warning(f"保存原始格式数据时出错: {str(e)}")
    
    # 生成图表
    plot_path = None  # 初始化plot_path变量，防止后续使用时未定义
    try:    
        plt.figure(figsize=(16, 10))
        
        # 创建子图
        # plt.subplot(2, 1, 1)
        # 更可读的字体与样式设置
        title_fs = 14
        label_fs = 12
        tick_fs = 11
        legend_fs = 11

        # 先计算差值
        diff = y_obs - y_calc
        
        plt.plot(x_data, diff, 'k-', label='Difference (Obs-Calc)', linewidth=1)
        plt.plot(x_data, y_obs, 'b.', label='Observed', markersize=6, alpha=0.8)
        plt.plot(x_data, y_calc, 'r-', label='Calculated', linewidth=3.6)
        plt.plot(x_data, y_bkg, 'g-', label='Background', linewidth=1.2)
        plt.axvline(x=tofmin, color='m', linestyle='--', linewidth=1, label='TOF Min')
        plt.axvline(x=tofmax, color='c', linestyle='--', linewidth=1, label='TOF Max')
        plt.title(f'Neutron Refinement - Rwp: {hist.get_wR():.2f}%', fontsize=title_fs)
        plt.xlabel('Time (μs)', fontsize=label_fs)
        plt.ylabel('Intensity', fontsize=label_fs)
        # 延后显示 legend，以便包含下面绘制的 Bragg 竖线
        plt.grid(True, alpha=0.3)
        ax = plt.gca()
        ax.tick_params(labelsize=tick_fs)
        # 使用 GSAS-II 生成的反射表在图上标注 Bragg 位置（短且下调的竖线）
        try:
            import GSASIIpwd as G2pwd
            import GSASIIlattice as G2lat
            Inst = hist.data['Instrument Parameters'][0]
            try:
                d_spacing = hist.getdata('d')
                dmin = float(np.nanmin(d_spacing)) if hasattr(d_spacing, '__len__') and len(d_spacing) else 0.0
            except Exception:
                dmin = 0.0
            ax = plt.gca()
            y0, y1 = ax.get_ylim()
            yspan = y1 - y0 if (y1 - y0) != 0 else 1.0
            # 将竖线上移（避免太靠下）并适度缩短长度，避免覆盖谱峰
            start = y0 + 0.05 * yspan
            tick_len = 0.02 * yspan
            cmap = plt.cm.get_cmap('tab10')
            # 收集自定义图例句柄（用于竖线样式的 Bragg peaks）
            from matplotlib.lines import Line2D
            bragg_handles = []
            bragg_labels = []
            for ip, phase in enumerate(phases):
                try:
                    SGData = phase.data['General']['SGData']
                    cell = phase.data['General']['Cell'][1:7]
                    A = G2lat.cell2A(cell)
                    hkls = G2pwd.getHKLpeak(dmin, SGData, A, Inst)
                    if hkls is None or len(hkls) == 0:
                        continue
                    col = cmap(ip % 10)
                    # 收集该相所有反射位置，批量绘制以减少 Artist 数量
                    positions = []
                    for hkl in hkls:
                        try:
                            pos = float(hkl[4])
                        except Exception:
                            pos = float(G2lat.Dsp2pos(Inst, hkl[3]))
                        # 仅保留位于当前显示范围内的反射，减少不必要绘制
                        if pos >= tofmin and pos <= tofmax:
                            positions.append(pos)
                    if positions:
                        ax.vlines(positions, start, start + tick_len, color=col, linewidth=1.6, alpha=0.9)
                        # 创建图例句柄（每相一次）
                        phase_name = None
                        try:
                            phase_name = phase.data.get('General', {}).get('Name')
                        except Exception:
                            phase_name = None
                        if not phase_name:
                            phase_name = getattr(phase, 'name', None)
                        if not phase_name:
                            phase_name = f'Phase {ip+1}'
                        handle = Line2D([0], [0], color=col, marker='|', linestyle='None', markersize=12, markeredgewidth=4)
                        bragg_handles.append(handle)
                        bragg_labels.append(f'Bragg peaks ({phase_name})')
                except Exception:
                    continue
            # 在所有竖线绘制完成后再显示 legend，以包含 Bragg peaks 条目
            try:
                # 获取当前默认 legend handles/labels（前面绘制的 obs/calc/bkg/diff/limits）
                cur_handles, cur_labels = ax.get_legend_handles_labels()
                # 将 bragg 的自定义句柄附加到末尾
                if bragg_handles:
                    cur_handles.extend(bragg_handles)
                    cur_labels.extend(bragg_labels)
                # 布局：两列以节省空间，字体更大
                # 放置在图内上方（使用轴坐标），防止跑出外框
                # 将 legend 放到左上角内侧并增大字体，减少对数据的遮挡
                ax.legend(cur_handles, cur_labels, fontsize=15, ncol=1, loc='upper left', bbox_to_anchor=(0.02, 0.98), bbox_transform=ax.transAxes, frameon=True, framealpha=0.95)
            except Exception:
                pass
        except Exception:
            pass
        
        # # 差值图
        # plt.subplot(2, 1, 2)
        # diff = y_obs - y_calc
        # plt.plot(x_data, diff, 'k-', label='Difference (Obs-Calc)', linewidth=1)
        # plt.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
        # plt.xlabel('Time (μs)')
        # plt.ylabel('Difference')
        # plt.legend()
        # plt.grid(True, alpha=0.3)
        
        plt.tight_layout(pad=2.0)
        id = os.path.basename(os.path.normpath(output_dir)).split('gsas_output_')[-1] if 'gsas_output_' in output_dir else None
        if refine_idx is not None:
            plot_path = Path(output_dir) / f'{id}_plot_{refine_idx}.png'
        else:
            plot_path = Path(output_dir) / f'{id}_plot_verified.png'
        plt.savefig(str(plot_path), dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"验证图表已保存到: {plot_path}")
        
    except ImportError:
        logger.warning("matplotlib不可用，跳过图表生成")
    except Exception as e:
        logger.error(f"生成图表时出错: {str(e)}")
    
    # 保存详细结构参数
    save_structure_parameters(gpx, phases, output_dir)
    
    # 创建精修后的CIF文件
    logger.info(f"original_cif_files: {original_cif_files}")
    logger.info(f"len of phases: {len(phases)}")
    refined_cif_files = []
    for i, phase in enumerate(phases):
        if i < len(original_cif_files):
            original_cif = original_cif_files[i]
            refined_cif = create_refined_cif(original_cif, phase, hist.get_wR(), output_dir)
            if refined_cif:
                refined_cif_files.append(refined_cif)
    
    # 收集所有生成的文件
    output_files = []
    if data_file.exists():
        output_files.append(str(data_file))
    
    # 添加其他可能的输出文件
    for i in range(len(phases)):
        phase_name = f"Phase_{i+1}"
        struct_file = Path(output_dir) / f'{phase_name}_structure_params.txt'
        if struct_file.exists():
            output_files.append(str(struct_file))
    
    # 添加精修后的CIF文件
    output_files.extend(refined_cif_files)
    
    # 收集结果
    current_rwp = hist.get_wR()
    results = {
        'rwp': current_rwp if current_rwp is not None else 0.0,
        'cell_params': [phase.get_cell() for phase in phases],
        'output_files': output_files,
        'plot_path': str(plot_path) if plot_path is not None else '',
        'refined_cif_files': refined_cif_files,
        'data_quality': {
            'total_points': len(x_data),
            'zero_calc_points': int(zero_calc),
            'calc_range': [float(y_calc.min()), float(y_calc.max())],
            'obs_range': [float(y_obs.min()), float(y_obs.max())]
        }
    }
    
    return results

def ensure_fixed_background(gpx, hist, logger=None):
    """如果 histogram 的 Background 包含 FixedPoints，则用线性插值写回 data[1][4]，
    并克隆为一个新的 PWDR histogram，设置为 background PWDR。
    此操作直接修改 gpx.data 并保存由调用方控制何时写入磁盘。
    """
    try:
        import numpy as _np
        import numpy.ma as _ma
    except Exception:
        return

    try:
        histname = hist.name if hasattr(hist, 'name') else str(hist)
        bg = gpx.data[histname]['Background']
        fixed = bg[1].get('FixedPoints')
        if not fixed:
            return

        # 插值 FixedPoints 到原始 x 网格
        X = _np.array([pt[0] for pt in fixed])
        Y = _np.array([pt[1] for pt in fixed])
        order = _np.argsort(X)
        X = X[order]; Y = Y[order]
        xgrid = _np.array(gpx.data[histname]['data'][1][0])
        full_bkg = _np.interp(xgrid, X, Y, left=Y[0], right=Y[-1])

        # 写回背景通道（使用MaskedArray以保留mask）
        try:
            mask = _ma.getmaskarray(gpx.data[histname]['data'][1][1]) if hasattr(gpx.data[histname]['data'][1][1], 'mask') else None
            gpx.data[histname]['data'][1][4] = _ma.MaskedArray(full_bkg, mask=mask)
        except Exception:
            try:
                gpx.data[histname]['data'][1][4] = full_bkg.tolist()
            except Exception:
                if logger:
                    logger.warning('无法将 full_bkg 写回 data channel 4')

        # 克隆新直方图并设置 background PWDR
        try:
            base = histname[5:] if histname.startswith('PWDR ') else histname
            newbase = f"Autobkg for {base}"
            newhist = gpx.clone_powder_histogram(histname, newbase, full_bkg)
            clone_name = newhist.name if hasattr(newhist, 'name') else str(newhist)
            if not clone_name.startswith('PWDR '):
                clone_name = 'PWDR ' + clone_name
            bg[1]['background PWDR'] = [clone_name, 1.0, False]
            # 关闭 computed 标志并清零系数（如有）
            try:
                bg[0][1] = False
                ncoeff = int(bg[0][2]) if len(bg[0]) > 2 else 0
                if ncoeff > 0:
                    while len(bg[0]) < 3 + ncoeff:
                        bg[0].append(0.0)
                    bg[0][3:3 + ncoeff] = [0.0] * ncoeff
            except Exception:
                pass
        except Exception as e:
            if logger:
                logger.warning(f'克隆背景直方图失败: {e}')
    except Exception as e:
        if logger:
            logger.warning(f'ensure_fixed_background 出错: {e}')
    return

def neutron_refinement(
    neutron_data=None,
    neutron_inst=None,
    cif_files=None,
    output_dir='neutron_output',
    # 基础参数 (简单模式,向后兼容)
    refine_cycle=3,                # 精修循环次数
    refine_background=False,       # True/False
    refine_cell=False,             # True/False
    refine_scale=False,            # True/False
    refine_instrument=False,       # True/False
    refine_absorption=False,       # True/False
    refine_atoms={},               # 要精修的原子标签字典, 例如: {'Fe1':'XU' , 'O2': 'XUF'}或{'all': 'XU'}
    use_constraints=False,          # 是否使用约束
    gpx_file=None,                 # 可选的已有gpx项目文件路径
    refine_idx=0,                    # 精修索引 (用于多次精修保存不同文件)
    # 高级参数 (可选,用于精细控制)
    advanced_config=None,          # 高级配置字典,支持所有GSAS-II精修参数
    que=multiprocessing.Queue()
):
    """
    中子粉末衍射数据精修主函数 - 支持所有GSAS-II精修参数

    参数:
    neutron_data: 中子数据文件路径 (当gpx_file为None时必需)
    neutron_inst: 仪器参数文件路径 (当gpx_file为None时必需)
    cif_files: CIF结构文件列表 (当gpx_file为None时必需)
    output_dir: 输出目录

    基础参数 (简单模式):
    refine_background: True/False - 是否精修背景
    refine_cell: True/False - 是否精修晶胞参数
    refine_scale: True/False - 是否精修标度因子
    refine_instrument: True/False - 是否精修仪器参数(整体)
    refine_absorption: True/False - 是否精修吸收参数
    refine_atoms: dict - 要精修的原子标签字典, 例如: {'Fe1':'XU' , 'O2': 'XUF'}或{'all': 'XU'}
    use_constraints: 是否使用约束
    gpx_file: 可选,已有的GSAS-II项目文件(.gpx)路径,如果提供则加载现有项目继续精修

    高级参数 (高级模式,提供更精细的控制):
    advanced_config: 字典,包含所有可用的精修参数,例如:
        {
            # 基础参数
            'background_coeffs': 3,              # 背景系数数量

            # 仪器参数 (单独控制)
            'refine_instrument_difc': True,      # difC
            'refine_instrument_difa': True,      # difA
            'refine_instrument_difb': True,      # difB
            'refine_instrument_zero': True,      # Zero
            'refine_instrument_alpha': True,     # alpha
            'refine_instrument_beta': True,      # beta-0, beta-1, beta-q
            'refine_instrument_sig': True,       # sig-0, sig-1, sig-2, sig-q
            'refine_instrument_x': True,         # X
            'refine_instrument_y': True,         # Y
            'refine_instrument_z': True,         # Z

            # 原子参数 (单独控制)
            'refine_atoms': {},            # dict - 要精修的原子标签字典, 例如: {'Fe1':'XU' , 'O2': 'XUF'}或{'all': 'XU'}

            # 高级参数
            'refine_limits': True,               # Limits精修
            'refine_sample_displacement': True,  # 样品位移
            'refine_size': True,                 # 晶粒尺寸
            'refine_mustrain': True,             # 微应变
            'refine_phase_fraction': True,       # 相分数
        }

    que: 多进程队列

    注意:
    - 如果提供了 advanced_config,它会覆盖基础参数
    - 基础参数适合快速使用,高级参数适合精细控制
    """
    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 设置日志
    logger = setup_logging(output_dir)
    logger.info("="*50)
    logger.info("开始中子粉末衍射精修")
    logger.info("="*50)

    # 构建精修配置字典
    if advanced_config:
        # 使用高级配置
        logger.info("使用高级配置模式")
        refine_config = advanced_config.copy()
        # 确保基础参数也在配置中
        if 'refine_cycle' not in refine_config:
            refine_config['refine_cycle'] = refine_cycle
        if 'refine_background' not in refine_config:
            refine_config['refine_background'] = refine_background
        if 'refine_cell' not in refine_config:
            refine_config['refine_cell'] = refine_cell
        if 'refine_scale' not in refine_config:
            refine_config['refine_scale'] = refine_scale
        if 'refine_instrument' not in refine_config:
            refine_config['refine_instrument'] = refine_instrument
        if 'refine_absorption' not in refine_config:
            refine_config['refine_absorption'] = refine_absorption
        if 'refine_atoms' not in refine_config:
            refine_config['refine_atoms'] = refine_atoms
    else:
        # 使用基础配置(向后兼容)
        logger.info("使用基础配置模式")
        refine_config = {
            'refine_cycle': refine_cycle,
            'refine_background': refine_background,
            'refine_cell': refine_cell,
            'refine_scale': refine_scale,
            'refine_instrument': refine_instrument,
            'refine_absorption': refine_absorption,
            'refine_atoms': refine_atoms,
        }

    import pprint
    logger.info("精修配置 (展开):\n" + pprint.pformat(refine_config, width=120))

    try:
        # 1. 加载或初始化项目
        if gpx_file and os.path.exists(gpx_file):
            # 使用用户提供的gpx文件
            logger.info(f"📂 加载现有GSAS-II项目: {gpx_file}")
            gpx = G2sc.G2Project(gpxfile=gpx_file)
            # 在对原始 gpx 操作前先保存一份备份，以便在需要时回退
            backup_path = None
            try:
                if gpx_file:
                    bk = Path(gpx_file)
                    backup_path = str(bk.with_name(bk.stem + '_pre_refine' + bk.suffix))
                    shutil.copy2(gpx_file, backup_path)
                    logger.info(f"已备份原始 gpx 到: {backup_path}")
            except Exception as e:
                logger.warning(f"无法创建 gpx 备份: {e}")
            

            # 获取项目中的histogram和phases
            hists = gpx.histograms()
            phases = gpx.phases()

            if not hists:
                raise ValueError("GPX项目中未找到任何histogram数据")
            if not phases:
                raise ValueError("GPX项目中未找到任何晶体结构")

            hist = hists[0]  # 使用第一个histogram
            logger.info(f"  ✓ 成功加载项目")
            logger.info(f"  - Histogram数量: {len(hists)}")
            logger.info(f"  - Phase数量: {len(phases)}")
            logger.info(f"  - 使用Histogram: {hist.name}")

            # 保存原始cif文件路径(用于后续导出)
            original_cif_files = cif_files if cif_files else []

        else:
            # 初始化新项目
            if gpx_file:
                logger.warning(f"⚠️  指定的gpx文件不存在: {gpx_file}")
                logger.info("  将创建新项目")
            else:
                logger.info("🆕 创建新的GSAS-II项目")

            # 验证必需参数
            if not (neutron_data and neutron_inst and cif_files):
                raise ValueError("创建新项目时必须提供 neutron_data, neutron_inst 和 cif_files 参数")

            logger.info(f"  中子数据: {neutron_data}")
            logger.info(f"  仪器参数: {neutron_inst}")
            logger.info(f"  结构文件: {len(cif_files)}个")

            gpx, hists, phases = initialize_project(
                neutron_data, neutron_inst, cif_files, output_dir
            )
            hist = hists[0]  # 只有中子数据
            ensure_fixed_background(gpx, hist, logger=logger)

            original_cif_files = cif_files

         # 2. 执行一次性精修流程
        logger.info("开始一次性精修流程...")
        _, refinement_log = flexible_neutron_refinement(
            gpx, hist, phases, output_dir,
            gpx_file=gpx_file,
            refine_idx=refine_idx,
            refine_config=refine_config,
            use_constraints=use_constraints
        )
        
        # 3. 导出结果
        try:
            results = export_neutron_results(gpx, hist, phases, output_dir, original_cif_files,refine_idx=refine_idx)
            results['refinement_log'] = refinement_log
        except Exception as e:
            logger.warning(f"导出结果时遇到问题: {str(e)}")
            # 创建基本结果，确保能显示精修参数
            results = {
                'rwp': hist.get_wR() if hist else 0.0,
                'cell_params': [phase.get_cell() for phase in phases],
                'output_files': [],
                'refined_cif_files': [],
                'refinement_log': refinement_log
            }
        
        # 4. 打印结构参数到控制台
        print_structure_parameters(phases)
        
        logger.info("="*50)
        logger.info(f"精修完成! 最终Rwp: {results['rwp']:.2f}%")
        if results['refined_cif_files']:
            logger.info(f"生成的精修CIF文件: {', '.join(results['refined_cif_files'])}")
        logger.info("="*50)
        # 精修完成后：如果存在备份，则将原始 gpx 恢复为备份文件（替换当前 gpx）
        try:
            if 'backup_path' in locals() and backup_path and gpx_file and os.path.exists(backup_path):
                shutil.copy2(backup_path, gpx_file)
                logger.info(f"已将 gpx 恢复为备份: {backup_path} -> {gpx_file}")
        except Exception as e:
            logger.warning(f"恢复 gpx 备份失败: {e}")
        que.put(results)
        return results

    except Exception as e:
        logger.error("!"*50)
        logger.error(f"精修失败: {str(e)}")
        logger.error("!"*50)
        que.put({
            'status': 'error',
            'error': str(e),
            'traceback': traceback.format_exc()
        })
        raise


id_to_task={}
id_to_result={}

@mcp.tool()
def write_info(
    gsa_path: str = None,
    instprm_path: str = None,
    cif_paths: List[str] = None,
    gpx_path: str = None,                 # 可选的已有gpx项目文件路径
    refine_idx: int = 0,                 # 精修轮次索引
    refine_params: Dict = None,            # 高级配置字典
    refine_background: bool = False,      # True/False - 是否精修背景
    refine_cell: bool = False,            # True/False - 是否精修晶胞参数
    refine_scale: bool = False,           # True/False - 是否精修标度因子
    refine_instrument: bool = False,      # True/False - 是否精修仪器参数
    refine_absorption: bool = False,      # True/False - 是否精修吸收参数
    refine_atoms: dict = {},              # 要精修的原子标签字典, 例如: {'Fe1':'XU' , 'O2': 'XUF'}或{'all': 'XU'}
    use_constraints: bool = False,         # 是否使用约束
    task_id: str|None = None,
    thread_id: str|None = None,
    ) -> Dict:
    """
    使用GSAS-II的API接口进行中子衍射数据精修任务并返回结果信息
    Args:
        gsa_file: GSAS的gsa文件绝对路径 (当gpx_file为None时必需)
        instprm_file: GSAS的instprm文件绝对路径 (当gpx_file为None时必需)
        cif_files: 结构文件列表 (当gpx_file为None时必需)
        gpx_file: 可选,已有的GSAS-II项目文件(.gpx)路径,如果提供则加载现有项目继续精修
        refine_idx: 精修轮次索引，默认0
        refine_config: 高级配置字典,支持所有GSAS-II精修参数，
        refine_background: True/False - 是否精修背景
        refine_cell: True/False - 是否精修晶胞参数
        refine_scale: True/False - 是否精修标度因子
        refine_instrument: True/False - 是否精修仪器参数
        refine_absorption: True/False - 是否精修吸收参数
        refine_atoms: dict = {},              # 要精修的原子标签字典, 例如: {'Fe1':'XU' , 'O2': 'XUF'}或{'all': 'XU'}
        use_constraints: 是否使用约束
        task_id: 任务ID，默认自动生成
        thread_id: 线程ID，默认自动生成
    """
    id_=task_id
    result_json={"id":id_,'state':None,'result':None}

    # 规范化并记录 refine_params，防止字符串/数字类型导致布尔字段丢失
    import pprint
    logger = logging.getLogger(__name__)
    if refine_params is None:
        refine_params = {}
    try:
        logger.info("收到的 refine_params (原始):\n" + pprint.pformat(refine_params, width=120))
    except Exception:
        logger.info(f"收到的 refine_params: {str(refine_params)}")

    bool_keys = [
        'refine_background','refine_cell','refine_scale','refine_instrument',
        'refine_absorption','refine_size','refine_mustrain','refine_phase_fraction',
        'refine_limits','refine_sample_displacement',
        'refine_instrument_difc','refine_instrument_difa','refine_instrument_difb',
        'refine_instrument_zero','refine_instrument_alpha','refine_instrument_beta',
        'refine_instrument_sig','refine_instrument_x','refine_instrument_y','refine_instrument_z'
    ]

    def to_bool(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            vs = v.strip().lower()
            if vs in ('true','1','yes','y'):
                return True
            if vs in ('false','0','no','n'):
                return False
        return v

    refine_params_norm = {}
    for k, v in refine_params.items():
        if k in bool_keys:
            refine_params_norm[k] = to_bool(v)
        else:
            refine_params_norm[k] = v

    # 根据是否提供gpx_file来确定输出目录
    if gpx_path:
        # 如果提供了gpx文件,输出目录基于gpx文件的位置
        output_dir = os.path.dirname(gpx_path)
    else:
        # 否则基于gsa文件的位置
        output_dir = os.path.join(os.path.dirname(gsa_path), f"output/{thread_id}/gsas_output_{task_id}")

    if id_ not in id_to_task or id_to_task[id_]==None:
        # 任务创建
        id_to_result[id_]=multiprocessing.Queue()
        id_to_task[id_]=multiprocessing.Process(target=neutron_refinement,kwargs={
                    'output_dir': output_dir,
                    'neutron_data': gsa_path,
                    'neutron_inst': instprm_path,
                    'cif_files': cif_paths,
                    'gpx_file': gpx_path,
                    'refine_idx': refine_idx,
                'advanced_config': refine_params_norm,
                    'refine_background': refine_background,
                    'refine_cell': refine_cell,
                    'refine_scale': refine_scale,
                    'refine_instrument': refine_instrument,
                    'refine_absorption': refine_absorption,
                    'refine_atoms': refine_atoms,
                    'use_constraints': use_constraints,
                    'que': id_to_result[id_]
                }
        )

        result_json['state']='created'
        id_to_task[id_].start()
        # id_to_task[id_].kill()
        # id_to_task.pop(id_)

    else:
        if not id_to_task[id_].is_alive():
            info=id_to_result[id_].get()
            id_to_task[id_].join()
            if (not info) or (isinstance(info, dict) and info.get('status') == 'error'):
                error_msg = info.get('error') if isinstance(info, dict) else "中子精修处理失败"
                traceback_msg = info.get('traceback') if isinstance(info, dict) else None

                result_json['state'] = 'completed'
                result_json['status'] = 'error'
                result_json['result'] = {
                    "status": "error",
                    "error": error_msg,
                    "traceback": traceback_msg,
                    "suggestion": "请检查输入文件格式、仪器参数或结构文件是否正确"
                }
                result_json["summary"] = f"GSAS-II中子粉末衍射精修失败: {error_msg}"
                id_to_task[id_] = None
            else:
                # 处理结果
                # print(info)
                id_to_task[id_]=None
                result_json['state']='completed'
                result_json['status']='success'
                result_json["name"] = f"{task_id}_neutron_refinement"
                
                # 计算输出文件大小并构建结果信息
                output_files = []
                total_size_bytes = 0
                total_size_mb = 0
                
                # 检查输出目录中的所有文件
                if os.path.exists(output_dir):
                    for filename in os.listdir(output_dir):
                        file_path = os.path.join(output_dir, filename)
                        if os.path.isfile(file_path):
                            file_size = os.path.getsize(file_path)
                            file_size_mb = file_size / (1024 * 1024)
                            
                            output_files.append({
                                "filename": filename,
                                "path": file_path,
                                "size_bytes": file_size,
                                "size_mb": round(file_size_mb, 3)
                            })
                            
                            total_size_bytes += file_size
                            total_size_mb += file_size_mb
                
                # 构建摘要信息
                rwp = info.get('rwp', 0.0)
                result_json["summary"] = f"GSAS-II中子粉末衍射精修完成，最终Rwp: {rwp:.2f}%\n"

                # 显示启用的精修参数
                enabled_params = []
                if refine_background:
                    enabled_params.append("背景")
                if refine_cell:
                    enabled_params.append("晶胞")
                if refine_scale:
                    enabled_params.append("标度")
                if refine_instrument:
                    enabled_params.append("仪器")
                if refine_absorption:
                    enabled_params.append("吸收")
                if refine_atoms:
                    enabled_params.append("原子")

                result_json["summary"] += f"精修参数: {', '.join(enabled_params) if enabled_params else '无'}\n"
                result_json["summary"] += f"总输出文件大小: {round(total_size_mb, 3)} MB\n"
                result_json["summary"] += f"生成文件数量: {len(output_files)}\n"
                
                # 添加主要文件信息
                if info.get('refined_cif_files'):
                    result_json["summary"] += f"精修CIF文件: {os.path.basename(info['refined_cif_files'][0])}\n"
                
                # 构建详细结果
                result_json['result'] = {
                    "status": "success",
                    "gpx_path": str(Path(output_dir) / f'neutron_refinement_{refine_idx}.gpx'),
                    "lst_path": str(Path(output_dir) / f'neutron_refinement_{refine_idx}.lst'),
                    "plot_path": info.get('plot_path', ''),
                    "refinement_log": info.get('refinement_log', '没有获取到本次精修的日志信息。'),
                    "input_files": {
                        "gsa_file": gsa_path,
                        "instprm_file": instprm_path,
                        "cif_file": cif_paths,
                        "gpx_file": gpx_path
                    },
                    "refinement_config": {
                        "refine_background": refine_background,
                        "refine_cell": refine_cell,
                        "refine_scale": refine_scale,
                        "refine_instrument": refine_instrument,
                        "refine_absorption": refine_absorption,
                        "refine_atoms": refine_atoms,
                        "use_constraints": use_constraints
                    },
                    "output_dir": output_dir,
                    "output_files": output_files,
                    "total_files": len(output_files),
                    "total_size_bytes": total_size_bytes,
                    "total_size_mb": round(total_size_mb, 3),
                    "refinement_results": {
                        "rwp": rwp,
                        "cell_parameters": info.get('cell_params', []),
                        "refined_cif_files": info.get('refined_cif_files', []) or glob(os.path.join(output_dir, '*_refined.cif')),
                        "data_quality": info.get('data_quality', {})
                    },
                    "processing_info": "中子粉末衍射数据精修完成，包含晶胞参数精修、原子位置优化等"
                }

        else:
            result_json['state']='running'
    return result_json

if __name__ == '__main__':
    # mcp.run(transport="stdio")
    mcp.run(transport="sse")

# 使用示例
# if __name__ == "__main__":
#     import sys
#     import traceback

#     print("="*60)
#     print("开始执行 GSAS-II 中子精修脚本")
#     print("="*60)

#     # 输入文件路径
#     input_dir = "/aifs/user/home/liqingmeng/rozai_agent/datasets/BL09"
#     output_dir = "/aifs/user/home/liqingmeng/rozai_agent/datasets/BL09/gsas_output20251222_6/output_gpx2"

#     # 方式1: 从头开始创建新项目
#     print("\n=== 方式1: 创建新项目 ===")
#     gsa_file = os.path.join(input_dir, "RUNdataFiles/RUN0000719/RUN0000719_groupHA.gsa")
#     inst_file = os.path.join(input_dir, "instrumentFIiles/groupHA_instr.instprm")
#     cif_file = os.path.join(input_dir, "RUNdataFiles/RUN0000719/zeolite.cif")

#     # 方式2: 使用已有的gpx文件继续精修
#     # 取消下面的注释来使用已有gpx文件
#     existing_gpx = "/aifs/user/home/liqingmeng/rozai_agent/datasets/BL09/gsas_output20251222_6/neutron_refinement.gpx"
#     # existing_gpx = None

#     print("\n检查输入文件:")
#     if existing_gpx:
#         print(f"模式: 加载现有GPX项目")
#         if os.path.exists(existing_gpx):
#             print(f"✓ GPX文件: {existing_gpx}")
#         else:
#             print(f"✗ GPX文件不存在: {existing_gpx}")
#             sys.exit(1)
#     else:
#         print(f"模式: 创建新项目")
#         for fpath, fname in [(gsa_file, "GSA文件"), (inst_file, "仪器参数文件"), (cif_file, "CIF文件")]:
#             if os.path.exists(fpath):
#                 size_mb = os.path.getsize(fpath) / (1024 * 1024)
#                 print(f"✓ {fname}: {fpath} ({size_mb:.2f} MB)")
#             else:
#                 print(f"✗ {fname} 不存在: {fpath}")
#                 sys.exit(1)

#     print("\n开始精修流程...")

#     try:
#         # 执行中子精修（使用True/False控制精修参数）
#         que = multiprocessing.Queue()

#                 # 定义要精修的原子标签
        
#         atom_labels_example1 = None  # 示例1: 精修所有原子
#         atom_labels_example2 = ["Si1", "Si2", "O1", "Al1"]  # 示例2: 只精修特定原子
#         atom_labels_example3 = ["Si", "Al"]  # 示例3: 只精修所有以Si或Al开头的原子       
#         atom_labels_example4 = ["O*"]  # 示例4: 使用通配符精修所有氧原子
        
#         # 选择要使用的原子标签配置
#         selected_atom_labels = atom_labels_example2  # 这里选择示例1（精修所有原子）
        
#         if selected_atom_labels is None:
#             print(f"原子精修设置: 精修所有原子")
#         else:
#             print(f"原子精修设置: 精修指定原子 {selected_atom_labels}")
#         # 定义原子精修参数类型
#         refine_atom_params = "XU"  # 精修原子位置(X)和温度因子(U)
#         print(f"原子精修参数类型: {refine_atom_params}")

#         if existing_gpx:
#             # 使用已有gpx文件
#             results = neutron_refinement(
#                 output_dir=output_dir,
#                 gpx_file=existing_gpx,          # 指定已有的gpx文件
#                 refine_background=True,        # 精修背景
#                 refine_cell=True,              # 精修晶胞
#                 refine_scale=True,             # 精修标度因子
#                 refine_instrument=True,        # 精修仪器参数
#                 refine_absorption=False,       # 不精修吸收参数
#                 refine_atoms=True,             # 精修原子参数和温度因子
#                 atom_labels=selected_atom_labels,  # 指定要精修的原子
#                 refine_atom_params=refine_atom_params,  # 原子精修参数类型
#                 use_constraints=True,          # 使用约束
#                 que=que
#             )
#         else:
#             # 创建新项目
#             results = neutron_refinement(
#                 neutron_data=gsa_file,
#                 neutron_inst=inst_file,
#                 cif_files=[cif_file],
#                 output_dir=output_dir,
#                 refine_background=True,        # 精修背景
#                 refine_cell=True,              # 精修晶胞
#                 refine_scale=True,             # 精修标度因子
#                 refine_instrument=True,        # 精修仪器参数
#                 refine_absorption=False,       # 不精修吸收参数
#                 refine_atoms=True,             # 精修原子参数和温度因子
#                 atom_labels=selected_atom_labels,  # 指定要精修的原子
#                 refine_atom_params=refine_atom_params,  # 原子精修参数类型
#                 use_constraints=True,          # 使用约束
#                 que=que
#             )

#         print("\n" + "="*60)
#         print("精修完成!")
#         print("="*60)
#         print(f"最终Rwp: {results['rwp']:.2f}%")
#         if results.get('refined_cif_files'):
#             print(f"\n生成的精修CIF文件:")
#             for cif_file_out in results['refined_cif_files']:
#                 print(f"  - {cif_file_out}")
#         print("="*60)

#     except KeyboardInterrupt:
#         print("\n\n用户中断执行")
#         sys.exit(1)
#     except Exception as e:
#         print("\n" + "!"*60)
#         print("精修过程中发生错误:")
#         print("!"*60)
#         print(f"错误类型: {type(e).__name__}")
#         print(f"错误信息: {str(e)}")
#         print("\n完整错误堆栈:")
#         traceback.print_exc()
#         print("!"*60)
#         sys.exit(1)


# import time,uuid
# id_=str(uuid.uuid4())
# for _ in range(1800):
#     t=write_info("/aifs/user/home/liqingmeng/rozai_agent/tools/GSAS-II-master/GSASII/RUN0021905"
#     ,"RUN0021905_group5.gsa"
#     ,"RT_GROUP5.instprm"
#     ,"mp-149.cif"
#     ,"/aifs/user/home/liqingmeng/rozai_agent/tools/GSAS-II-master/GSASII/RUN0021905/gsas_output_20250908"
#     ,id_)
#     if t['state']=="completed":
#         print(t)
#         break
#     else:
#         print(t)
#     time.sleep(100)
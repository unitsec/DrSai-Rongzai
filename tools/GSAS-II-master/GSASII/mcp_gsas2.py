from mcp.server.fastmcp import FastMCP

import glob
import time
import shutil
from typing import Dict, List, Any
from mcp.server.fastmcp import FastMCP
import GSASIIscriptable as G2sc

# 初始化MCP服务
# mcp = FastMCP("xrd_integration")

# 初始化MCP服务
mcp = FastMCP("xrd_simulation")

import os, sys
sys.path.insert(0, '/aifs/Users/toby/software/G2/GSASII')
import GSASIIscriptable as G2sc

# 配置路径（可根据需要修改）

GSASII_PATH = '/aifs/user/home/liqingmeng/multi_mcp_tools/GSAS-II-master/GSASII'
DATA_DIR = "/aifs/user/home/liqingmeng/multi_mcp_tools/GSAS-II-master/GSASII/0data_test/script_data"
CIF_DIR = "/aifs/user/home/liqingmeng/multi_mcp_tools/GSAS-II-master/GSASII/0data_test/cif"

# 添加GSAS-II路径
sys.path.insert(0, GSASII_PATH)

#########################################################################################
# '''Sample script to demonstrate use of GSASIIscriptable to duplicate the
# tutorial found here:
# https://subversion.xray.aps.anl.gov/pyGSAS/Tutorials/CWCombined/Combined%20refinement.htm

# This script is described in this tutorial: 
# https://subversion.xray.aps.anl.gov/pyGSAS/Tutorials/PythonScript/Scripting.htm
# '''

##多相，自定义精修次数

import os
import logging
from pathlib import Path
import matplotlib.pyplot as plt
import GSASIIscriptable as G2sc

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

def initialize_project(xray_data, xray_inst, neutron_data, neutron_inst, cif_files, output_dir, use_xray=True, use_neutron=True):
    """初始化GSAS-II项目并添加数据"""
    logger = logging.getLogger(__name__)
    gpx = G2sc.G2Project(filename=str(Path(output_dir) / 'refinement.gpx'))
    
    hists = []
    phases = []
    
    # 添加X射线数据（如果选择）
    if use_xray and xray_data and xray_inst:
        hist = gpx.add_powder_histogram(xray_data, xray_inst)
        hists.append(hist)
        logger.info(f"添加X射线数据: {xray_data}")
    
    # 添加中子数据（如果选择）
    if use_neutron and neutron_data and neutron_inst:
        hist = gpx.add_powder_histogram(neutron_data, neutron_inst)
        hists.append(hist)
        logger.info(f"添加中子数据: {neutron_data}")
    
    if not hists:
        raise ValueError("至少需要选择一个衍射数据集（X射线或中子）")
    
    # 添加多个相
    if cif_files:
        for i, cif_file in enumerate(cif_files, start=1):
            phase_name = f"Phase_{i}"
            phase = gpx.add_phase(cif_file, phasename=phase_name, histograms=hists)
            phases.append(phase)
            logger.info(f"添加晶体结构 {i}: {cif_file} (名称: {phase_name})")
    
    # 设置最大精修循环次数
    gpx.data['Controls']['data']['max cyc'] = 20
    
    return gpx, hists, phases

def refine_background(gpx, hists, output_dir, cycles=1, step_name='step4'):
    """背景精修"""
    if cycles <= 0:
        return
    
    logger = logging.getLogger(__name__)
    logger.info(f"执行背景精修（{cycles}次）...")
    ref_dict = {"set": {"Background": {"no. coeffs": 3, "refine": True}}}
    for _ in range(cycles):
        gpx.do_refinements([ref_dict])
    gpx.save(str(Path(output_dir) / f'{step_name}.gpx'))

def refine_cell(gpx, phases, output_dir, cycles=1, step_name='step5'):
    """晶胞参数精修"""
    if cycles <= 0:
        return
    
    logger = logging.getLogger(__name__)
    logger.info(f"执行晶胞参数精修（{cycles}次）...")
    ref_dict = {"set": {"Cell": True}}
    for _ in range(cycles):
        gpx.do_refinements([ref_dict])
    gpx.save(str(Path(output_dir) / f'{step_name}.gpx'))

def refine_hap(gpx, phases, hists, output_dir, cycles=1, step_name='step6'):
    """HAP参数精修"""
    if cycles <= 0:
        return
    
    logger = logging.getLogger(__name__)
    for hist in hists:
        for phase in phases:
            logger.info(f"执行HAP参数精修({phase.name}相, {hist.name}数据, {cycles}次)...")
            ref_dict = {"set": {"HStrain": True}}
            for _ in range(cycles):
                gpx.set_refinement(ref_dict, phase=phase, histogram=[hist])
                gpx.do_refinements([{}])
    gpx.save(str(Path(output_dir) / f'{step_name}.gpx'))

def refine_size_strain(gpx, phases, hists, output_dir, cycles=1, step_name='step7'):
    """尺寸和应变精修"""
    if cycles <= 0:
        return
    
    logger = logging.getLogger(__name__)
    for hist in hists:
        for phase in phases:
            logger.info(f"执行尺寸和应变精修({phase.name}相, {hist.name}数据, {cycles}次)...")
            ref_dict = {
                "set": {
                    "Mustrain": {"type": "isotropic", "refine": True},
                    "Size": {"type": "isotropic", "refine": True}
                }
            }
            for _ in range(cycles):
                gpx.set_refinement(ref_dict, phase=phase, histogram=[hist])
                gpx.do_refinements([{}])
    gpx.save(str(Path(output_dir) / f'{step_name}.gpx'))

def refine_sample_atoms(gpx, phases, hists, output_dir, cycles=1, step_name='step8'):
    """样品参数和原子位置精修"""
    if cycles <= 0:
        return
    
    logger = logging.getLogger(__name__)
    logger.info(f"执行样品参数和原子位置精修（{cycles}次）...")
    
    # 对每个hist设置不同的样品参数
    for i, hist in enumerate(hists):
        if i == 0:  # 第一个hist（通常是X射线）
            hist.set_refinements({'Sample Parameters': ['Shift']})
        else:       # 第二个hist（通常是中子）
            hist.set_refinements({'Sample Parameters': ['DisplaceX', 'DisplaceY']})
            hist.data['Sample Parameters']['Gonio. radius'] = 650.0
    
    # 原子位置精修（对所有相）
    for phase in phases:
        phase.set_refinements({"Atoms": {"all": "XU"}})
    
    for _ in range(cycles):
        gpx.do_refinements([{}])
    gpx.save(str(Path(output_dir) / f'{step_name}.gpx'))

def refine_instrument(gpx, hists, output_dir, cycles=1, step_name='step9'):
    """数据范围和仪器参数精修"""
    if cycles <= 0:
        return
    
    logger = logging.getLogger(__name__)
    logger.info(f"执行数据范围和仪器参数精修（{cycles}次）...")
    
    # 设置数据范围（根据hist类型设置不同范围）
    for i, hist in enumerate(hists):
        if i == 0:  # 第一个hist（通常是X射线）
            hist.set_refinements({'Limits': [8, 160]})
        else:       # 第二个hist（通常是中子）
            hist.set_refinements({'Limits': [8, 158.0]})
    
    # 仪器参数精修
    ref_dict = {"set": {'Instrument Parameters': ['U', 'V', 'W']}}
    for _ in range(cycles):
        gpx.do_refinements([ref_dict])
    gpx.save(str(Path(output_dir) / f'{step_name}.gpx'))

def export_results(gpx, hists, phases, output_dir):
    """导出结果和图表"""
    logger = logging.getLogger(__name__)
    results = {
        'rwp_values': {},
        'cell_parameters': {},
        'output_files': []
    }
    
    # 获取Rwp值
    for hist in hists:
        results['rwp_values'][hist.name] = hist.get_wR()
        logger.info(f"{hist.name} Rwp: {hist.get_wR():.2f}%")
    
    # 获取晶胞参数和相分数
    for phase in phases:
        results['cell_parameters'][phase.name] = phase.get_cell()
    
    # 导出数据
    for i, hist in enumerate(hists, start=1):
        data_file = Path(output_dir) / f'Refinement_data_hist{i}.csv'
        refl_file = Path(output_dir) / f'Refinement_refl_hist{i}.csv'
        
        hist.Export(str(data_file), '.csv', 'hist')
        hist.Export(str(refl_file), '.csv', 'refl')
        
        results['output_files'].extend([str(data_file), str(refl_file)])
    
    # 生成并保存图表（每个hist一个子图）
    if hists:
        plt.figure(figsize=(10, 6 * len(hists)))
        
        for i, hist in enumerate(hists, start=1):
            plt.subplot(len(hists), 1, i)
            x = hist.getdata('x')
            y_obs = hist.getdata('yobs')
            y_calc = hist.getdata('ycalc')
            
            plt.plot(x, y_obs, 'b-', label='Observed', linewidth=1)
            plt.plot(x, y_calc, 'r-', label='Calculated', linewidth=1)
            plt.title(f'{hist.name} ({"X-ray" if i == 1 else "Neutron"}) - Rwp: {hist.get_wR():.2f}%')
            plt.legend()
            plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plot_path = Path(output_dir) / 'refinement_plot.png'
        plt.savefig(str(plot_path), dpi=300, bbox_inches='tight')
        plt.close()
        results['output_files'].append(str(plot_path))
    
    return results

def powder_refinement(
    xray_data=None, 
    xray_inst=None, 
    neutron_data=None, 
    neutron_inst=None, 
    cif_files=None, 
    output_dir='output',
    use_xray=True,
    use_neutron=True,
    refine_background_cycles=1,
    refine_cell_cycles=1,
    refine_hap_cycles=1,
    refine_size_strain_cycles=1,
    refine_sample_atoms_cycles=1,
    refine_instrument_cycles=1
):
    """
    粉末衍射数据精修主函数（支持多相）
    
    参数:
        xray_data (str): X射线数据文件路径
        xray_inst (str): X射线仪器参数文件路径
        neutron_data (str): 中子数据文件路径
        neutron_inst (str): 中子仪器参数文件路径
        cif_files (list): CIF结构文件路径列表
        output_dir (str): 输出目录路径
        use_xray (bool): 是否使用X射线数据 (默认True)
        use_neutron (bool): 是否使用中子数据 (默认True)
        refine_*_cycles (int): 各精修步骤的执行次数，0表示不执行
        
    返回:
        dict: 包含精修结果的字典，包括:
            - rwp_values: 各数据的Rwp值
            - cell_parameters: 各相的晶胞参数
            - phase_fractions: 各相的相分数
            - output_files: 生成的文件列表
    """
    # 确保输出目录存在
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 设置日志
    logger = setup_logging(output_dir)
    logger.info("="*50)
    logger.info("开始多相结构精修分析")
    logger.info(f"使用X射线数据: {use_xray}")
    logger.info(f"使用中子数据: {use_neutron}")
    logger.info(f"相数量: {len(cif_files) if cif_files else 0}")
    logger.info("="*50)
    
    try:
        # 1. 初始化项目
        gpx, hists, phases = initialize_project(
            xray_data, xray_inst, neutron_data, neutron_inst, cif_files, output_dir,
            use_xray=use_xray, use_neutron=use_neutron
        )
        
        # 2. 执行精修步骤（根据cycles参数决定执行次数）
        refine_background(gpx, hists, output_dir, cycles=refine_background_cycles)
        refine_cell(gpx, phases, output_dir, cycles=refine_cell_cycles)
        refine_hap(gpx, phases, hists, output_dir, cycles=refine_hap_cycles)
        refine_size_strain(gpx, phases, hists, output_dir, cycles=refine_size_strain_cycles)
        refine_sample_atoms(gpx, phases, hists, output_dir, cycles=refine_sample_atoms_cycles)
        refine_instrument(gpx, hists, output_dir, cycles=refine_instrument_cycles)
        
        # 3. 导出结果
        results = export_results(gpx, hists, phases, output_dir)
        
        logger.info("="*50)
        logger.info("精修完成!")
        logger.info("="*50)
        
        return results
        
    except Exception as e:
        logger.error("!"*50)
        logger.error(f"精修过程中发生错误: {str(e)}")
        logger.error("!"*50)
        raise

# 使用示例
if __name__ == "__main__":
    # 输入文件路径
    input_dir = "/aifs/user/home/liqingmeng/multi_mcp_tools/GSAS-II-master/GSASII/0data_test/script_data"
    output_dir = "/aifs/user/home/liqingmeng/multi_mcp_tools/GSAS-II-master/GSASII/0data_test/script_data/output"
    
    # 定义多个CIF文件（多相）
    cif_files = [
        os.path.join(input_dir, "PbSO4-Wyckoff.cif"),
        #os.path.join(input_dir, "Be.cif")
    ]
    
    # 执行精修（示例：使用X射线和中子数据，3个相）
    refinement_results = powder_refinement(
        xray_data=os.path.join(input_dir, "PBSO4.XRA"),
        xray_inst=os.path.join(input_dir, "INST_XRY.PRM"),
        neutron_data=os.path.join(input_dir, "PBSO4.CWN"),
        neutron_inst=os.path.join(input_dir, "inst_d1a.prm"),
        cif_files=cif_files,
        output_dir=output_dir,
        use_xray=True,
        use_neutron=True,
        refine_background_cycles=1,
        refine_cell_cycles=10,  # 晶胞参数精修执行2次
        refine_hap_cycles=1,
        refine_size_strain_cycles=1,  # 不执行尺寸和应变精修
        refine_sample_atoms_cycles=1,
        refine_instrument_cycles=1
    )
    
    # 打印结果
    print("\n=== 精修结果 ===")
    print("Rwp值:")
    for name, rwp in refinement_results['rwp_values'].items():
        print(f"{name}: {rwp:.2f}%")
    
    print("\n晶胞参数:")
    for phase_name, cell_params in refinement_results['cell_parameters'].items():
        print(f"\n{phase_name}:")
        print(cell_params)
    
    print("\n生成的文件:")
    for file in refinement_results['output_files']:
        print(f"- {file}")




@mcp.tool()
def simulate_and_plot_xrd(cif_file, instrument_params, 
                            two_theta_range, num_points, 
                            output_prefix, save_plot):
    """模拟XRD图谱并绘制图表
    Args:
        cif_file (str): CIF文件路径
        instrument_params (str): 仪器参数文件路径
        two_theta_range (tuple): 2theta范围 (min, max)
        num_points (int): 数据点数
        output_prefix (str): 输出文件前缀
        save_plot (bool): 是否保存图表
    Returns:
        dict: 包含模拟结果和图表文件的路径
        {
            "status": "success",
            "project_file": str,  # 项目文件路径
            "data_file": str,  # 数据文件路径
            "reflections_file": str,  # 反射文件路径
            "plot_file": str,  # 图表文件路径（如果保存）
            "x_data": list,  # x数据
            "y_data": list,  # y数据
            "error": str  # 错误信息（如果有的话）
        }
        """
    # 获取 cif 文件名（不包含扩展名）
    phasename = os.path.splitext(os.path.basename(cif_file))[0]
  
    # 创建项目
    gpx = G2sc.G2Project(newgpx=f'{output_prefix}.gpx')
  
    # 添加相
    phase0 = gpx.add_phase(os.path.join(CIF_DIR, cif_file), phasename=phasename, fmthint='CIF')
  
    # 添加模拟的图谱并链接到之前添加的相
    hist1 = gpx.add_simulated_powder_histogram(f'{output_prefix} simulation', os.path.join(DATA_DIR, instrument_params), *two_theta_range, Npoints=num_points, phases=gpx.phases(), scale=500000.)
  
    # 计算图谱
    gpx.do_refinements()
  
    # 保存项目文件
    gpx.save(os.path.join(DATA_DIR, f'{output_prefix}.gpx'))
  
    # 导出结果
    gpx.histogram(0).Export(os.path.join(DATA_DIR, f'{output_prefix}_data'), '.csv', 'hist')  # 数据
    gpx.histogram(0).Export(os.path.join(DATA_DIR, f'{output_prefix}_refl'), '.csv', 'refl')  # 反射
  
    # 获取结果并绘制图表
    x = gpx.histogram(0).getdata('x')
    y = gpx.histogram(0).getdata('ycalc')
    import matplotlib.pyplot as plt
    plt.plot(x, y)
    if save_plot:
        plt.savefig(os.path.join(DATA_DIR, f'{output_prefix}__.png'))  # 保存图像到DATA_DIR路径下
        plt.close()  # 关闭图像窗口（避免在Jupyter中显示）
  
    return {
        "status": "success",
        "project_file": os.path.join(DATA_DIR, f'{output_prefix}.gpx'),
        "data_file": os.path.join(DATA_DIR, f'{output_prefix}_data.csv'),
        "reflections_file": os.path.join(DATA_DIR, f'{output_prefix}_refl.csv'),
        "plot_file": os.path.join(DATA_DIR, f'{output_prefix}__.png') if save_plot else None,
        "x_data": x.tolist(),  # 转换为列表便于JSON序列化
        "y_data": y.tolist(),
        "error": None
    }

# if __name__ == "__main__":
#     mcp.run(transport="stdio")

# 定义模拟参数
cif_file = "PbSO4-Wyckoff.cif"
instrument_params = "inst_d1a.prm"
two_theta_range = (5.0, 120.0)
num_points = 1000
output_prefix = "Pb_xrd_sim"
save_plot = True

# 调用模拟函数
#result=simulate_and_plot_xrd(cif_file, instrument_params, two_theta_range, num_points, output_prefix, save_plot)
#print(result)

# 配置GSAS-II参数
G2sc.blkSize = 2**8
G2sc.SetPrintLevel('warn')

@mcp.tool()
def integrate_single_image(
    image_file: str,
    image_control_file: str,
    output_dir: str = "custom_results"
) -> Dict[str, Any]:
    """
    处理单个XRD图像文件并生成积分数据（输出TXT格式）
    
    Args:
        image_file: 图像文件名(需在DATA_DIR中)
        image_control_file: 图像控制文件名(需在DATA_DIR中)
        output_dir: 输出目录名称(默认:"custom_results")
        
    Returns:
        {
            "status": "success"/"error",
            "input_image": 输入图像路径,
            "output_files": 生成的TXT文件列表,
            "gpx_file": 项目文件路径,
            "processing_time": 处理耗时(秒),
            "output_path": 输出目录绝对路径,
            "error": 错误信息(如有)
        }
    """
    # 构建完整路径
    img_path = os.path.join(DATA_DIR, image_file)
    ctrl_path = os.path.join(DATA_DIR, image_control_file)
    output_path = os.path.join(DATA_DIR, output_dir)
    
    # 创建输出目录
    os.makedirs(output_path, exist_ok=True)

    try:
        start_time = time.time()
        
        # 验证输入文件
        if not os.path.exists(img_path):
            raise FileNotFoundError(f"图像文件不存在: {img_path}")
        if not os.path.exists(ctrl_path):
            raise FileNotFoundError(f"控制文件不存在: {ctrl_path}")

        # 创建GSAS-II项目
        gpx_path = os.path.join(output_path, 'integration.gpx')
        gpx = G2sc.G2Project(newgpx=gpx_path)
        
        # 加载图像和控制文件
        img_list = gpx.add_image(img_path, fmthint="TIF")
        img = img_list[0]
        img.loadControls(ctrl_path)
        
        # 执行积分
        pwdrList = img.Integrate()
        
        # 保存项目文件
        gpx.save()
        
        # 导出积分数据为TXT格式
        output_files = []
        base_name = os.path.splitext(image_file)[0]
        
        for i, pwdr in enumerate(pwdrList):
            # 修改1：指定.txt扩展名
            output_file = os.path.join(output_path, f"{base_name}_{i}.txt")
            
            # 修改2：明确使用.txt作为导出格式
            pwdr.Export(output_file.split('.')[0], '.txt', 'hist')  # 'hist'表示导出衍射数据
            
            output_files.append(os.path.relpath(output_file, DATA_DIR))
        
        return {
            "status": "success",
            "input_image": os.path.relpath(img_path, DATA_DIR),
            "output_files": output_files,
            "gpx_file": os.path.relpath(gpx_path, DATA_DIR),
            "processing_time": round(time.time() - start_time, 2),
            "output_path": output_path,
            "error": None
        }
        
    except Exception as e:
        return {
            "status": "error",
            "input_image": os.path.relpath(img_path, DATA_DIR) if 'img_path' in locals() else image_file,
            "output_files": [],
            "gpx_file": "",
            "processing_time": 0,
            "output_path": "",
            "error": str(e)
        }
    finally:
        if 'gpx' in locals():
            del gpx
            
# result = integrate_single_image(
#     image_file="Si_free_dc800_1-00000.tif",  # 必须参数
#     image_control_file="Si_free_dc800_1-00000.imctrl",  # 必须参数
#     output_dir="custom_results"  # 可选，自定义输出目录
# )
# print(result)

# 配置GSAS-II参数
G2sc.blkSize = 2**8  # 计算机相关性能调优参数
G2sc.SetPrintLevel('warn')  # 减少输出信息

@mcp.tool()
def xrd_img_process(
    image_control_file: str,
    image_mask_file: str,
    file_pattern: str = "*_d700-*.tif",
    max_images: int = 10,
    output_dir: str = "integrated_results"
) -> Dict[str, Any]:
    """
    将XRD图像积分转换为衍射数据
    
    Args:
        image_control_file: 图像控制文件名(需在DATA_DIR中)
        image_mask_file: 图像掩膜文件名(需在DATA_DIR中) 
        file_pattern: 待处理图像文件匹配模式 (默认:"*_d700-*.tif")
        max_images: 单次最大处理图像数量 (默认:10)
        output_dir: 输出目录名称 (默认:"integrated_results")
        
    Returns:
        {
            "status": "success"/"error",
            "processed_images": 已处理的图像文件列表,
            "output_files": 生成的.xye数据文件列表,
            "processing_time": 总耗时(秒),
            "output_path": 输出目录绝对路径,
            "error": 错误信息(如有)
        }
    """
    # 初始化缓存
    cache = {}
    
    # 构建完整路径
    ctrl_path = os.path.join(DATA_DIR, image_control_file)
    mask_path = os.path.join(DATA_DIR, image_mask_file)
    output_path = os.path.join(DATA_DIR, output_dir)
    
    # 创建输出目录结构
    img_output = os.path.join(output_path, 'processed_images')
    xye_output = os.path.join(output_path, 'xye_data')
    os.makedirs(img_output, exist_ok=True)
    os.makedirs(xye_output, exist_ok=True)

    def wait_for_metadata(tif_path):
        """等待元数据文件生成"""
        meta_file = tif_path + '.metadata'
        while not os.path.exists(meta_file):
            time.sleep(0.05)

    try:
        # 验证输入文件
        if not all(os.path.exists(f) for f in [ctrl_path, mask_path]):
            missing = [f for f in [ctrl_path, mask_path] if not os.path.exists(f)]
            raise FileNotFoundError(f"缺少必要文件: {missing}")

        # 获取待处理文件列表(按创建时间排序)
        tif_list = sorted(
            glob.glob(os.path.join(DATA_DIR, file_pattern)),
            key=lambda x: os.path.getctime(x)
        )[:max_images]

        if not tif_list:
            return {
                "status": "success",
                "message": f"在{DATA_DIR}中未找到匹配{file_pattern}的图像文件",
                "processed_images": [],
                "output_files": [],
                "processing_time": 0,
                "output_path": output_path
            }

        start_time = time.time()
        results = {
            "processed_images": [],
            "output_files": []
        }

        # 创建临时GSAS-II项目
        with G2sc.G2Project(newgpx=os.path.join(DATA_DIR, 'tmp_integration.gpx')) as gpx:
            # 处理每个图像文件
            for tif_path in tif_list:
                try:
                    # 等待元数据文件就绪
                    wait_for_metadata(tif_path)
                    
                    # 加载图像
                    img = next(gpx.add_image(tif_path, fmthint="TIF", cacheImage=True))
                    
                    # 首次运行时加载控制参数
                    if not cache:
                        img.loadControls(ctrl_path)
                        img.loadMasks(mask_path)
                        
                        cache.update({
                            'Image Controls': img.getControls(),
                            'Masks': img.getMasks(),
                            'intMaskMap': img.IntMaskMap(),
                            'intTAmap': img.IntThetaAzMap(),
                            'FrameMask': img.MaskFrameMask(),
                            'maskTmap': img.MaskThetaMap()
                        })
                    else:
                        # 复用缓存参数
                        img.setControls(cache['Image Controls'])
                        img.setMasks(cache['Masks'], True)
                    
                    # 生成像素掩膜
                    img.GeneratePixelMask(
                        esdMul=3,
                        ThetaMap=cache['maskTmap'],
                        FrameMask=cache['FrameMask']
                    )
                    
                    # 执行积分并导出数据
                    for pwdr in img.Integrate(
                        MaskMap=cache['intMaskMap'],
                        ThetaAzimMap=cache['intTAmap']
                    ):
                        base_name = os.path.splitext(os.path.basename(tif_path))[0]
                        output_file = os.path.join(xye_output, f"{base_name}.xye")
                        pwdr.Export(output_file)
                        results["output_files"].append(output_file)
                    
                    # 清理资源并移动已处理文件
                    img.clearImageCache()
                    img.clearPixelMask()
                    shutil.move(tif_path, img_output)
                    shutil.move(tif_path + '.metadata', img_output)
                    
                    results["processed_images"].append(os.path.basename(tif_path))
                    
                except Exception as e:
                    print(f"处理文件 {tif_path} 时出错: {str(e)}")
                    continue

        # 返回处理结果
        return {
            "status": "success",
            "processed_images": results["processed_images"],
            "output_files": [os.path.relpath(f, DATA_DIR) for f in results["output_files"]],
            "processing_time": round(time.time() - start_time, 2),
            "output_path": output_path,
            "error": None
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "processed_images": [],
            "output_files": [],
            "processing_time": 0,
            "output_path": ""
        }


# if __name__ == "__main__":
#     mcp.run(transport="stdio")
# print(xrd_img_integration(image_control_file,image_mask_file,
#     file_pattern = "*_d700-*.tif",
#     max_images = 10,output_dir = "integrated_results"))

# result = xrd_img_process(
#     image_control_file="Si_ch3_d700-00000.imctrl",  # 自动从DATA_DIR读取
#     image_mask_file="Si_ch3_d700-00000.immask",    # 自动从DATA_DIR读取
#     file_pattern="*_d700-*.tif"                    # 在DATA_DIR中匹配
# )

# print(result)



# import os
# import sys
# import matplotlib.pyplot as plt
# from typing import Dict, Any
# from mcp.server.fastmcp import FastMCP
# import GSASIIscriptable as G2sc

# # 初始化MCP服务
# mcp = FastMCP("xrd_simulation")

# # 配置路径（可根据需要修改）
# GSASII_PATH = '/Users/liqingmeng-macbook/working/GSAS-II-master/GSASII'
# DATA_DIR = "/Users/liqingmeng-macbook/working/GSAS-II-master/GSASII/0data_test/script_data"
# CIF_DIR = "/Users/liqingmeng-macbook/working/GSAS-II-master/GSASII/0data_test/cif"

# # 添加GSAS-II路径
# sys.path.insert(0, GSASII_PATH)

# @mcp.tool()
# def simulate_and_plot_xrd(
#     cif_file: str,
#     instrument_params: str = "inst_d1a.prm",
#     two_theta_range: tuple = (5.0, 120.0),
#     num_points: int = 1000,
#     output_prefix: str = "xrd_sim",
#     save_plot: bool = True
# ) -> Dict[str, Any]:
#     """
#     模拟X射线粉末衍射图谱并绘制结果
    
#     Args:
#         cif_file: CIF结构文件名 (需位于数据目录)
#         instrument_params: 仪器参数文件名 (默认: inst_d1a.prm)
#         two_theta_range: 2θ角度范围 (最小, 最大)
#         num_points: 数据点数
#         output_prefix: 输出文件前缀
#         save_plot: 是否保存图谱图片
        
#     Returns:
#         {
#             "status": "success"/"error",
#             "project_file": GPX项目文件路径,
#             "data_file": 衍射数据CSV路径,
#             "reflections_file": 衍射峰CSV路径,
#             "plot_file": 图谱图片路径(如保存),
#             "x_data": 2θ角度数据,
#             "y_data": 强度数据,
#             "error": 错误信息
#         }
#     """
#     try:
#         # 路径处理函数
#         def get_path(filename):
#             return os.path.join(DATA_DIR, filename)
        
#         # 创建GSAS-II项目
#         gpx = G2sc.G2Project(newgpx=get_path(f'{output_prefix}.gpx'))
        
#         # 添加晶体相
#         phase = gpx.add_phase(
#             get_path(cif_file),
#             phasename=os.path.splitext(cif_file)[0],
#             fmthint='CIF'
#         )
        
#         # 添加模拟衍射图谱
#         hist = gpx.add_simulated_powder_histogram(
#             f"{output_prefix} pattern",
#             get_path(instrument_params),
#             two_theta_range[0],
#             two_theta_range[1],
#             Npoints=num_points,
#             phases=gpx.phases(),
#             scale=500000
#         )
        
#         # 执行计算
#         gpx.do_refinements()
#         gpx.save()
        
#         # 导出数据
#         data_csv = get_path(f'{output_prefix}_data.csv')
#         refl_csv = get_path(f'{output_prefix}_refl.csv')
#         hist.Export(data_csv.split('.')[0], '.csv', 'hist')
#         hist.Export(refl_csv.split('.')[0], '.csv', 'refl')
        
#         # 获取绘图数据
#         x = hist.getdata('x')
#         y = hist.getdata('ycalc')
        
#         # 绘制图谱
#         plt.figure(figsize=(10, 6))
#         plt.plot(x, y, 'b-', linewidth=1.5)
#         plt.xlabel('2θ (degrees)', fontsize=12)
#         plt.ylabel('Intensity (a.u.)', fontsize=12)
#         plt.title(f'XRD Simulation: {os.path.splitext(cif_file)[0]}', fontsize=14)
#         plt.grid(True, alpha=0.3)
        
#         plot_path = None
#         if save_plot:
#             plot_path = get_path(f'{output_prefix}_plot.png')
#             plt.savefig(plot_path, dpi=300, bbox_inches='tight')
#             plt.close()
        
#         return {
#             "status": "success",
#             "project_file": get_path(f'{output_prefix}.gpx'),
#             "data_file": data_csv,
#             "reflections_file": refl_csv,
#             "plot_file": plot_path,
#             "x_data": x.tolist(),  # 转换为列表便于JSON序列化
#             "y_data": y.tolist(),
#             "error": None
#         }
        
#     except Exception as e:
#         return {
#             "status": "error",
#             "project_file": None,
#             "data_file": None,
#             "reflections_file": None,
#             "plot_file": None,
#             "x_data": None,
#             "y_data": None,
#             "error": str(e)
#         }
    
# # if __name__ == "__main__":
# #     mcp.run(transport="stdio")

# print(simulate_and_plot_xrd(
#     cif_file="/CIF_DIR/PbSO4-Wyckoff.cif",
#     instrument_params = "/DATA_DIR/inst_d1a.prm",
#     two_theta_range= (5.0, 120.0),
#     num_points= 1000,
#     output_prefix= "xrd_sim",
#     save_plot= True
# ))
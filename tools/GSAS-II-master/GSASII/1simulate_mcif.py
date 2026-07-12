import logging
from pathlib import Path
import os
import sys
import numpy as np
from mcp.server.fastmcp import FastMCP
import multiprocessing
import GSASIIscriptable as G2sc
import csv
from itertools import zip_longest
import matplotlib.pyplot as plt

# 创建 FastMCP 实例，端口 50054
mcp = FastMCP(
    name="NPD_Simulator_Tool",
    instructions="A tool for simulating the neutron powder diffraction pattern from cif/mcif file and instrument file.",
    port=50054,
)

def setup_logging(output_dir):
    """配置日志系统"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(Path(output_dir) / 'NPD_Simulator.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


class HiddenPrints:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout


def set_background_simple(gpx, hist_name,
                          cheb_coeffs=None, cheb_refine=False,
                          debye_terms=None):
    """
    直接写入 gpx.data[hist]['Background']，并把 Debye 项转换成
    GSAS-II 期望的 [A,refA,R,refR,U,refU] 形式。
    - cheb_coeffs: [c0,c1,...]
    - debye_terms:
    接受三种写法：
    1) (A,R,U)
    2) (A,refA,R,refR,U,refU)
    3) {'A':..,'R':..,'U':.., 可选 'refA','refR','refU'}
    Debye 项物理含义（简述）
        这是用 Debye 散射方程近似的背景项，用来描述无序/玻璃/容器等近邻对导致的缓慢起伏背景。
        一个项对应一组有效“原子对”：
        A：幅度，类似该对的“权重/数量”（越大贡献越大）
        R：该对的平均间距（Å），控制起伏的周期 2π/R（在 Q 域）
        U：均方位移/展宽项，随 Q 增大指数衰减，U 大→高 Q 更快衰减
    """
    bg = gpx.data[hist_name].get('Background')
    if bg is None:
        bg = [['chebyschev-1', False, 3, 1.0, 0.0, 0.0],
              {'nDebye': 0, 'debyeTerms': [], 'nPeaks': 0,
               'peaksList': [], 'background PWDR': ['', 1.0, False]}]
        gpx.data[hist_name]['Background'] = bg

    # Chebyshev
    if cheb_coeffs is not None:
        n = int(len(cheb_coeffs))
        gpx.data[hist_name]['Background'][0] = ['chebyschev-1',
                                                bool(cheb_refine),
                                                n] + [float(v) for v in cheb_coeffs]

    # Debye（规范化为 [A,refA,R,refR,U,refU]）
    if debye_terms is not None:
        norm_terms = []
        for t in debye_terms:
            if isinstance(t, dict):
                A = float(t.get('A', 0.0))
                R = float(t.get('R', 10.0))
                U = float(t.get('U', 0.0))
                refA = bool(t.get('refA', False))
                refR = bool(t.get('refR', False))
                refU = bool(t.get('refU', False))
                term = [A, refA, R, refR, U, refU]
            else:
                t = list(t)
            if len(t) == 3:
                A, R, U = float(t[0]), float(t[1]), float(t[2])
                term = [A, False, R, False, U, False]
            elif len(t) == 6:
                # 允许两种顺序：[(A,R,U),(refA,refR,refU)] 或 [A,refA,R,refR,U,refU]
                # 这里尽量判断：若 t[1],t[3],t[5] 是布尔值/0/1，则按交错对待
                def as_bool(x): return bool(x) if isinstance(x, (bool, int)) else str(x).lower() in ('true','t','y','yes','1')
                if all(isinstance(t[i], (bool, int)) for i in (1,3,5)):
                    term = [float(t[0]), as_bool(t[1]),
                    float(t[2]), as_bool(t[3]),
                    float(t[4]), as_bool(t[5])]
                else:
                    # 假定是 [A,R,U,refA,refR,refU]
                    term = [float(t[0]), as_bool(t[3]),
                    float(t[1]), as_bool(t[4]),
                    float(t[2]), as_bool(t[5])]
            else:
                raise ValueError("debye_terms entry must be len 3 or 6, or dict")
        norm_terms.append(term)

        gpx.data[hist_name]['Background'][1]['nDebye'] = len(norm_terms)
        gpx.data[hist_name]['Background'][1]['debyeTerms'] = norm_terms


def _find_atom_indices_by_label(phase, label):
    """返回与标签匹配的原子行索引列表（可能有重名）。"""
    atoms = phase.data['Atoms']
    idxs = [i for i, row in enumerate(atoms) if str(row[0]) == str(label)]
    return idxs


def edit_atom(phase, label,
              x=None, y=None, z=None,
              occ=None,
              uiso=None, uij=None,
              mx=None, my=None, mz=None,
              mom_sym=None):
    """
    按原子标签修改晶体与磁结构参数。
    - 位置: x,y,z；占位: occ
    - 热参数: uiso 或 uij(6元列表: U11,U22,U33,U12,U13,U23)
    - 磁矩: mx,my,mz；磁矩对称标签: mom_sym（常用 'mx,my,mz'）
    若有多个同名原子，将全部应用；可按需改成只改第一个。
    """
    G = phase.data['General']
    ap = G['AtomPtrs']  # 例如 [3,1,10,12]
    xyz0 = ap[0]
    occ_col = xyz0 + 3
    mom_sym_col = ap[2]
    mx_col, my_col, mz_col = mom_sym_col - 3, mom_sym_col - 2, mom_sym_col - 1
    utype_col = ap[3]  # 'I' 或 'A'

    atoms = phase.data['Atoms']
    idxs = _find_atom_indices_by_label(phase, label)
    if not idxs:
        raise ValueError(f'No atom with label "{label}" found')

    for i in idxs:
        row = atoms[i]
        # 位置/占位
        if x is not None: row[xyz0 + 0] = float(x)
        if y is not None: row[xyz0 + 1] = float(y)
        if z is not None: row[xyz0 + 2] = float(z)
        if occ is not None: row[occ_col] = float(occ)
        # 热参数
        if uiso is not None:
            row[utype_col] = 'I'
            row[utype_col + 1] = float(uiso)
        if uij is not None:
            if len(uij) != 6:
                raise ValueError('uij must have 6 values: U11,U22,U33,U12,U13,U23')
            row[utype_col] = 'A'
            for k in range(6):
                row[utype_col + 1 + k] = float(uij[k])
        # 磁矩
        if mx is not None: row[mx_col] = float(mx)
        if my is not None: row[my_col] = float(my)
        if mz is not None: row[mz_col] = float(mz)
        if mom_sym is not None: row[mom_sym_col] = str(mom_sym)


def compute_component(gpx, phase, hist, which='nuclear', mag_dmin=0.6):
    """
    计算单一分量（nuclear 或 magnetic），返回 x,ycalc。
    通过 General['Type'] 切换，确保 parmDict[pfx+'isMag'] 匹配。
    """
    G = phase.data['General']
    print(G['Type'])
    if which == 'nuclear':
        G['Type'] = 'nuclear'
    elif which == 'magnetic':
        G['Type'] = 'magnetic'
    else:
        raise ValueError("which must be 'nuclear' or 'magnetic'")
    G['MagDmin'] = float(mag_dmin)  # 对磁散射有效

    gpx.data['Controls']['data']['max cyc'] = 0
    gpx.do_refinements([{}])

    x = hist.getdata('x')
    y = hist.getdata('ycalc')
    return np.asarray(x, float), np.asarray(y, float)

def simulate_from_mcif(
    mcif, instprm, tmin, tmax,
    mode='both',                  # 'nuclear' | 'magnetic' | 'both'
    mag_dmin=0.6,
    cheb_coeffs=None,             # 背景 Chebyshev 系数，例如 [1.0, 0.0, 0.0]
    cheb_refine=False,
    debye_terms=None,             # Debye 项 [(A,R,U), ...]
    edits=None,                   # 原子/磁矩编辑指令列表，如 [{'label':'Mn','mx':2,'my':4,'mz':1,'mom_sym':'mx,my,mz'}]
    phasename='phase',
    gpxfile='./_tmp_sim.gpx',
    keep_gpx=False,
    task_id: str | None = None,
    output_dir='./',
    result_queue=multiprocessing.Queue()
):
    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 设置日志
    logger = setup_logging(output_dir)
    logger.info("="*50)
    logger.info("开始NPD模拟")
    logger.info(f"结构数据: {os.path.basename(mcif)}")
    logger.info(f"仪器参数: {os.path.basename(instprm)}")
    logger.info("="*50)

    try:
        with HiddenPrints():
            gpx = G2sc.G2Project(newgpx=gpxfile)
            phase = gpx.add_phase(mcif, mag=True, phasename=phasename)

            hist = gpx.add_simulated_powder_histogram(
                "profile", instprm, float(tmin), float(tmax), phases=[phase]
            )
            hist_name = hist.name  # 通常是 'PWDR profile'

            # 背景
            set_background_simple(gpx, hist_name,
                                cheb_coeffs=cheb_coeffs,
                                cheb_refine=cheb_refine,
                                debye_terms=debye_terms)

            # 在 add_phase 之后，直接编辑晶体与磁结构
            if edits:
                for ed in edits:
                    edit_atom(phase, **ed)

            # 计算
            x = None
            yN = yM = None
            if mode in ('nuclear', 'both'):
                x, yN = compute_component(gpx, phase, hist, which='nuclear', mag_dmin=mag_dmin)
            if mode in ('magnetic', 'both'):
                x, yM = compute_component(gpx, phase, hist, which='magnetic', mag_dmin=mag_dmin)

            if x is None:
                raise RuntimeError("Nothing computed. Check mode & inputs.")

            yTot = np.zeros_like(x)
            if yN is not None: yTot += yN
            if yM is not None: yTot += yM
            if not keep_gpx:
                try: os.remove(gpxfile)
                except Exception: pass
        # 组织结果并附带可能的输出文件路径（稍后填充）
        result = {
            "tof": x,
            "yTot": yTot,
            "yN": yN,
            "yM": yM,
            "csv_file": None,
            "plot_file": None,
        }

        # 尝试将结果保存到 output_dir（CSV + PNG），不依赖 pandas
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            csv_file_path = None
            plot_file_path = None
            if x is not None and len(x) > 0:
                csv_file_path = os.path.join(output_dir, f"simulation_data_{task_id or 'anon'}.csv")
                try:
                    with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvf:
                        writer = csv.writer(csvf)
                        writer.writerow(['tof', 'yTot', 'yN', 'yM'])
                        # 将可能的 numpy arrays 转为列表，避免在布尔上下文中引发异常
                        x_list = list(x) if x is not None else []
                        yTot_list = list(yTot) if yTot is not None else []
                        yN_list = list(yN) if yN is not None else []
                        yM_list = list(yM) if yM is not None else []
                        for row in zip_longest(x_list, yTot_list, yN_list, yM_list, fillvalue=''):
                            writer.writerow(row)
                except Exception as e:
                    logger.error(f"Error writing CSV file: {e}")

                if yTot is not None and len(yTot) > 0:
                    try:
                        plt.figure(figsize=(10, 6))
                        # 使用列表以兼容之前的转换
                        plt.plot(x_list, yTot_list, 'b-', linewidth=1, label='Total Intensity')
                        plt.xlabel('Time of Flight (μs)')
                        plt.ylabel('Intensity')
                        plt.title('NPD Simulation Result')
                        plt.grid(True, alpha=0.3)
                        plt.legend()
                        plot_file_path = os.path.join(output_dir, f"simulation_plot_{task_id or 'anon'}.png")
                        plt.savefig(plot_file_path, dpi=300, bbox_inches='tight')
                        plt.close()
                    except Exception as e:
                        logger.error(f"Error saving plot: {e}")

            # 将文件路径写回结果
            result['csv_file'] = csv_file_path
            result['plot_file'] = plot_file_path
        except Exception as e:
            logger.error(f"Error while saving output files: {e}")
        
        logger.info("="*50)
        logger.info(f"衍射谱模拟完成！")
        logger.info("="*50)
        result_queue.put(result)
        return result
    
    except Exception as e:
        logger.error("!"*50)
        logger.error(f"模拟失败: {str(e)}")
        logger.error("!"*50)
        result_queue.put({})
        raise



id_to_task={}
id_to_result={}

@mcp.tool()
def simulator(structure_file:str, #mcif_path, 
              instprm_path:str,
              tmin:float=10,
              tmax:float=90,
              mode:str='nuclear',
              mag_dmin:float=0.6,
              cheb_coeffs:list=None,
              cheb_refine:bool=False,
              debye_terms:list=None,
              edits:list=None,
              phasename:str='Unknown',
              gpxfile:str='./_tmp_sim.gpx',
              keep_gpx:bool=False,
              task_id: str | None = None,
              thread_id: str | None = None):
    
    """
    调用NPD_Simulator来预测空间群。

    Args:
        structure_file: 结构文件的绝对路径
        instprm_path: 实验参数文件的绝对路径
        task_id: 任务 id，默认自动生成
        message: 线程 id,默认自动生成

    Returns:
        一个包含 task_id, state, result 的字典, result本身是一个包含结构化输出的字典
    """

    id_=task_id
    result_json={"id":id_,'state':None,'result':None}
    output_dir = os.path.join(os.path.dirname(structure_file), f"output/{thread_id}/NPD_Simulator_output_{task_id}")

    if id_ not in id_to_task or id_to_task[id_]==None:
        # 任务创建
        id_to_result[id_]=multiprocessing.Queue()
        id_to_task[id_]=multiprocessing.Process(
            target=simulate_from_mcif, 
            args=(structure_file,instprm_path,tmin,tmax,mode,mag_dmin,cheb_coeffs,cheb_refine,debye_terms,edits,phasename,gpxfile,keep_gpx, task_id, output_dir, id_to_result[id_]))
        result_json['state']='created'
        id_to_task[id_].start()
    else:
        if not id_to_task[id_].is_alive():
            info=id_to_result[id_].get()
            id_to_task[id_].join()
            if not info:
                # 任务失败
                result_json['state']='completed'
                result_json['status']='error'
                result_json['result']={
                    "status":"error",
                    'error':'衍射谱模拟失败',
                    'suggestion':'请检查输入的的结构文件是否正确'}
                result_json['summary']="NPD Simulator衍射谱模拟失败"
            else:
                # 处理结果
                print(info)
                id_to_task[id_]=None
                result_json['state']='completed'
                result_json['status']='success'
                result_json["name"] = f"{task_id}_NPD_Simulator_output"
                
                # 构建摘要信息
                tof = info.get('tof', [])
                yTot = info.get('yTot', [])
                yN = info.get('yN', [])
                yM = info.get('yM', [])
                result_json["summary"] = f"衍射谱模拟完成"
                
                # 从子进程结果读取已保存的文件路径（simulate_from_mcif 中负责保存）
                csv_file_path = info.get('csv_file') if isinstance(info, dict) else None
                plot_file_path = info.get('plot_file') if isinstance(info, dict) else None

                # 构建详细结果
                result_json['result'] = {
                    "status":"success",
                    "input_strucutre_file": structure_file,
                    "output_dir": output_dir,
                    "csv_file": csv_file_path,
                    "plot_file": plot_file_path,
                    "simulation_results": {
                        "tof": tof,
                        "yTot": yTot,
                        "yN": yN,
                        "yM": yM
                    },
                "processing_info": "使用NPD Simulator进行衍射谱模拟，包含飞行时间，总衍射谱，核结构衍射谱，磁结构衍射谱。"
                }
        else:
            result_json['state']='running'

    return result_json

if __name__ == '__main__':
    # 以 SSE 方式启动服务，监听端口
    mcp.run(transport='sse')


# if __name__ == '__main__':
#     # 路径按需修改
#     cif_path = '/home/dur/rozai_agent/datasets/BL16/cifFiles/Si.cif'
#     # cif_path = '/home/dur/rozai_agent/datasets/BL16/cifFiles/LaMnO3.mcif'
#     instprm_path = '/home/dur/rozai_agent/datasets/BL16/instrumentFiles/RT_group4.instprm'
#     output_dir = "/home/dur/rozai_agent/datasets/BL16/cifFiles/simulator_output_test"

#     result = simulate_from_mcif(
#         mcif=cif_path,
#         instprm=instprm_path,
#         tmin=10, tmax=90,
#         mode='nuclear',
#         mag_dmin=0.6,
#         cheb_coeffs=[1.0, 0.0, 0.0],
#         cheb_refine=False,
#         debye_terms=None,
#         edits=[],
#         phasename='Unknown',
#         gpxfile='./_tmp_sim.gpx',
#         keep_gpx=False,
#         output_dir=output_dir
#     )








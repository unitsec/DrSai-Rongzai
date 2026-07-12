# GSAS-II 中子精修脚本使用说明

## 功能概述

本脚本提供了简化的中子粉末衍射数据精修接口，支持：
1. ✅ **True/False 开关控制精修参数**（替代原来的循环次数控制）
2. ✅ **一次性精修所有参数**（不再需要多次循环）
3. ✅ **支持加载已有 GPX 项目继续精修**（新增功能）

## 主要改进

### 1. 简化的参数控制
```python
# 之前 (旧版本)
refine_background=[1, 1],  # [顺序, 循环次数]
refine_cell=[2, 3],
refine_scale=[3, 1],

# 现在 (新版本)
refine_background=True,    # 简单的 True/False
refine_cell=True,
refine_scale=False,        # 不需要的参数设为 False
```

### 2. 一次性精修
所有启用的精修参数会被汇总到一个 `ref_dict` 中，调用一次 `gpx.do_refinements([ref_dict])` 完成精修。

### 3. 支持继续精修已有项目
可以加载之前保存的 `.gpx` 文件继续精修，无需重新初始化。

## 使用方法

### 方式1: 创建新项目

```python
from 0neutron_gsas_refine import neutron_refinement

results = neutron_refinement(
    neutron_data="path/to/data.gsa",
    neutron_inst="path/to/instrument.instprm",
    cif_files=["path/to/structure.cif"],
    output_dir="output_directory",
    # 精修参数控制 (True/False)
    refine_background=True,    # 精修背景
    refine_cell=True,          # 精修晶胞参数
    refine_scale=True,         # 精修标度因子
    refine_instrument=True,    # 精修仪器参数
    refine_absorption=False,   # 不精修吸收参数
    refine_atoms=True,         # 精修原子参数和温度因子
    use_constraints=True       # 使用约束
)

print(f"最终 Rwp: {results['rwp']:.2f}%")
```

### 方式2: 加载已有项目继续精修

```python
results = neutron_refinement(
    gpx_file="path/to/existing_project.gpx",  # 指定已有的 gpx 文件
    output_dir="output_directory",
    # 精修参数控制
    refine_background=True,
    refine_cell=True,
    refine_scale=True,
    refine_instrument=True,
    refine_absorption=False,
    refine_atoms=True,
    use_constraints=True
)
```

**注意**：当使用 `gpx_file` 参数时，`neutron_data`、`neutron_inst` 和 `cif_files` 参数是可选的。

## 精修参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `refine_background` | bool | False | 是否精修背景 |
| `refine_cell` | bool | False | 是否精修晶胞参数 |
| `refine_scale` | bool | False | 是否精修标度因子 |
| `refine_instrument` | bool | False | 是否精修仪器参数 |
| `refine_absorption` | bool | False | 是否精修吸收参数 |
| `refine_atoms` | bool | False | 是否精修原子参数和温度因子 |
| `use_constraints` | bool | True | 是否使用约束 |
| `gpx_file` | str | None | 可选的已有 GPX 项目文件路径 |

## MCP 工具函数

### `write_info()` 函数

用于异步任务管理的 MCP 工具函数，支持相同的参数：

```python
result = write_info(
    gsa_file="path/to/data.gsa",         # 当 gpx_file 为 None 时必需
    instprm_file="path/to/inst.instprm", # 当 gpx_file 为 None 时必需
    cif_files=["path/to/struct.cif"],    # 当 gpx_file 为 None 时必需
    gpx_file="path/to/existing.gpx",     # 可选：使用已有项目
    refine_background=True,
    refine_cell=True,
    refine_scale=True,
    refine_instrument=True,
    refine_absorption=False,
    refine_atoms=True,
    use_constraints=True,
    task_id="task_123",
    thread_id="thread_456"
)

# 检查任务状态
print(result['state'])  # 'created', 'running', 或 'completed'
```

## 输出结果

精修完成后返回的结果字典包含：

```python
{
    'rwp': 12.34,                           # 最终 Rwp 值
    'cell_params': [...],                    # 晶胞参数
    'output_files': [...],                   # 生成的文件列表
    'refined_cif_files': [...],              # 精修后的 CIF 文件
    'data_quality': {                        # 数据质量信息
        'total_points': 6089,
        'zero_calc_points': 2,
        'calc_range': [0.0, 33.64],
        'obs_range': [1.28, 295.38]
    }
}
```

## 精修流程说明

### 初始化流程（创建新项目时）
1. 创建新的 GSAS-II 项目
2. 清理数据文件中的 NaN 值
3. 添加中子粉末衍射数据
4. 设置时间范围限制
5. 添加晶体结构
6. 设置精修控制参数
7. 执行初始化计算

### 加载已有项目时
1. 加载指定的 GPX 文件
2. 获取项目中的 histogram 和 phases
3. 验证数据完整性
4. 直接进入精修流程

### 精修流程
1. 根据 True/False 配置构建精修字典
2. 一次性执行所有启用的精修参数
3. 导出精修结果（图表、CIF 文件等）

## 示例场景

### 场景1: 完整的新项目精修
```python
results = neutron_refinement(
    neutron_data="data.gsa",
    neutron_inst="inst.instprm",
    cif_files=["structure.cif"],
    output_dir="./output",
    refine_background=True,
    refine_cell=True,
    refine_scale=True,
    refine_instrument=True,
    refine_atoms=True,
    use_constraints=True
)
```

### 场景2: 只精修特定参数
```python
results = neutron_refinement(
    neutron_data="data.gsa",
    neutron_inst="inst.instprm",
    cif_files=["structure.cif"],
    output_dir="./output",
    refine_background=False,  # 跳过背景
    refine_cell=True,         # 只精修晶胞
    refine_scale=False,       # 跳过标度因子
    refine_instrument=False,  # 跳过仪器参数
    refine_atoms=True,        # 精修原子
    use_constraints=True
)
```

### 场景3: 继续精修已有项目
```python
# 第一次精修
results1 = neutron_refinement(
    neutron_data="data.gsa",
    neutron_inst="inst.instprm",
    cif_files=["structure.cif"],
    output_dir="./output1",
    refine_background=True,
    refine_cell=True,
    use_constraints=True
)

# 使用第一次精修的结果继续精修其他参数
results2 = neutron_refinement(
    gpx_file="./output1/comprehensive_refinement.gpx",  # 加载之前的结果
    output_dir="./output2",
    refine_instrument=True,  # 继续精修仪器参数
    refine_atoms=True,       # 和原子参数
    use_constraints=True
)
```

## 日志和输出

精修过程会生成详细的日志文件：
- `refinement.log` - 完整的精修日志
- `neutron_refinement_data_verified.csv` - 验证后的数据
- `neutron_refinement_plot_verified.png` - 精修拟合图
- `Phase_N_structure_params.txt` - 各相的结构参数
- `*_gsas_refined.cif` - 精修后的 CIF 文件

## 注意事项

1. **默认所有精修参数都是 False**，需要明确设置为 True 才会执行
2. **使用 gpx_file 时**，可以省略 neutron_data、neutron_inst 和 cif_files 参数
3. **创建新项目时**，必须提供 neutron_data、neutron_inst 和 cif_files 参数
4. 精修过程会自动保存结果到 `comprehensive_refinement.gpx`
5. 每个精修步骤都有详细的进度日志输出

## 故障排查

### 问题: 精修返回 None
**原因**: 函数缺少返回语句
**解决**: 已修复，确保使用最新版本

### 问题: GPX 文件加载失败
**原因**: GPX 文件路径不存在或文件损坏
**解决**: 检查文件路径，确保文件完整

### 问题: 内存不足 (Killed)
**原因**: 数据文件过大或系统内存不足
**解决**:
- 检查可用内存: `free -h`
- 使用更少的精修参数
- 在内存更大的节点上运行

## 版本历史

- **v2.0** (2025-12-10):
  - 改用 True/False 开关控制精修参数
  - 一次性精修所有启用的参数
  - 新增支持加载已有 GPX 项目
  - 添加详细的进度日志
  - 修复返回值问题

- **v1.0**: 原始版本（使用 [order, cycles] 控制）

# GSAS-II 中子精修高级参数指南

## 概述

本脚本现在支持所有 GSAS-II 中子粉末衍射精修参数，提供两种使用模式：
1. **基础模式**：简单的 True/False 开关，适合快速使用
2. **高级模式**：精细控制每个参数，适合专业用户

## 支持的所有精修参数

### 1. 背景参数 (Background)
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `refine_background` | bool | False | 是否精修背景 |
| `background_coeffs` | int | 3 | 背景函数系数数量 |

**GSAS-II 对应**:
- Background function
- Number of coeff

### 2. Limits 参数
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `refine_limits` | bool | False | 是否精修时间范围限制 |

**GSAS-II 对应**:
- Original Tmin
- Original Tmax

### 3. 仪器参数 (Instrument Parameters)

#### 3.1 整体控制
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `refine_instrument` | bool | False | 整体精修仪器参数(X, Y, alpha, beta, sig) |

#### 3.2 单独控制
| 参数 | 类型 | 默认值 | GSAS-II 对应 | 说明 |
|------|------|--------|--------------|------|
| `refine_instrument_difc` | bool | False | difC | 衍射常数 C |
| `refine_instrument_difa` | bool | False | difA | 衍射常数 A |
| `refine_instrument_difb` | bool | False | difB | 衍射常数 B |
| `refine_instrument_zero` | bool | False | Zero | 零点偏移 |
| `refine_instrument_alpha` | bool | False | alpha | 角度相关峰宽参数 |
| `refine_instrument_beta` | bool | False | beta-0, beta-1, beta-q | 各向异性峰形参数 |
| `refine_instrument_sig` | bool | False | sig-0, sig-1, sig-2, sig-q | 峰宽分布参数 |
| `refine_instrument_x` | bool | False | X | 仪器几何参数 X |
| `refine_instrument_y` | bool | False | Y | 仪器几何参数 Y |
| `refine_instrument_z` | bool | False | Z | 仪器几何参数 Z |

### 4. 样品参数 (Sample Parameters)
| 参数 | 类型 | 默认值 | GSAS-II 对应 | 说明 |
|------|------|--------|--------------|------|
| `refine_scale` | bool | False | scale | 标度因子 |
| `refine_absorption` | bool | False | absorption | 吸收参数 |
| `refine_sample_displacement` | bool | False | DisplaceX, DisplaceY | 样品位移 |

### 5. 晶胞参数 (Unit Cell)
| 参数 | 类型 | 默认值 | GSAS-II 对应 | 说明 |
|------|------|--------|--------------|------|
| `refine_cell` | bool | False | Unit cell | 晶胞参数 (a, b, c, α, β, γ) |

### 6. 原子参数 (Atoms)

#### 6.1 整体控制
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `refine_atoms` | bool | False | 整体精修原子参数(位置+温度因子+占位) |

#### 6.2 单独控制
| 参数 | 类型 | 默认值 | GSAS-II 标签 | 说明 |
|------|------|--------|-------------|------|
| `refine_atoms_pos` | bool | False | X | 原子位置 (fractional coordinates) |
| `refine_atoms_uiso` | bool | False | U | 各向同性温度因子 |
| `refine_atoms_occ` | bool | False | F | 原子占位度 |

### 7. 高级参数 (Advanced)
| 参数 | 类型 | 默认值 | GSAS-II 对应 | 说明 |
|------|------|--------|--------------|------|
| `refine_size` | bool | False | Domain size model, size | 晶粒尺寸模型和尺寸 |
| `refine_mustrain` | bool | False | Mustrain model, microstrain | 微应变模型和微应变 |
| `refine_phase_fraction` | bool | False | Phase fraction | 多相精修中的相分数 |

## 使用示例

### 示例 1: 基础模式 - 快速精修
```python
from 0neutron_gsas_refine import neutron_refinement

# 简单的基础精修
results = neutron_refinement(
    neutron_data="data.gsa",
    neutron_inst="inst.instprm",
    cif_files=["structure.cif"],
    output_dir="./output",
    # 基础参数
    refine_background=True,
    refine_cell=True,
    refine_scale=True,
    refine_instrument=True,  # 整体仪器参数
    refine_atoms=True,       # 整体原子参数
)
```

### 示例 2: 高级模式 - 精细控制仪器参数
```python
# 只精修特定的仪器参数
advanced_config = {
    'refine_background': True,
    'background_coeffs': 5,  # 使用5个背景系数
    'refine_cell': True,
    'refine_scale': True,

    # 单独精修特定的仪器参数
    'refine_instrument_zero': True,   # 只精修Zero
    'refine_instrument_alpha': True,  # 和alpha
    'refine_instrument_beta': True,   # 和beta参数
    # 不精修其他仪器参数
}

results = neutron_refinement(
    neutron_data="data.gsa",
    neutron_inst="inst.instprm",
    cif_files=["structure.cif"],
    output_dir="./output",
    advanced_config=advanced_config
)
```

### 示例 3: 高级模式 - 精细控制原子参数
```python
# 只精修原子位置和温度因子,不精修占位
advanced_config = {
    'refine_background': True,
    'refine_cell': True,
    'refine_scale': True,

    # 原子参数单独控制
    'refine_atoms_pos': True,    # 精修原子位置
    'refine_atoms_uiso': True,   # 精修温度因子
    'refine_atoms_occ': False,   # 不精修占位
}

results = neutron_refinement(
    neutron_data="data.gsa",
    neutron_inst="inst.instprm",
    cif_files=["structure.cif"],
    output_dir="./output",
    advanced_config=advanced_config
)
```

### 示例 4: 高级模式 - 包含晶粒尺寸和微应变
```python
# 精修晶粒尺寸和微应变
advanced_config = {
    'refine_background': True,
    'refine_cell': True,
    'refine_scale': True,
    'refine_instrument': True,
    'refine_atoms': True,

    # 高级参数
    'refine_size': True,         # 精修晶粒尺寸
    'refine_mustrain': True,     # 精修微应变
}

results = neutron_refinement(
    neutron_data="data.gsa",
    neutron_inst="inst.instprm",
    cif_files=["structure.cif"],
    output_dir="./output",
    advanced_config=advanced_config
)
```

### 示例 5: 高级模式 - 完整精修所有参数
```python
# 精修所有可用参数
advanced_config = {
    # 基础参数
    'refine_background': True,
    'background_coeffs': 6,
    'refine_cell': True,
    'refine_scale': True,
    'refine_absorption': True,

    # 所有仪器参数
    'refine_instrument_difc': True,
    'refine_instrument_difa': True,
    'refine_instrument_difb': True,
    'refine_instrument_zero': True,
    'refine_instrument_alpha': True,
    'refine_instrument_beta': True,
    'refine_instrument_sig': True,
    'refine_instrument_x': True,
    'refine_instrument_y': True,
    'refine_instrument_z': True,

    # 所有原子参数
    'refine_atoms_pos': True,
    'refine_atoms_uiso': True,
    'refine_atoms_occ': True,

    # 样品参数
    'refine_sample_displacement': True,

    # 高级参数
    'refine_size': True,
    'refine_mustrain': True,
    'refine_phase_fraction': True,  # 多相时使用
}

results = neutron_refinement(
    neutron_data="data.gsa",
    neutron_inst="inst.instprm",
    cif_files=["structure.cif"],
    output_dir="./output",
    advanced_config=advanced_config
)
```

### 示例 6: 继续精修已有项目
```python
# 加载已有gpx文件,只精修特定参数
advanced_config = {
    'refine_instrument_zero': True,
    'refine_instrument_alpha': True,
    'refine_atoms_pos': True,
}

results = neutron_refinement(
    gpx_file="existing_project.gpx",  # 加载已有项目
    output_dir="./output_refined",
    advanced_config=advanced_config
)
```

## 参数组合建议

### 建议 1: 初次精修流程
```python
# 第一步: 精修背景和晶胞
results1 = neutron_refinement(
    ...,
    refine_background=True,
    refine_cell=True
)

# 第二步: 加载第一步结果,精修标度和仪器参数
results2 = neutron_refinement(
    gpx_file="output1/comprehensive_refinement.gpx",
    refine_scale=True,
    refine_instrument=True
)

# 第三步: 精修原子参数
results3 = neutron_refinement(
    gpx_file="output2/comprehensive_refinement.gpx",
    refine_atoms=True
)
```

### 建议 2: 峰形优化
```python
# 专注于峰形参数
advanced_config = {
    'refine_instrument_alpha': True,
    'refine_instrument_beta': True,
    'refine_instrument_sig': True,
    'refine_size': True,
    'refine_mustrain': True,
}
```

### 建议 3: 结构优化
```python
# 专注于结构参数
advanced_config = {
    'refine_cell': True,
    'refine_atoms_pos': True,
    'refine_atoms_uiso': True,
}
```

## 注意事项

1. **参数依赖关系**:
   - 精修原子位置前建议先精修晶胞参数
   - 精修微应变和晶粒尺寸时建议先精修峰形参数

2. **整体 vs 单独控制**:
   - 设置 `refine_instrument=True` 会精修常用的仪器参数组合
   - 如果需要更精细的控制,使用 `refine_instrument_xxx` 单独设置
   - 同样适用于原子参数 (`refine_atoms` vs `refine_atoms_xxx`)

3. **基础模式 vs 高级模式**:
   - 基础模式适合快速精修和标准流程
   - 高级模式适合需要精细控制的复杂情况
   - 高级模式的 `advanced_config` 会覆盖基础参数

4. **性能考虑**:
   - 同时精修过多参数可能导致收敛困难
   - 建议分步精修:先精修背景和晶胞,再精修仪器参数,最后精修原子参数

5. **多相精修**:
   - 使用 `refine_phase_fraction=True` 精修相分数
   - 需要在cif_files中提供多个结构文件

## 完整参数清单

### 支持的所有参数(31个)

**基础参数 (6个)**:
1. refine_background
2. background_coeffs (数值,非布尔)
3. refine_cell
4. refine_scale
5. refine_absorption
6. refine_sample_displacement

**仪器参数 (11个)**:
7. refine_instrument (整体)
8. refine_instrument_difc
9. refine_instrument_difa
10. refine_instrument_difb
11. refine_instrument_zero
12. refine_instrument_alpha
13. refine_instrument_beta
14. refine_instrument_sig
15. refine_instrument_x
16. refine_instrument_y
17. refine_instrument_z

**原子参数 (4个)**:
18. refine_atoms (整体)
19. refine_atoms_pos
20. refine_atoms_uiso
21. refine_atoms_occ

**高级参数 (4个)**:
22. refine_limits
23. refine_size
24. refine_mustrain
25. refine_phase_fraction

**其他**:
26. use_constraints (控制收敛标准)
27. gpx_file (加载已有项目)

## 与 GSAS-II GUI 的对应关系

| 本脚本参数 | GSAS-II GUI 位置 |
|-----------|-----------------|
| refine_background | Data → Background → refine |
| refine_cell | General → Unit cell → refine |
| refine_scale | Sample Parameters → Scale |
| refine_instrument_xxx | Instrument Parameters → [specific param] |
| refine_atoms_xxx | Atoms → [select atoms] → refine X/U/F |
| refine_size | Data → Size → refine |
| refine_mustrain | Data → Mustrain → refine |

## 故障排查

### 问题 1: 精修不收敛
**解决方案**:
- 减少同时精修的参数数量
- 分步精修,从背景和晶胞开始
- 检查初始模型是否合理

### 问题 2: 某些参数精修失败
**解决方案**:
- 检查日志中的警告信息
- 确保初始值合理
- 尝试先固定该参数,精修其他参数后再释放

### 问题 3: Rwp 反而变差
**解决方案**:
- 检查是否释放了过多参数
- 某些参数可能相关性太强
- 使用分步精修策略

## 版本信息

- **当前版本**: v3.1 (2025-12-11)
- **新增功能**:
  - 支持所有 GSAS-II 中子粉末衍射精修参数
  - 基础模式和高级模式双模式支持
  - 参数单独控制和整体控制
  - 31个可配置参数
  - 增强的flexible_neutron_refinement函数支持完整的参数控制
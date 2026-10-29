# ImageAngle 图片量角器 · 开发方案（定稿版 v1）

> 项目目录：`D:\Doubao\image angle`
> 基线：UI 草图 v2（已评审定稿）· 日期：2026-10-29
> 状态：方案定稿，待批准后进入 P1 开发

## 1. 项目目标

口腔全景片（曲面断层片）牙齿近远中轴倾角手动测量工具，替代 ImageJ 等通用软件的低效操作。核心目标：**同一操作者多次测量、不同操作者之间测量结果的一致性**，固化测量规范（固定参考线、排除根尖区、近中为正符号约定），支持批量输出结构化数据用于后续分析。

## 2. 已定稿决策（v2 评审确认）

| # | 决策项 | 定稿内容 |
|---|--------|----------|
| 1 | 方向约定 | **放射学惯例（患者右侧 = 图像左侧）**；工具栏提供「镜像」按钮纠正异常导入；导出文件头记录约定 |
| 2 | 未画参考线 | 允许画牙长轴并记录，但角度**留空（空白结果）**，不临时计算；画好参考线后**自动补算**全部空白牙角度并提示 |
| 3 | 置信度 | 默认空；列表点击循环 空→高→中→低；导出留空不伪造数据（可选一键「全部设为中」） |
| 4 | 覆盖策略 | 重复序号/牙位 → 覆盖 + toast 提示 + 可撤销（无模态弹窗） |
| 5 | 序号 | 每图从 1 开始；合并导出含 image_file + image_index |
| 6 | 参考线定义 | 腭中缝优先；不可辨时按操作者判断。参考线类型下拉记录（腭中缝/竖直/其他），随导出头输出 |
| 7 | 未填牙位 | 按图像左右给临时符号（等价规则：**牙冠偏向图像中线方向 = 近中 = 正**），结果栏提示「未填牙位，正负号需人工确认」，导出 note 注明 |
| 8 | 图片格式 | JPG / JPEG / PNG / TIFF / BMP；v1 不支持 DICOM |
| 9 | 技术栈 | Python 3.10+ · PySide6（GUI）· OpenCV（图像读取/合成测试）；pytest 测试 |

## 2.1 系统要求（Win 10 / Win 11）

- **Windows 10（64 位，建议版本 ≥ 1809）与 Windows 11（64 位）均支持**；Python 3.10+（64 位）、PySide6 6.x、OpenCV 4.x。
- Qt6 默认启用高 DPI 缩放，4K / 高分屏正常显示；界面文字走系统字体栈（微软雅黑等）。
- 无需管理员权限，不依赖外部命令行工具；单机离线可用。
| 10 | 22% 根尖回退 | **显示约定 + 协议参数**（默认 22%，可配置），不影响角度数值（回退点与原根→冠连线共线） |
| 11 | 异常值 | \|角度\|>30° 列表标色，导出 note 注明「异常值待复核」；阈值可配置 |
| 12 | 参考线角度 | 随图导出 summary（参考线方向、牙数、均值/极值），用于 QC |

## 3. 项目结构

```
ImageAngle/
├── app/
│   ├── __init__.py
│   ├── main.py               # 入口：QApplication + 主窗口
│   ├── ui/
│   │   ├── main_window.py    # 主窗口：工具栏 / 画布 / 结果栏装配
│   │   ├── canvas.py         # 画布：缩放平移 / 画线 / 端点拖拽 / 选中高亮 / 放大镜
│   │   └── result_panel.py   # 结果栏：当前测量卡（三态）+ 列表 + 双向联动 + 置信度循环
│   ├── model/
│   │   ├── session.py        # Session / ImageData / Tooth 模型 + JSON 自动保存
│   │   ├── angle.py          # 角度计算纯函数（核心逻辑，可单测）
│   │   └── protocol.py       # 协议常量：方向约定 / 参考线类型 / 置信度取值
│   └── io/
│       ├── image_loader.py   # 图片读取与尺寸信息
│       └── csv_export.py     # CSV 导出（UTF-8 BOM + 元数据头 + 原始坐标）
├── tests/
│   ├── test_angle.py         # 角度计算单元测试
│   ├── test_golden.py        # 合成金标准图端到端测试
│   └── test_session.py       # 会话保存/恢复/覆盖去重
├── docs/
│   └── 使用说明.md            # 解剖定义、方向约定、全景片局限、双操作者流程
├── resources/                # 图标等
├── session.json              # 运行时自动保存（gitignore）
├── CHANGELOG.md
├── requirements.txt          # PySide6, opencv-python, pytest
└── .gitignore
```

## 4. 数据模型

### Session（一个文件夹 = 一个会话）
```json
{
  "protocol_version": 1,
  "software_version": "0.1.0",
  "direction_convention": "radiological",
  "reference_definition": "palatal_midline",
  "apex_exclusion_pct": 22,
  "operator_id": "",
  "patient_id": "",
  "images": { "<图片绝对路径>": { "...ImageData" } }
}
```

### ImageData
```json
{
  "file": "P20261029_001.jpg",
  "width": 3000,
  "height": 1200,
  "flipped": false,
  "reference": { "x1": 0, "y1": 0, "x2": 0, "y2": 0, "type": "palatal_midline" },
  "teeth": [ { "...Tooth" } ]
}
```

### Tooth
```json
{
  "seq": 1,
  "fdi": "",
  "root": { "x": 0, "y": 0 },
  "crown": { "x": 0, "y": 0 },
  "angle_deg": null,
  "direction": null,
  "confidence": "",
  "note": ""
}
```
- `angle_deg`：参考线缺失时为 `null`（空白结果）；参考线存在时为由 `angle.py` 算出的带符号角度。
- `confidence`：`""` | `高` | `中` | `低`。
- `note`：自动标注「未填牙位」「异常值待复核」等。

## 5. 角度计算规则（angle.py）

- 输入：`root`、`crown`（像素坐标）、参考线两点、`flipped`、`fdi`（可空）。
- 方向角：`ref = atan2(y2-y1, x2-x1)`；`axis = atan2(crown.y-root.y, crown.x-root.x)`。
- 差角并归一化到 [-90, 90]：`d = ((axis - ref + 90) mod 180) - 90`（消除两线相交的双角度歧义）。
- 符号（基准 = 放射学惯例，图像左侧为患者右侧）：
  - 已填 FDI：`1x / 4x`（图像左半侧）冠偏向图像右侧 = 近中 = 正；`2x / 3x`（图像右半侧）冠偏向图像左侧 = 近中 = 正。
  - 未填 FDI：临时符号 = 牙冠偏向图像中线方向为正（等价于上述规则），结果栏提示人工确认。
- `flipped = true` 时先对坐标做镜像（`x' = width-1-x`）再计算。
- 无参考线：返回 `None`（不计算，空白结果）。

## 6. 界面定稿（以草图 v2 为准）

- **工具栏**（顺序即操作流程）：打开图片 → 打开文件夹 → 画参考线（完成后变「重画参考线」）→ 画牙长轴 → 镜像 → 撤销 → 删除 → 上一张 / 下一张 → 导出 CSV。
- **画布**：深色底；滚轮缩放（10%~800%）、拖拽平移、适应窗口；取点放大镜 2× + 十字线；线选中高亮置顶；端点手柄拖拽实时更新角度；参考线拖动 → 全量重算。
- **结果栏**：当前测量卡（三态：空白结果 / 测量中 / 完成）+ 已测列表（# 牙位 角度 方向 置信度 删）+ 底部统计；行 ↔ 线双向联动；置信度点击循环；异常行标红。
- **快捷键**：R 参考线 / T 牙长轴 / Ctrl+Z 撤销 / Del 删除 / ←→ 切图 / Esc 取消当前线 / Enter 确认。
- **状态条**：未打开图片 / 未画参考线（提示 + 空白结果）/ 测量中 / 完成态。

## 7. CSV 输出格式

UTF-8 **带 BOM**（Excel 中文不乱码）。每行一颗牙，含原始坐标（可复核、可重算）：

```
# ImageAngle Export v1
# software_version: 0.1.0
# protocol_version: 1
# direction_convention: radiological
# reference_definition: palatal_midline
# apex_exclusion_pct: 22
# operator_id:
# exported_at: 2026-10-29T10:30:00+08:00
patient_id,image_file,image_index,seq,tooth_fdi,axis_inclination_deg,direction,confidence,note,ref_x1,ref_y1,ref_x2,ref_y2,root_x,root_y,crown_x,crown_y,image_width,image_height
```
- 空白牙：`axis_inclination_deg` 留空，`note` 注明「无参考线」。
- 未填牙位：`tooth_fdi` 留空，`note` 注明「未填牙位，符号未经象限确认」。
- 导出入口：导出当前图 / 导出全部（按图分组，`image_index` 区分，每图 seq 独立从 1 开始）。

## 8. 阶段计划（P0–P5，任务级）

| 阶段 | 内容 | 验收标准 |
|------|------|----------|
| P0 | Python 环境、requirements、项目结构、git 初始化、CHANGELOG | 项目可运行空窗口 |
| P1 | 打开图片、画布（缩放/平移/放大镜）、画参考线、画牙长轴、角度计算 + 单元测试、当前测量卡三态 | 单图完成 参考线+1 颗牙测量，角度正确，无参考线显示空白 |
| P2 | 多记录列表、删除、按图撤销栈、端点拖拽、双向联动、置信度循环 | 编辑闭环：画/改/删/撤销全部可用 |
| P3 | session.json 自动保存/恢复、文件夹遍历、上一张/下一张、沿用参考线、patient_id/操作者、镜像按钮 | 批量切换不丢数据，崩溃可恢复 |
| P4 | CSV 导出（当前/全部 + 元数据头 + 坐标）、异常标记、参考线 summary | 导出文件 Excel 打开无乱码，字段与坐标完整 |
| P5 | 金标准合成图测试、双操作者一致性流程、使用说明定稿 | 端到端误差 ≤0.5°，双人差值/ICC 流程可执行 |

## 9. 测试与验证

- `test_angle.py`：四象限符号（16/26/36/46 各方向）、归一化边界（±90）、镜像翻转、临时符号规则、无参考线返回 None。
- `test_golden.py`：OpenCV 合成已知角度线图，端到端测量误差 ≤ 0.5°。
- `test_session.py`：保存/恢复、重复牙位覆盖去重、自动保存触发。
- 双操作者一致性：两人各测同一组全景片，导出对比差值分布 / ICC，写入使用说明附录。
- 交付前以 UI 草图 v2 逐项核对布局与交互。

## 10. 已知限制与说明

- 全景片为曲面断层投影，存在区域放大率与几何形变，测量值为**投影角而非解剖真值**，使用说明注明。
- 22% 根尖回退为显示与协议约定，不改变角度数值。
- 显示方向以放射学惯例为基准；镜像按钮用于纠正 JPEG 等无元数据图片的方向异常。
- patient_id 由文件夹/会话级录入（默认取文件夹名或文件名前缀，可改），每图沿用。

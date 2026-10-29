"""协议常量与可配置参数。"""
from __future__ import annotations

# 显示方向约定：放射学惯例（患者右侧 = 图像左侧）
DIRECTION_CONVENTION_RADIOLOGICAL = 'radiological'
DIRECTION_CONVENTION_DISPLAY = '放射学惯例（患者右侧 = 图像左侧）'

# 参考线类型
DEFAULT_REFERENCE_DEFINITION = 'palatal_midline'
REFERENCE_TYPES = ('palatal_midline', 'vertical', 'other')
REFERENCE_TYPES_ZH = {
    'palatal_midline': '腭中缝',
    'vertical': '竖直方向',
    'other': '其他',
}

# 置信度取值：空 / 高 / 中 / 低（点击循环）
CONFIDENCE_LEVELS = ('', '高', '中', '低')

# 异常值阈值（可配置，默认 |角度| > 30°）
EXCEPTION_THRESHOLD_DEG = 30.0

# 根尖回退比例（显示约定 + 协议参数，不影响角度数值）
APEX_EXCLUSION_PCT = 22.0

# 支持的图片格式（v1 不含 DICOM）
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp')

# FDI 牙位：恒牙 11-18 / 21-28 / 31-38 / 41-48，乳牙 51-55 / 61-65 / 71-75 / 81-85。
# 第二位 1 开始，不代表「0 号牙」，所以不能用 10-48 这种区间一把抓。
_FDI_RANGES = (
    ('1', '8'), ('2', '8'), ('3', '8'), ('4', '8'),   # 恒牙象限 1-4，牙位 1-8
    ('5', '5'), ('6', '5'), ('7', '5'), ('8', '5'),   # 乳牙象限 5-8，牙位 1-5
)


def is_valid_fdi(text: str) -> bool:
    """牙号是否合法（两位 FDI 编号）。空串也算合法＝「暂不填」。"""
    s = (text or '').strip()
    if not s:
        return True
    if len(s) != 2 or not s.isdigit():
        return False
    quad, idx = s[0], s[1]
    for q, hi in _FDI_RANGES:
        if quad == q:
            return '1' <= idx <= hi
    return False


# note 自动标注
NOTE_NO_REFERENCE = '无参考线'
NOTE_NO_FDI = '未填牙位，侧别按图像位置判定'
NOTE_OUTLIER = '异常值待复核'
NOTE_FDI_CONFLICT = '牙位与图像位置不符，请确认片子左右或牙位'
NOTE_SIDE_UNKNOWN = '牙根落在参考线上，看不出左右侧'

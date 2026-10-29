"""角度计算核心（纯函数，可单元测试）。

约定：
- 图像坐标系：x 向右、y 向下（像素坐标）。
- 显示方向约定：放射学惯例（患者右侧 = 图像左侧）。
- 牙长轴固定按「牙根 → 牙冠」点击。

方向（近中 / 远中）判定分两步，互不干扰：

1. **左右侧**：牙根落在参考线的哪一侧（有向距离 s，用叉积算）。
   牙在图像左侧（患者右侧）→ 近中朝右；在右侧 → 近中朝左。
   有向距离与「用参考线哪个端点」无关：把端点沿该线平移不改变叉积的符号，
   所以参考线从上往下画、从下往上画，结果完全一样。
   前提是参考线大致竖直（偏离 < 45°）；画成接近水平时「左/右」退化成
   「前/后」，此时按「侧别未知」处理，交给牙位判定。

2. **牙冠偏向**：dx = crown.x − root.x。
   这是唯一与「牙轴朝上还是朝下」无关的横向量，因此上颌牙、下颌牙用
   **同一套规则**，不需要分别处理。

    近中 = dx 的方向与「朝中线」的方向一致 → 正，否则负。

为什么不用「牙轴角度 − 参考线角度」的符号：
`normalize_deg` 把差折进 [-90°, 90°] 时，会把「牙轴朝上」和「牙轴朝下」
折叠成同一条直线，方向信息在这一步丢失。同一个差值符号，在牙轴朝上时
表示「牙冠偏右」、在朝下时表示「牙冠偏左」。v1.0 用这个符号判方向却没补
上下颌，导致上颌牙（FDI 1x/2x）全部反号、下颌牙（3x/4x）反而正确。
dx 没有这个折叠问题，所以本实现不再使用角度差的符号。

上下颌（jaw）由「牙冠在牙根的哪一侧」自动判定（上颌冠在下、下颌冠在上），
只用于象限命名与牙位一致性校验，**不参与方向计算**：判定表里上颌行与
下颌行的规则完全相同。

牙位（FDI）也不是必需的：侧别既能从参考线几何算，也能从牙位首位算。
**几何优先**——牙在线的哪一侧是图像上直接看得见的事实，不依赖人工输入，
所以输错牙位不会污染结果。牙位只在两种情况派上用场：几何判不出（牙根压
在线上、参考线接近水平）时兜底；与几何矛盾时提示「片子可能左右反了」。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

# 小于这个角度视为「牙轴竖直」，不标近中/远中
DEAD_BAND_DEG = 0.5
# 牙根到参考线的有向距离（像素）小于它 → 认为压在线上，侧别不可判
ONLINE_EPS_PX = 2.0
# 牙冠相对牙根的水平偏移小于它 → 方向不可判（亚像素抖动）
FLAT_EPS_PX = 0.5


class Point:
    """不可变二维点。"""

    __slots__ = ('x', 'y')

    def __init__(self, x: float, y: float):
        self.x = float(x)
        self.y = float(y)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Point):
            return NotImplemented
        return self.x == other.x and self.y == other.y

    def __repr__(self) -> str:
        return f'Point({self.x}, {self.y})'


@dataclass(frozen=True)
class MeasureResult:
    """一次测量的完整结论。"""

    angle_deg: float
    direction: Optional[str]      # '近中' / '远中' / None（竖直或方向不可判）
    side: str                     # 'left' / 'right' / 'unknown'（图像侧）
    jaw: str                      # 'upper' / 'lower' / 'unknown'
    quadrant: Optional[str]       # 'upper_left' 等；任一维未知时为 None
    conflict: bool                # 牙位与图像位置矛盾


def _wrap180(d: float) -> float:
    """将角度折回 (-180, 180]。"""
    d = d % 360.0
    if d > 180.0:
        d -= 360.0
    return d


def normalize_deg(d: float) -> float:
    """归一化到 [-90, +90]，消除两条线相交产生两个夹角的歧义。

    注意：这个折叠会丢失「这条线朝哪一端」的信息，所以只用于**幅值**，
    不能用来判方向（见模块文档）。
    """
    d = _wrap180(d)
    if d > 90.0:
        d -= 180.0
    elif d < -90.0:
        d += 180.0
    return d


def axis_deg(root: Point, crown: Point) -> float:
    """牙长轴方向角（根 → 冠），度数。"""
    return math.degrees(math.atan2(crown.y - root.y, crown.x - root.x))


def reference_deg(p1: Point, p2: Point) -> float:
    """参考线方向角（p1 → p2），度数。"""
    return math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))


def mirror_x(p: Point, width: float) -> Point:
    """以图像中线为轴做水平镜像（纠正历史会话里的 flipped 数据）。"""
    return Point(width - 1.0 - p.x, p.y)


# ---------- 牙位 ----------

def fdi_side(fdi: str) -> Optional[str]:
    """FDI 牙位 → 图像侧：'left'（1x/4x，患者右侧）/'right'（2x/3x，患者左侧）。"""
    s = (fdi or '').strip()
    if len(s) != 2 or not s.isdigit():
        return None
    q = s[0]
    if q in ('1', '4', '5', '8'):
        return 'left'
    if q in ('2', '3', '6', '7'):
        return 'right'
    return None


def fdi_jaw(fdi: str) -> Optional[str]:
    """FDI 牙位 → 上下颌：1x/2x/5x/6x 上颌，3x/4x/7x/8x 下颌。"""
    s = (fdi or '').strip()
    if len(s) != 2 or not s.isdigit():
        return None
    q = s[0]
    if q in ('1', '2', '5', '6'):
        return 'upper'
    if q in ('3', '4', '7', '8'):
        return 'lower'
    return None


# ---------- 参考线几何 ----------

def reference_baseline(p1: Point, p2: Point) -> Optional[Tuple[Point, Point, Tuple[float, float]]]:
    """把参考线规整成 (下端点, 上端点, 单位方向向量)。

    端点顺序与点击顺序无关：y 大的那个当「下端」。线退化成点（两点重合）
    时返回 None。
    """
    d, u = (p1, p2) if p1.y >= p2.y else (p2, p1)
    dx, dy = u.x - d.x, u.y - d.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    return d, u, (dx / length, dy / length)


def reference_side(point: Point, p1: Point, p2: Point) -> Optional[float]:
    """点相对参考线的有向距离。

    < 0 图像左侧，> 0 图像右侧；参考线退化时返回 None。
    与「用哪个端点」无关（同一条线上的点给出相同符号）。
    """
    base = reference_baseline(p1, p2)
    if base is None:
        return None
    d, _u, (ux, uy) = base
    return ux * (point.y - d.y) - uy * (point.x - d.x)


def reference_is_level(p1: Point, p2: Point) -> bool:
    """参考线是否接近水平（偏竖直超过 45°）——此时「左右侧」失去意义。"""
    base = reference_baseline(p1, p2)
    if base is None:
        return True
    _d, _u, (ux, uy) = base
    return abs(ux) > abs(uy)


# ---------- 上下颌 ----------

def jaw_of_axis(root: Point, crown: Point, eps: float = FLAT_EPS_PX) -> str:
    """由牙轴朝向判上下颌：牙冠在牙根下方 = 上颌，上方 = 下颌。

    全景片中上颌牙冠朝下、下颌牙冠朝上，且标注固定「先根后冠」，所以这一
    判断不依赖牙位，也不需要用户输入。牙轴水平（冠根等高）时判不出。
    """
    if crown.y > root.y + eps:
        return 'upper'
    if crown.y < root.y - eps:
        return 'lower'
    return 'unknown'


def _side_of(root: Point, p1: Point, p2: Point, fdi: str) -> Tuple[str, bool]:
    """返回 (侧别, 是否与牙位矛盾)。

    几何优先：牙在参考线哪一侧是图像上直接看得见的事实，不依赖人工输入，
    输错牙位也不会污染结果。牙位只做两件事——几何判不出时兜底、与几何
    矛盾时提示（提示片子可能左右反了，或牙位填错）。
    """
    geom = 'unknown'
    if not reference_is_level(p1, p2):
        s = reference_side(root, p1, p2)
        if s is not None:
            if s < -ONLINE_EPS_PX:
                geom = 'left'
            elif s > ONLINE_EPS_PX:
                geom = 'right'

    from_fdi = fdi_side(fdi)
    if geom != 'unknown':
        return geom, (from_fdi is not None and from_fdi != geom)
    if from_fdi is not None:
        return from_fdi, False
    return 'unknown', False


# ---------- 主计算 ----------

def measure(
    root: Point,
    crown: Point,
    ref_p1: Optional[Point],
    ref_p2: Optional[Point],
    width: float,
    fdi: str = '',
    flipped: bool = False,
) -> MeasureResult:
    """计算倾角、方向、象限与矛盾标记。无参考线时抛 ValueError。"""
    if ref_p1 is None or ref_p2 is None:
        raise ValueError('measure() 需要参考线；无参考线请先判空')

    if flipped:
        root, crown = mirror_x(root, width), mirror_x(crown, width)
        ref_p1, ref_p2 = mirror_x(ref_p1, width), mirror_x(ref_p2, width)

    base = reference_baseline(ref_p1, ref_p2)
    if base is None:
        return MeasureResult(0.0, None, 'unknown', 'unknown', None, False)
    d, u, _vec = base

    side, conflict = _side_of(root, ref_p1, ref_p2, fdi)
    jaw = jaw_of_axis(root, crown)
    from_fdi_jaw = fdi_jaw(fdi)
    if from_fdi_jaw and jaw != 'unknown' and from_fdi_jaw != jaw:
        conflict = True

    # 幅值：牙轴相对参考线的夹角（临床读数，与方向解耦）
    mag = abs(normalize_deg(axis_deg(root, crown) - reference_deg(d, u)))

    dx = crown.x - root.x
    direction: Optional[str] = None
    if side != 'unknown' and abs(dx) >= FLAT_EPS_PX and mag >= DEAD_BAND_DEG:
        near_right = (side == 'left')
        direction = '近中' if (dx > 0) == near_right else '远中'

    if mag < DEAD_BAND_DEG:
        angle = 0.0
    elif direction is None:
        angle = round(mag, 2)       # 方向不可判：只给幅值，不臆造正负
    else:
        angle = round(mag if direction == '近中' else -mag, 2)

    quadrant = f'{jaw}_{side}' if jaw != 'unknown' and side != 'unknown' else None
    return MeasureResult(angle, direction, side, jaw, quadrant, conflict)


def compute_angle(
    root: Point,
    crown: Point,
    ref_p1: Optional[Point],
    ref_p2: Optional[Point],
    width: float,
    fdi: str = '',
    flipped: bool = False,
) -> Optional[float]:
    """带符号倾角（近中为正）。无参考线返回 None。

    只取数值时用这个；需要方向/象限请直接用 `measure()`。
    """
    if ref_p1 is None or ref_p2 is None:
        return None
    return measure(root, crown, ref_p1, ref_p2, width, fdi, flipped).angle_deg


def apex_retreat_point(root: Point, crown: Point, pct: float) -> Point:
    """沿长轴（根 → 冠）将牙根点回退 pct%（显示约定，不影响角度数值）。"""
    pct = float(pct) / 100.0
    dx = crown.x - root.x
    dy = crown.y - root.y
    return Point(root.x + pct * dx, root.y + pct * dy)

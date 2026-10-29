"""角度计算单元测试：归一化、四象限方向规则、牙位兜底、镜像、边界。"""
import pytest

from app.model.angle import (
    Point,
    apex_retreat_point,
    compute_angle,
    fdi_jaw,
    fdi_side,
    measure,
    normalize_deg,
    reference_side,
)

# 竖直参考线（腭中缝），中线 x=200，图宽 400
REF = (Point(200, 380), Point(200, 20))
W = 400


def test_normalize_deg():
    assert normalize_deg(0) == 0
    assert normalize_deg(30) == 30
    assert normalize_deg(150) == -30
    assert normalize_deg(-150) == 30
    assert normalize_deg(179) == -1
    assert normalize_deg(-179) == 1
    assert normalize_deg(90) == 90
    assert normalize_deg(-90) == -90
    assert normalize_deg(270) == -90
    assert normalize_deg(360) == 0


def test_no_reference_returns_none():
    assert compute_angle(Point(100, 100), Point(120, 50), None, None, 400) is None


# 图像左侧 = 患者右侧（FDI 1x 上颌 / 4x 下颌）：牙冠偏右 = 朝中线 = 近中
# 图像右侧 = 患者左侧（FDI 2x 上颌 / 3x 下颌）：牙冠偏左 = 朝中线 = 近中
# 上下颌两行规则完全相同 —— 这正是旧实现（只用角度差）出错的地方
@pytest.mark.parametrize('fdi,root,crown,want', [
    ('11', Point(100, 150), Point(120, 250), '近中'),   # 左·上颌
    ('11', Point(100, 150), Point(80, 250), '远中'),
    ('41', Point(100, 250), Point(120, 150), '近中'),   # 左·下颌
    ('41', Point(100, 250), Point(80, 150), '远中'),
    ('21', Point(300, 150), Point(280, 250), '近中'),   # 右·上颌
    ('21', Point(300, 150), Point(320, 250), '远中'),
    ('31', Point(300, 250), Point(280, 150), '近中'),   # 右·下颌
    ('31', Point(300, 250), Point(320, 150), '远中'),
])
def test_four_quadrants(fdi, root, crown, want):
    res = measure(root, crown, *REF, W, fdi)
    assert res.direction == want
    assert (res.angle_deg > 0) == (want == '近中')
    assert abs(abs(res.angle_deg) - 11.31) < 0.05


def test_upper_and_lower_share_same_rule():
    """同一几何，只换上下颌（1x ↔ 4x），符号必须相同。"""
    upper = measure(Point(100, 150), Point(120, 250), *REF, W, '11')
    lower = measure(Point(100, 250), Point(120, 150), *REF, W, '41')
    assert upper.angle_deg == lower.angle_deg > 0
    assert upper.jaw == 'upper' and lower.jaw == 'lower'


def test_quadrant_names():
    assert measure(Point(100, 150), Point(120, 250), *REF, W, '11').quadrant == 'upper_left'
    assert measure(Point(100, 250), Point(120, 150), *REF, W, '41').quadrant == 'lower_left'
    assert measure(Point(300, 150), Point(280, 250), *REF, W, '21').quadrant == 'upper_right'
    assert measure(Point(300, 250), Point(280, 150), *REF, W, '31').quadrant == 'lower_right'


def test_without_fdi_uses_geometry():
    """不填牙位也能判对：牙在参考线哪一侧是几何事实。"""
    left = measure(Point(100, 250), Point(120, 150), *REF, W, '')
    right = measure(Point(300, 250), Point(280, 150), *REF, W, '')
    left_upper = measure(Point(100, 150), Point(120, 250), *REF, W, '')
    assert left.side == 'left' and left.direction == '近中'
    assert right.side == 'right' and right.direction == '近中'
    assert left_upper.side == 'left' and left_upper.direction == '近中'
    assert left_upper.jaw == 'upper'          # 冠在下方 → 上颌，无需输入


def test_fdi_conflict_keeps_geometry_and_flags():
    """牙位与图像位置矛盾时按几何算，但标记 conflict（提示片子可能左右反）。"""
    res = measure(Point(100, 250), Point(120, 150), *REF, W, '21')
    assert res.side == 'left'          # 几何优先
    assert res.direction == '近中'
    assert res.conflict is True


def test_fdi_fills_in_when_geometry_unknown():
    """牙根压在参考线上判不出侧别时，由牙位兜底。"""
    res = measure(Point(200, 250), Point(220, 150), *REF, W, '11')
    assert res.side == 'left'
    assert res.direction == '近中'


def test_tooth_on_line_without_fdi_has_no_direction():
    res = measure(Point(200, 250), Point(220, 150), *REF, W, '')
    assert res.side == 'unknown'
    assert res.direction is None
    assert res.angle_deg > 0          # 幅值仍给出，只是不臆造方向


def test_reference_direction_independent_of_endpoint():
    """参考线从上往下画 / 从下往上画，结果完全一致。"""
    a = measure(Point(100, 250), Point(120, 150), Point(200, 380), Point(200, 20), W, '41')
    b = measure(Point(100, 250), Point(120, 150), Point(200, 20), Point(200, 380), W, '41')
    assert a == b


def test_reference_side_sign():
    """有向距离：左侧为负、右侧为正；用任一端点算都一样。"""
    left = reference_side(Point(100, 200), *REF)
    right = reference_side(Point(300, 200), *REF)
    assert left is not None and left < 0
    assert right is not None and right > 0
    assert left == reference_side(Point(100, 200), REF[1], REF[0])


def test_degenerate_reference_line():
    p = Point(50, 50)
    res = measure(Point(100, 250), Point(120, 150), p, p, W, '41')
    assert res.angle_deg == 0.0
    assert res.direction is None


def test_flipped_equals_manually_mirrored():
    """flipped 只是把旧会话里的镜像坐标还原：结果应等于「手工镜像后再算」。"""
    a = compute_angle(Point(100, 100), Point(120, 50), Point(0, 0), Point(0, 100), 400, '16',
                      flipped=True)
    # 图宽 400：x → 399 − x
    b = compute_angle(Point(299, 100), Point(279, 50), Point(399, 0), Point(399, 100), 400, '16')
    assert a is not None and b is not None
    assert abs(a - b) < 1e-9
    assert a < 0          # 还原后牙冠偏左（远离中线）→ 远中


def test_parallel_axis_zero():
    a = compute_angle(Point(100, 100), Point(100, 50), Point(0, 0), Point(0, 100), 400, '16')
    assert a == 0


def test_vertical_tooth_has_no_direction():
    res = measure(Point(100, 100), Point(100, 50), Point(0, 0), Point(0, 100), 400, '16')
    assert res.angle_deg == 0
    assert res.direction is None


def test_horizontal_reference_ninety():
    # 参考线水平时，竖直牙轴相对参考 = 90°（方向未知，只给幅值）
    a = compute_angle(Point(100, 100), Point(100, 50), Point(0, 50), Point(100, 50), 400, '16')
    assert a is not None and abs(abs(a) - 90) < 1e-6


def test_fdi_side():
    assert fdi_side('16') == 'left'
    assert fdi_side('46') == 'left'
    assert fdi_side('26') == 'right'
    assert fdi_side('36') == 'right'
    assert fdi_side('55') == 'left'      # 乳牙左上限
    assert fdi_side('85') == 'left'      # 乳牙右下限
    assert fdi_side('65') == 'right'
    assert fdi_side('') is None
    assert fdi_side('6') is None
    assert fdi_side('5x') is None


def test_fdi_jaw():
    assert fdi_jaw('16') == 'upper' and fdi_jaw('26') == 'upper'
    assert fdi_jaw('36') == 'lower' and fdi_jaw('46') == 'lower'
    assert fdi_jaw('55') == 'upper' and fdi_jaw('85') == 'lower'
    assert fdi_jaw('') is None


def test_apex_retreat_point():
    # 沿根→冠回退 22%：共线，方向不变
    r = apex_retreat_point(Point(0, 0), Point(100, 0), 22.0)
    assert r.x == 22.0 and r.y == 0.0
    r2 = apex_retreat_point(Point(0, 0), Point(60, 80), 22.0)
    assert abs(r2.x - 13.2) < 1e-6 and abs(r2.y - 17.6) < 1e-6

"""金标准端到端测试：合成图已知角度 → 测量误差 ≤ 0.5°。

图像由 scripts/make_sample_panoramic.py 生成：
- 竖直参考线（x=800）
- 牙 1（480,320）轴线 +15° → 预期 +15.0°
- 牙 2（1120,320）轴线 -10° → 按右半侧规则预期 +10.0°
"""
import math
import os

from app.io.image_loader import image_size, load_image
from app.model.angle import Point, compute_angle

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'resources', 'sample_panoramic.png')


def _axis_points(cx, cy, angle_deg, r=160.0):
    rad = math.radians(angle_deg)
    root = Point(cx - r * math.sin(rad), cy + r * math.cos(rad))
    crown = Point(cx + r * math.sin(rad), cy - r * math.cos(rad))
    return root, crown


def test_golden_sample_within_half_degree():
    img = load_image(RES)
    w, h = image_size(img)
    assert (w, h) == (1600, 700)

    ref1, ref2 = Point(800, 60), Point(800, 640)
    root1, crown1 = _axis_points(480, 320, 15.0)
    a1 = compute_angle(root1, crown1, ref1, ref2, w, '16')
    assert a1 is not None
    assert abs(a1 - 15.0) <= 0.5, f'牙1 测量 {a1}，预期 15.0'

    root2, crown2 = _axis_points(1120, 320, -10.0)
    a2 = compute_angle(root2, crown2, ref1, ref2, w, '26')
    assert a2 is not None
    assert abs(a2 - 10.0) <= 0.5, f'牙2 测量 {a2}，预期 10.0'

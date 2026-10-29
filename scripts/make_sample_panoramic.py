"""生成合成示例全景片（用于开发调试与金标准测试）。

画布 1600 × 700，深色底；牙弓弧 + 14 颗牙刻度；
竖直参考线（腭中缝，x=800）；
两条已知角度的牙长轴：
- 牙 1 位于左半侧（480, 320），轴线 +15°（冠偏右 = 近中）
- 牙 2 位于右半侧（1120, 320），轴线 -10°（冠偏左 = 近中）

测量预期：牙 1 ≈ +15.0°，牙 2 ≈ +10.0°（按放射学惯例 + 竖直参考线）。

用 Pillow 绘制（不再依赖 OpenCV，见 requirements.txt）。
"""
from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageDraw

W, H = 1600, 700
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'resources', 'sample_panoramic.png')


def _jaw_arc():
    pts = []
    for t in np.linspace(0.0, 1.0, 200):
        x = 200 + 1200 * t
        y = 480 - 260 * math.sin(math.pi * t)
        pts.append((int(x), int(y)))
    return pts


def _draw_tooth(draw, cx, cy, angle_deg, color):
    rad = math.radians(angle_deg)
    r = 160
    root = (cx - r * math.sin(rad), cy + r * math.cos(rad))
    crown = (cx + r * math.sin(rad), cy - r * math.cos(rad))
    draw.line([root, crown], fill=color, width=6)
    for (x, y), c in ((root, (40, 200, 140)), (crown, (90, 230, 160))):
        draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=c)


def main(out: str = OUT) -> None:
    img = Image.new('RGB', (W, H), (18, 18, 18))
    draw = ImageDraw.Draw(img)

    draw.line(_jaw_arc(), fill=(100, 110, 130), width=6, joint='curve')
    for t in np.linspace(0.05, 0.95, 14):
        x = 200 + 1200 * t
        y = 480 - 260 * math.sin(math.pi * t)
        draw.line([(x, y - 14), (x, y + 14)], fill=(150, 160, 180), width=5)
    draw.line([(800, 60), (800, 640)], fill=(220, 230, 245), width=3)   # 竖直参考线

    _draw_tooth(draw, 480, 320, 15.0, (210, 120, 120))    # 牙 1：+15°
    _draw_tooth(draw, 1120, 320, -10.0, (90, 170, 220))   # 牙 2：-10°

    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    print(f'已生成示例全景片: {out}')
    print('预期（竖直参考线）：牙1 ≈ +15.0°（近中）；牙2 ≈ +10.0°（近中）')


if __name__ == '__main__':
    main()

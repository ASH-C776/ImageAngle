"""生成 ImageAngle 应用图标（resources/icon.ico + 预览 PNG）。

图形语义：一条竖直参考线 + 一条倾斜牙长轴 + 两者之间的角度弧 —— 就是软件里每颗牙
在量角时画的那三样东西。底色用品牌薄荷绿、符号用深墨色（与「导出CSV」按钮同一对
配色），缩到 16px 时仍能看出「一个角」。

用法：py scripts/make_icon.py
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

SIZE = 1024
GREEN = (34, 203, 168, 255)
INK = (6, 43, 35, 255)
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _line(draw, p1, p2, width, fill):
    """带圆头的线段（PIL 的 line 默认是平头，端点会显得被切掉）。"""
    draw.line([p1, p2], fill=fill, width=width)
    for x, y in (p1, p2):
        r = width // 2
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def build(size: int = SIZE) -> Image.Image:
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 1024.0

    # 圆角底：Windows 图标自带圆角裁切，这里留一点内边距避免被切到
    pad = int(40 * s)
    radius = int(210 * s)
    d.rounded_rectangle([pad, pad, size - pad, size - pad],
                        radius=radius, fill=GREEN)

    w = int(54 * s)
    apex = (int(486 * s), int(812 * s))
    # 竖直参考线
    _line(d, (apex[0], int(228 * s)), apex, w, INK)
    # 倾斜牙长轴（约 30° 偏离竖直）
    _line(d, apex, (int(834 * s), int(220 * s)), w, INK)
    # 角度弧：从竖直方向扫到牙轴方向。半径要比线宽大不少，否则弧被两条线吞掉，
    # 缩到 32px 就成了一个「小横杠」。
    r = int(330 * s)
    box = [apex[0] - r, apex[1] - r, apex[0] + r, apex[1] + r]
    d.arc(box, start=-86, end=-64, fill=INK, width=int(30 * s))

    # 顶点补一个小圆，让两条线交汇处干净
    dot = int(22 * s)
    d.ellipse([apex[0] - dot, apex[1] - dot, apex[0] + dot, apex[1] + dot], fill=INK)
    return img


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    res = os.path.join(root, 'resources')
    os.makedirs(res, exist_ok=True)

    big = build()
    png = os.path.join(res, 'icon.png')
    big.save(png)
    ico = os.path.join(res, 'icon.ico')
    big.save(ico, format='ICO', sizes=[(n, n) for n in ICO_SIZES])
    print('saved', png, os.path.getsize(png), 'bytes')
    print('saved', ico, os.path.getsize(ico), 'bytes')

    # 小尺寸预览：确认 16/32px 下还能认出形状
    strip = Image.new('RGBA', (sum(ICO_SIZES) + 20 * len(ICO_SIZES), 256 + 40), (24, 24, 24, 255))
    x = 0
    for n in ICO_SIZES:
        small = big.resize((n, n), Image.LANCZOS)
        strip.paste(small, (x, 20), small)
        x += n + 20
    prev = os.path.join(root, '_shots', 'icon_preview.png')
    os.makedirs(os.path.dirname(prev), exist_ok=True)
    strip.save(prev)
    print('saved', prev)


if __name__ == '__main__':
    main()

"""Offscreen 渲染结果栏（单卡：当前测量 + 已测记录），验证排版与对齐。

用法：python tools/preview_panel.py
输出：tools/preview_panel_<theme>_<w>.png
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFontDatabase, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from app.model.session import Tooth
from app.ui import theme
from app.ui.result_panel import ResultPanel

HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_OLD = '"Segoe UI", "Microsoft YaHei UI", system-ui, -apple-system, sans-serif'
_FONT_NEW = '"Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", sans-serif'


def _load_fonts() -> None:
    for fn in ("msyh.ttc", "msyhbd.ttc", "simsun.ttc", "simhei.ttf", "msyhl.ttc"):
        p = os.path.join("C:/Windows/Fonts", fn)
        if os.path.isfile(p):
            QFontDatabase.addApplicationFont(p)


def _teeth() -> list[Tooth]:
    data = [
        (1, '26', 14.8, '高'), (2, '16', -4.2, '高'), (3, '11', 3.1, '中'),
        (4, '36', -28.4, ''), (5, '46', 41.6, '低'), (6, '', -2.0, ''),
    ]
    out = []
    for seq, fdi, ang, conf in data:
        out.append(Tooth(seq=seq, fdi=fdi, angle_deg=ang, confidence=conf,
                         direction=('近中' if ang >= 0 else '远中')))
    return out


def render(theme_name: str, width: int, height: int, current_seq: int | None,
           suffix: str = '') -> str:
    theme.set_theme(theme_name)
    app = QApplication.instance()
    app.setStyleSheet(theme.build_qss().replace(_FONT_OLD, _FONT_NEW))

    panel = ResultPanel()
    panel.setFixedSize(width, height)
    teeth = _teeth()
    if current_seq is None:
        panel.show_blank('')
        panel.refresh_list([], None)
        panel.set_status('no_image.png · 无图片')
    else:
        cur = next(t for t in teeth if t.seq == current_seq)
        panel.show_result(cur)
        panel.refresh_list(teeth, cur.seq)
        panel.set_status('panorama_20261029.png · 2924 × 1462')
    panel.show()
    for _ in range(3):
        app.processEvents()

    pix = QPixmap(panel.size())
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    panel.render(p, QPoint(0, 0))
    p.end()
    out = os.path.join(HERE, f'preview_panel_{theme_name}_{width}{suffix}.png')
    pix.save(out)
    print('saved', out)
    panel.close()
    return out


def main() -> int:
    app = QApplication(sys.argv)
    _load_fonts()
    render('dark', 400, 720, 4)
    render('light', 400, 720, 4)
    render('dark', 336, 620, 2)
    render('dark', 400, 720, None, 'blank')
    return 0


if __name__ == '__main__':
    sys.exit(main())

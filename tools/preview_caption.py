"""Offscreen 渲染：打开示例全景片，检查画布左下角文件名浮层。

用法：QT_QPA_PLATFORM=offscreen py tools/preview_caption.py
输出 tools/preview_caption_dark.png / _light.png（整窗 + 左下角放大图）。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFontDatabase, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from app.ui import theme
from app.ui.main_window import MainWindow

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IMG = os.path.join(ROOT, 'resources', 'sample_panoramic.png')


def _load_fonts() -> None:
    for fn in ("msyh.ttc", "msyhbd.ttc", "msyhl.ttc"):
        p = os.path.join("C:/Windows/Fonts", fn)
        if os.path.isfile(p):
            QFontDatabase.addApplicationFont(p)


def render(app: QApplication, theme_name: str) -> None:
    theme.set_theme(theme_name)
    w = MainWindow()
    theme.set_theme(theme_name)      # 覆盖持久化偏好
    w._apply_theme()
    w.resize(1240, 780)
    w.setMinimumSize(1240, 780)
    w.show()
    app.processEvents()
    w._open_path(IMG)
    for _ in range(3):
        app.processEvents()
        time.sleep(0.2)
    print('caption =', repr(w.canvas.caption()), '| panel status visible =',
          w.panel._status.isVisible())

    pix = QPixmap(w.size())
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    w.render(p, QPoint(0, 0))
    p.end()
    out = os.path.join(HERE, f'preview_caption_{theme_name}.png')
    pix.save(out)

    g = w.canvas.geometry()
    tl = w.canvas.mapTo(w, QPoint(0, 0))
    crop = pix.copy(tl.x(), tl.y() + g.height() - 110, min(760, g.width()), 110)
    crop.scaled(crop.width() * 2, crop.height() * 2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
                ).save(out.replace('.png', '_zoom.png'))
    print('saved', out)
    w.close()


def main() -> int:
    app = QApplication(sys.argv)
    _load_fonts()
    render(app, 'dark')
    render(app, 'light')
    return 0


if __name__ == '__main__':
    sys.exit(main())

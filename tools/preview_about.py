"""离屏渲染「关于」对话框，用来目测深浅两套主题下的排版。

    py tools/preview_about.py

产物：tools/preview_about_dark.png / _light.png
不改任何用户偏好（纯渲染，不建主窗口）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QFontDatabase            # noqa: E402
from PySide6.QtWidgets import QApplication       # noqa: E402

from app.ui import theme                          # noqa: E402
from app.ui.about import AboutDialog              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_OLD = '"Segoe UI", "Microsoft YaHei UI", system-ui, -apple-system, sans-serif'
_FONT_NEW = '"Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", sans-serif'


def _load_fonts() -> None:
    """offscreen 平台不保证有中文字体，不显式加载会整屏豆腐块。"""
    for fn in ('msyh.ttc', 'msyhbd.ttc', 'simhei.ttf'):
        p = os.path.join('C:/Windows/Fonts', fn)
        if os.path.isfile(p):
            QFontDatabase.addApplicationFont(p)


def main() -> int:
    app = QApplication(sys.argv)
    _load_fonts()
    for name in ('dark', 'light'):
        theme.set_theme(name)
        app.setStyleSheet(theme.build_qss().replace(_FONT_OLD, _FONT_NEW))
        dlg = AboutDialog()
        dlg.adjustSize()
        dlg.show()
        app.processEvents()
        out = os.path.join(HERE, f'preview_about_{name}.png')
        pm = dlg.grab()
        ok = pm.save(out)
        print(f'[{name}] {pm.width()}x{pm.height()} saved={ok} -> {out}')
        dlg.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())

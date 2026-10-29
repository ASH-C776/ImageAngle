"""Offscreen 渲染 MainWindow 为 PNG，用于验证主题 / 图标 / 响应式布局。

沙箱无显示器，无法弹真窗口；本脚本用 offscreen 平台把窗口绘制成图片。
渲染三张：暗色宽屏、亮色宽屏、暗色窄屏（触发工具栏 IconOnly + 面板折叠）。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QPixmap, QFontDatabase
from PySide6.QtWidgets import QApplication

from app.ui import theme
from app.ui.main_window import MainWindow

HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_OLD = '"Segoe UI", "Microsoft YaHei UI", system-ui, -apple-system, sans-serif'
_FONT_NEW = '"Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", sans-serif'


def _load_fonts() -> None:
    for fn in ("msyh.ttc", "msyhbd.ttc", "simsun.ttc", "simhei.ttf", "msyhl.ttc"):
        p = os.path.join("C:/Windows/Fonts", fn)
        if os.path.isfile(p):
            QFontDatabase.addApplicationFont(p)


def render_one(app: QApplication, theme_name: str, width: int, height: int,
               suffix: str) -> str:
    theme.set_theme(theme_name)
    w = MainWindow()
    # MainWindow.__init__ 会按持久化偏好再设一次主题，这里强制覆盖回目标主题
    theme.set_theme(theme_name)
    w._apply_theme()
    w.resize(width, height)
    w.setMinimumSize(width, height)
    w.show()
    app.processEvents()
    time.sleep(0.35)
    app.processEvents()
    # 最后再设全局 QSS（含中文字体替换）并触发一次重算，确保 show 后重建完成、
    # 工具栏混合布局稳定、中文不 tofu，再渲染
    app.setStyleSheet(theme.build_qss().replace(_FONT_OLD, _FONT_NEW))
    for _ in range(2):
        app.processEvents()
        w._update_responsive(width, force=True)

    pix = QPixmap(w.size())
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    w.render(painter, QPoint(0, 0))
    painter.end()
    out = os.path.join(HERE, f"preview_{suffix}.png")
    ok = pix.save(out)
    print(f"[{suffix}] {theme_name} {width}x{height} saved={ok} -> {out}")
    w.close()
    return out


def main() -> int:
    app = QApplication(sys.argv)
    _load_fonts()
    render_one(app, "dark", 1280, 820, "dark")     # 暗·中屏（混合：核心按钮保文字）
    render_one(app, "light", 1700, 900, "light")  # 亮·宽屏（全图文）
    render_one(app, "dark", 920, 800, "narrow")    # 暗·窄屏（面板折叠）
    return 0


if __name__ == "__main__":
    sys.exit(main())

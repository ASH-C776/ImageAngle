"""诊断 4：修复后的端到端验证。

1) 水平扫描左右边缘，确认仍返回 HTLEFT / HTRIGHT（拖拽缩放没被废掉）
2) 用真实 WM_LBUTTONDOWN/UP 消息点击「最大化」「关闭」按钮，确认窗口真的响应
3) 真实点击画布，确认参考线两点能画出来
注意：WM_*MOUSE 的 lParam 是【物理像素】客户区坐标，需 逻辑坐标 × dpr。
"""
from __future__ import annotations

import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.model.session import ImageData
from app.ui.canvas import Canvas
from app.ui.main_window import MainWindow

user32 = ctypes.windll.user32
WM_NCHITTEST = 0x0084
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
HT = {0: 'HTNOWHERE', 1: 'HTCLIENT', 2: 'HTCAPTION', 10: 'HTLEFT',
      11: 'HTRIGHT', 12: 'HTTOP', 15: 'HTBOTTOM', 16: 'HTBOTTOMLEFT',
      17: 'HTBOTTOMRIGHT'}


class RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


def lp(x: int, y: int) -> int:
    return (x & 0xFFFF) | ((y & 0xFFFF) << 16)


def click(hwnd: int, phys_x: int, phys_y: int) -> None:
    p = lp(phys_x, phys_y)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, p)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, p)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, p)
    for _ in range(12):
        QApplication.processEvents()
        QTest.qWait(20)


def main() -> int:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1180, 760)
    w.move(80, 80)
    w.show()
    QTest.qWaitForWindowExposed(w, 2000)
    app.processEvents()

    hwnd = int(w.winId())
    dpr = w.devicePixelRatio()
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    mid_y = (r.top + r.bottom) // 2
    print(f'dpr={dpr} 物理矩形=({r.left},{r.top},{r.right},{r.bottom})')

    print('\n=== 1. 水平扫描：左右边缘还应是 HTLEFT / HTRIGHT ===')
    for dx in (2, 6, 10, 14, 20, 40, 200):
        left = int(user32.SendMessageW(hwnd, WM_NCHITTEST, 0, lp(r.left + dx, mid_y)))
        right = int(user32.SendMessageW(hwnd, WM_NCHITTEST, 0, lp(r.right - dx, mid_y)))
        print(f'  dx={dx:4} 左 {left:2}{HT.get(left, "?"):10} 右 {right:2}{HT.get(right, "?"):10}')
    bottom = int(user32.SendMessageW(hwnd, WM_NCHITTEST, 0, lp(r.left + 400, r.bottom - 6)))
    print(f'  底部 dx=6 -> {bottom} {HT.get(bottom, "?")}')

    def win_click(widget, pos_logical) -> None:
        """把控件内的逻辑坐标换算成物理客户区坐标后投递真实点击。"""
        g = widget.mapTo(w, pos_logical)
        click(hwnd, int(g.x() * dpr), int(g.y() * dpr))

    tb = w._title_bar
    max_btn = [b for b in tb._win_btns if b.text() == '□'][0]
    close_btn = [b for b in tb._win_btns if b.text() == '✕'][0]
    min_btn = [b for b in tb._win_btns if b.text() == '—'][0]

    print('\n=== 2. 真实点击「最大化」 ===')
    print('  点击前 isMaximized =', w.isMaximized())
    win_click(max_btn, max_btn.rect().center())
    print('  点击后 isMaximized =', w.isMaximized())

    print('\n=== 3. 再点一次还原 ===')
    win_click(max_btn, max_btn.rect().center())
    print('  isMaximized =', w.isMaximized(), 'geometry =', w.geometry())

    print('\n=== 4. 真实点击画布画参考线 ===')
    img = QImage(800, 400, QImage.Format.Format_RGB32)
    img.fill(0xFF202020)
    data = ImageData(file='<fake>')
    data.width, data.height = 800, 400
    w.canvas.set_image(img, data)
    w.canvas.set_mode(Canvas.MODE_REF)
    app.processEvents()
    print('  mode =', w.canvas.mode, 'has_image =', w.canvas.has_image())
    win_click(w.canvas, w.canvas.rect().center() + type(w.canvas.rect().center())(-150, -120))
    print('  第一点 _pending =', w.canvas._pending)
    win_click(w.canvas, w.canvas.rect().center() + type(w.canvas.rect().center())(150, 120))
    print('  参考线 reference =', data.reference)
    print('  结束后 mode =', w.canvas.mode)

    print('\n=== 5. 真实点击「关闭」 ===')
    win_click(close_btn, close_btn.rect().center())
    print('  窗口仍可见 =', w.isVisible())
    return 0


if __name__ == '__main__':
    sys.exit(main())

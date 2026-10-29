"""Windows 原生窗口圆角 / 边框着色（DWM）。

为什么用 DWM 而不是自己画：
- 本窗口是 `FramelessWindowHint` 的无边框窗口，客户区被标题栏、画布卡片填满，
  自己画圆角只能靠 `setMask()` 裁切 —— 边缘是硬锯齿，在 225% 缩放下尤其明显。
- Windows 11 的 DWM 直接给窗口做**抗锯齿**圆角，且由合成器完成，不参与我们的重绘，
  零性能开销、拖动缩放时也不会有残影。

限制：
- 仅 Windows 11（build ≥ 22000）有效。Win10 上 `DwmSetWindowAttribute` 返回
  E_INVALIDARG，此时函数返回 False，窗口保持直角（不做锯齿兜底，宁可不圆也不难看）。
- 最大化 / 全屏时圆角必须关掉：那些状态下窗口贴边，圆角会在屏幕边缘留下缺口。
"""
from __future__ import annotations

import ctypes

# DWMWA_WINDOW_CORNER_PREFERENCE / DWMWA_BORDER_COLOR
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_BORDER_COLOR = 34

# DWM_WINDOW_CORNER_PREFERENCE 取值
DWMWCP_DEFAULT = 0
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
DWMWCP_ROUNDSMALL = 3

# 特殊值：让 DWM 不画边框（会影响圆角描边，通常不用）
DWMWA_COLOR_NONE = 0xFFFFFFFE


def _hwnd_of(widget) -> int:
    """取顶层窗口的原生句柄（offstage / 未 show 时可能是 0）。"""
    try:
        return int(widget.window().winId())
    except Exception:
        return 0


def _colorref(hex_color: str) -> int:
    """'#RRGGBB' → COLORREF（0x00BBGGRR）。"""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def set_round_corners(widget, enabled: bool = True,
                      radius: int = DWMWCP_ROUND,
                      border_color: str | None = None) -> bool:
    """给顶层窗口开 / 关原生圆角。

    参数
    ----
    widget       : 任意属于该窗口的控件（内部取 window().winId()）
    enabled      : True=圆角；False=直角（最大化 / 全屏时传 False）
    radius       : DWMWCP_ROUND（系统标准 8px，推荐）或 DWMWCP_ROUNDSMALL
    border_color : 可选，'#RRGGBB'，DWM 会在圆角外缘描 1px 线；不传则用系统默认

    返回 True 表示 DWM 接受了设置（Windows 11），False 表示不支持（Win10 及更早）。
    """
    hwnd = _hwnd_of(widget)
    if not hwnd:
        return False
    try:
        dwm = ctypes.windll.dwmapi
    except Exception:
        return False

    pref = ctypes.c_int(radius if enabled else DWMWCP_DONOTROUND)
    hr = dwm.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd), _DWMWA_WINDOW_CORNER_PREFERENCE,
        ctypes.byref(pref), ctypes.sizeof(pref))
    if hr != 0:
        return False

    if border_color:
        col = ctypes.c_uint(_colorref(border_color))
        dwm.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), _DWMWA_BORDER_COLOR,
            ctypes.byref(col), ctypes.sizeof(col))
    return True

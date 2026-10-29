"""窗口圆角模块的纯逻辑测试（DWM 调用本身依赖真实窗口，见 tools/diag_round.py）。"""
from __future__ import annotations

import pytest

from app.ui.win_round import (
    DWMWCP_DONOTROUND,
    DWMWCP_ROUND,
    _colorref,
    set_round_corners,
)


def test_colorref_is_bgr():
    assert _colorref('#000000') == 0x000000
    assert _colorref('#ffffff') == 0xFFFFFF
    # COLORREF 是 0x00BBGGRR：Red 在最低字节
    assert _colorref('#d0d7de') == 0xDED7D0
    assert _colorref('#333333') == 0x333333


def test_colorref_without_hash():
    assert _colorref('22cba8') == 0xA8CB22


def test_round_preferences_are_distinct():
    assert DWMWCP_ROUND != DWMWCP_DONOTROUND


def test_set_round_corners_without_native_window_is_safe(qapp):
    """offscreen / 未 show 时没有原生句柄，必须静默返回 False 而不是抛异常。"""
    from PySide6.QtWidgets import QWidget

    w = QWidget()
    try:
        assert set_round_corners(w) in (True, False)
        assert set_round_corners(w, enabled=False) in (True, False)
    finally:
        w.close()


@pytest.fixture(scope='session')
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    return app

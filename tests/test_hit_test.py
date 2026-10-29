"""无边框窗口边缘命中判定（hit_test_edges）的回归测试。

这里锁死一个曾经真实炸过的坑：WM_NCHITTEST 给的是**物理像素**，而 Qt 的
frameGeometry() 是**逻辑像素**。两者混用在 225% 缩放下会让整个客户区被判成
「右边缘」，Windows 于是把每次点击当成拖拽改窗口大小 —— 表现是标题栏的
最大化/关闭按钮点不动、画布也画不了线。
"""
from __future__ import annotations

import pytest

from app.ui.main_window import (
    _HTBOTTOM,
    _HTLEFT,
    _HTRIGHT,
    hit_test_edges,
)

EDGE_LOGICAL = 7  # MainWindow._EDGE


@pytest.mark.parametrize('dpr', [1.0, 1.25, 1.5, 2.0, 2.25])
def test_center_is_client(dpr):
    """窗口正中必须是客户区（0），不能被误判成边缘。"""
    w, h = 1180 * dpr, 760 * dpr
    wx, wy = 80 * dpr, 80 * dpr
    edge = max(6.0, EDGE_LOGICAL * dpr)
    assert hit_test_edges(wx + w / 2, wy + h / 2, wx, wy, w, h, edge) == 0


@pytest.mark.parametrize('dpr', [1.0, 1.25, 1.5, 2.0, 2.25])
def test_title_bar_and_toolbar_are_client(dpr):
    """标题栏与工具栏区域必须是客户区，否则按钮收不到点击。"""
    w, h = 1180 * dpr, 760 * dpr
    wx, wy = 80 * dpr, 80 * dpr
    edge = max(6.0, EDGE_LOGICAL * dpr)
    # 标题栏中部（逻辑 y≈18）、工具栏中部（逻辑 y≈60）
    for logical_y in (18, 60):
        res = hit_test_edges(wx + w / 2, wy + logical_y * dpr, wx, wy, w, h, edge)
        assert res == 0, f'dpr={dpr} y={logical_y} 被判成 {res}'


@pytest.mark.parametrize('dpr', [1.0, 1.5, 2.25])
def test_edges_still_resize(dpr):
    """左右/底部边缘仍必须可拖拽缩放。"""
    w, h = 1180 * dpr, 760 * dpr
    wx, wy = 80 * dpr, 80 * dpr
    edge = max(6.0, EDGE_LOGICAL * dpr)
    mid_y = wy + h / 2

    assert hit_test_edges(wx + 2, mid_y, wx, wy, w, h, edge) == _HTLEFT
    assert hit_test_edges(wx + w - 2, mid_y, wx, wy, w, h, edge) == _HTRIGHT
    assert hit_test_edges(wx + w / 2, wy + h - 2, wx, wy, w, h, edge) == _HTBOTTOM
    # 左下角同时命中左 + 底
    assert hit_test_edges(wx + 2, wy + h - 2, wx, wy, w, h, edge) == (_HTLEFT | _HTBOTTOM)


def test_top_strip_delegates_to_titlebar():
    """顶部条返回 -1（交给标题栏拖动），不在这里 resize。"""
    assert hit_test_edges(500, 81, 80, 80, 1180, 760, 7) == -1
    # 顶部条之外就是客户区
    assert hit_test_edges(500, 90, 80, 80, 1180, 760, 7) == 0


def test_regression_physical_vs_logical_225():
    """回归：225% 缩放下，物理坐标点不能被当成逻辑坐标来比。"""
    dpr = 2.25
    wx, wy = 80 * dpr, 80 * dpr           # 物理左上角 (180, 180)
    w, h = 1180 * dpr, 760 * dpr          # 物理尺寸 (2655, 1710)
    edge = max(6.0, EDGE_LOGICAL * dpr)   # 15.75

    # 修复前：把物理 x 直接和逻辑宽 1180 相减，几乎所有点都 >= 1173 → HTRIGHT
    for phys_x in (1507, 2000, 2600):
        assert hit_test_edges(phys_x, 700, wx, wy, w, h, edge) == 0

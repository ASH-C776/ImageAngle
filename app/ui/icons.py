"""工具栏 SVG 图标集（重画版）。

设计约定（统一，保证系列感）：
- 24×24 视图框，1.75px 描边，圆角端点 / 圆角连接（linecap/join = round）。
- 线性图标，语义清晰、几何居中、留白均衡。
- 端点圆点用 fill="currentColor" stroke="none" 表达，随整图标换色。

工厂渲染：SVG 字符串 → QSvgRenderer → 按设备像素比放大渲染到 QPixmap，
再 setDevicePixelRatio，得到在 Retina / 4K（150%~200% 缩放）下清晰的图标。
同时生成 Normal / Disabled 两态。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

ICON_SIZE = 18
ICON_COLOR = '#c8c8c8'        # 普通态：与工具栏文字同档亮度（set_theme 会按当前主题覆盖）
ICON_COLOR_DISABLED = '#6f6f6f'
ICON_COLOR_ACTIVE = '#7cf0d8'     # 激活(checked)态：薄荷绿，与激活文字色一致

# 每个图标一个 SVG。currentColor 在渲染时被替换为 ICON_COLOR。
_SVG = {
    # 打开图片：图片/风景框（与文件夹明确区分）
    'open': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="4" width="18" height="16" rx="2.5"/>'
        '<circle cx="8.5" cy="9" r="1.6"/>'
        '<path d="M21 16l-5-5-4 4-2-2-7 6"/></svg>'
    ),
    # 文件夹
    'folder': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 6.5a2 2 0 0 1 2-2h3.5l2 2H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6.5z"/>'
        '</svg>'
    ),
    # 上一张：左箭头
    'prev': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M14 6l-6 6 6 6"/></svg>'
    ),
    # 下一张：右箭头
    'next': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M10 6l6 6-6 6"/></svg>'
    ),
    # 图片列表：三行 + 行首点
    'list': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/>'
        '<line x1="9" y1="18" x2="20" y2="18"/>'
        '<circle cx="5" cy="6" r="1.4" fill="currentColor" stroke="none"/>'
        '<circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none"/>'
        '<circle cx="5" cy="18" r="1.4" fill="currentColor" stroke="none"/></svg>'
    ),
    # 面板显隐：右边栏（外框 + 分隔线 + 右栏两条短线）
    # 与「列表」区分开：两个功能共用一个图标时，用户分不清哪个是抽屉、哪个是文件列表。
    'panel': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="4" width="18" height="16" rx="2.5"/>'
        '<line x1="14.5" y1="4" x2="14.5" y2="20"/>'
        '<line x1="16.8" y1="9" x2="18.4" y2="9"/><line x1="16.8" y1="13" x2="18.4" y2="13"/></svg>'
    ),
    # 适应窗口：四角取景框 + 中心小图（整图正好装进视图）
    'fit': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 8V5.5A2.5 2.5 0 0 1 5.5 3H8"/><path d="M16 3h2.5A2.5 2.5 0 0 1 21 5.5V8"/>'
        '<path d="M21 16v2.5A2.5 2.5 0 0 1 18.5 21H16"/>'
        '<path d="M8 21H5.5A2.5 2.5 0 0 1 3 18.5V16"/>'
        '<rect x="8" y="8" width="8" height="8" rx="1.5"/></svg>'
    ),
    # 参考线：竖直虚线 + 两端圆点
    'ref': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="12" y1="4" x2="12" y2="20" stroke-dasharray="3 3"/>'
        '<circle cx="12" cy="4" r="1.8" fill="currentColor" stroke="none"/>'
        '<circle cx="12" cy="20" r="1.8" fill="currentColor" stroke="none"/></svg>'
    ),
    # 牙长轴：竖直轴线 + 两端圆点 + 中点虚线刻度
    'tooth': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="12" y1="4" x2="12" y2="20"/>'
        '<line x1="8.5" y1="12" x2="15.5" y2="12" stroke-dasharray="2 2"/>'
        '<circle cx="12" cy="4" r="2" fill="currentColor" stroke="none"/>'
        '<circle cx="12" cy="20" r="2" fill="currentColor" stroke="none"/></svg>'
    ),
    # 撤销：左旋箭头
    'undo': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-4"/></svg>'
    ),
    # 删除：垃圾桶
    'delete': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
        '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>'
        '<path d="M10 11v6M14 11v6"/></svg>'
    ),
    # 清空：方框内 X（区别于垃圾桶）
    'clear': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="3" width="18" height="18" rx="3"/>'
        '<path d="M9 9l6 6M15 9l-6 6"/></svg>'
    ),
    # 导出 CSV：下载到托盘
    'export': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 19h16"/></svg>'
    ),
    # 关于：圆圈里的 i（与窗口控制同规格，18px 下仍可辨）
    'about': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="8.5"/>'
        '<path d="M12 11.2v5"/>'
        '<circle cx="12" cy="7.9" r="1.05" fill="currentColor" stroke="none"/></svg>'
    ),
    # 主题切换：对比度（左空右实的半圆，明暗两套主题下都清晰）
    'contrast': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="8.5"/>'
        # 只填右半圆（弧 + 直线闭合），左半留白 —— 之前两个弧都顺时针导致整圆被填实成黑点
        '<path d="M12 3.5A8.5 8.5 0 0 1 12 20.5Z" fill="currentColor" stroke="none"/>'
        '</svg>'
    ),
    # ---- 窗口控制（与工具栏同规格：24 视图框 / 1.75 描边 / 圆角端点）----
    # 最小化：一条水平线
    'win_min': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M5.5 12.5h13"/></svg>'
    ),
    # 最大化：单方框
    'win_max': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="5.5" y="5.5" width="13" height="13" rx="1.6"/></svg>'
    ),
    # 还原：前后两个错位方框（前左下、后右上，错开约 4px 才不粘连）
    'win_restore': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3.5" y="9.2" width="10.4" height="10.4" rx="1.5"/>'
        '<path d="M9.8 9.2V7.2a1.6 1.6 0 0 1 1.6-1.6H18a1.6 1.6 0 0 1 1.6 1.6v6.6'
        'a1.6 1.6 0 0 1-1.6 1.6h-.8"/></svg>'
    ),
    # 关闭：叉
    'win_close': (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>'
    ),
}


def _dpr() -> float:
    """取当前主屏设备像素比（高 DPI / 4K / 缩放屏）。"""
    try:
        screen = QApplication.primaryScreen()
        if screen is not None:
            return float(max(1.0, screen.devicePixelRatio()))
    except Exception:
        pass
    return 1.0


def _render(svg: str, color: str, size: int, dpr: float) -> QPixmap:
    svg_colored = svg.replace('currentColor', color)
    px = max(1, int(round(size * dpr)))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer = _renderer(svg_colored)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def _renderer(svg: str):
    from PySide6.QtSvg import QSvgRenderer
    return QSvgRenderer(svg.encode('utf-8'))


def get_icon(name: str, color: str | None = None, size: int | None = None) -> QIcon:
    """返回带 Normal / Disabled / 激活(On) 三态的 QIcon（DPI 感知）。

    工具栏可勾选工具（参考线 / 牙轴）在 checked 时自动使用
    State.On 的浅蓝图标，与激活态背景、文字色形成一致反馈。

    `color` / `size` 用于窗口控制这类需要自定义前景色与尺寸的场景
    （例如关闭按钮 hover 在红底上要换成白色图标）。
    """
    svg = _SVG[name]
    dpr = _dpr()
    base = color or ICON_COLOR
    px_size = size or ICON_SIZE
    icon = QIcon()
    icon.addPixmap(_render(svg, base, px_size, dpr),
                   QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_render(svg, color or ICON_COLOR_ACTIVE, px_size, dpr),
                   QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(
        _render(svg, ICON_COLOR_DISABLED, px_size, dpr), QIcon.Mode.Disabled)
    return icon

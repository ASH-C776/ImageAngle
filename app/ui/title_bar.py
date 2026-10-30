"""自定义标题栏：标题 + 工具栏位 + 主题切换 + 窗口控制，暗色/亮色一体化。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from . import theme
from .icons import get_icon

# 图标规格与工具栏保持一致：24 视图框 / 1.75 描边；窗口按钮用 16px 更贴合窗口控件习惯
WIN_ICON_SIZE = 16
THEME_ICON_SIZE = 17
BTN_W, BTN_H = 40, 30       # 窗口控制按钮：统一尺寸，等间距
THEME_BTN_W = 34


class _IconButton(QPushButton):
    """纯图标按钮：hover / pressed 时把图标换成更亮的同色系版本。

    QIcon 只有 Normal/Disabled/On 三态，没有 hover 态，所以这里手动换图。
    """

    def __init__(self, icon_name: str, parent: QWidget | None = None,
                 size: int = WIN_ICON_SIZE) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_size = size
        self._normal = '#a6a6a6'
        self._hover = '#ffffff'
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self._apply_icon(hovered=False)

    def set_colors(self, normal: str, hover: str) -> None:
        self._normal, self._hover = normal, hover
        self._apply_icon(hovered=self.underMouse())

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self._apply_icon(hovered=self.underMouse())

    def _apply_icon(self, hovered: bool) -> None:
        color = self._hover if hovered else self._normal
        self.setIcon(get_icon(self._icon_name, color, self._icon_size))

    def enterEvent(self, e) -> None:
        self._apply_icon(hovered=True)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._apply_icon(hovered=False)
        super().leaveEvent(e)


class TitleBar(QWidget):
    """一体化标题栏：左侧标题 + 中间工具栏位 + 右侧主题切换 + 窗口控制。

    无边框窗口下承担拖拽移动与最小化 / 最大化 / 关闭。
    主题切换按钮点击后通过 on_theme_toggle 回调通知主窗口（避免循环依赖）。

    底部分割线由本控件的 paintEvent 整行绘制 —— 之前挂在 QToolBar 上，
    只画到工具栏宽度，右侧按钮下方是断的。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(38)
        self.on_theme_toggle = None  # 由主窗口注入
        self._drag_pos: QPoint | None = None
        self._state_hooked = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 6, 0)
        lay.setSpacing(2)

        self.title = QLabel('ImageAngle')
        lay.addWidget(self.title)

        # 标题与右侧按钮之间的弹性留白（工具栏由主窗口 addToolBar 挂在标题栏下方）
        lay.addStretch(1)

        # 主题切换按钮（对比度图标）
        self.theme_btn = _IconButton('contrast', size=THEME_ICON_SIZE)
        self.theme_btn.setFixedSize(THEME_BTN_W, BTN_H)
        self.theme_btn.setToolTip('切换深色 / 浅色主题')
        self.theme_btn.clicked.connect(self._on_theme_clicked)
        lay.addWidget(self.theme_btn)

        # 主题切换与窗口控制之间的留白
        lay.addSpacing(6)

        # 窗口控制按钮：图标 + 统一尺寸
        self.btn_min = _IconButton('win_min')
        self.btn_max = _IconButton('win_max')
        self.btn_close = _IconButton('win_close')
        for btn, tip, slot in ((self.btn_min, '最小化', self._min),
                               (self.btn_max, '最大化', self._max),
                               (self.btn_close, '关闭', self._close)):
            btn.setFixedSize(BTN_W, BTN_H)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            lay.addWidget(btn)
        self.btn_close.setObjectName('closeWinBtn')

        self._win_btns = [self.btn_min, self.btn_max, self.btn_close]

        # 整行底部分割线：独立 1px 控件并 raise_() 到最上层。
        # 不能只在 paintEvent 里画 —— 子控件（QToolBar 会填充自己的背景）会盖住它，
        # 这正是之前「按钮下方那截线是断的」的原因。
        self._bottom_line = QFrame(self)
        self._bottom_line.setFixedHeight(1)
        self._bottom_line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.refresh_theme()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._bottom_line.setGeometry(0, self.height() - 1, self.width(), 1)
        self._bottom_line.raise_()

    # ---------- 交互 ----------

    def _on_theme_clicked(self) -> None:
        if callable(self.on_theme_toggle):
            self.on_theme_toggle()

    def _min(self) -> None:
        self.window().showMinimized()

    def _max(self) -> None:
        w = self.window()
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()

    def _close(self) -> None:
        self.window().close()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        # 窗口拿到原生句柄后挂状态变化，最大化/还原（含 Win+↑、双击标题）都能同步图标
        if not self._state_hooked:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.windowStateChanged.connect(self.sync_maximized)
                self._state_hooked = True
        self.sync_maximized()

    def sync_maximized(self, *_args) -> None:
        """最大化时把「方框」换成「双框还原」图标。"""
        is_max = self.window().isMaximized()
        name = 'win_restore' if is_max else 'win_max'
        if self.btn_max._icon_name != name:
            self.btn_max.set_icon_name(name)
        self.btn_max.setToolTip('还原' if is_max else '最大化')

    # ---------- 样式 ----------

    def refresh_theme(self) -> None:
        """用当前主题重设标题栏与所有子按钮样式。"""
        self._bottom_line.setStyleSheet(
            f'background:{theme.C_BORDER};border:none;')
        # 软件名是主标题，必须是最强的文字层级：主文字色 + 700 字重 + 13px。
        # 之前用 C_TEXT3（第三档灰）配 12px，看起来像禁用的辅助文字，几乎看不见。
        self.title.setStyleSheet(
            f'color:{theme.C_TEXT};font-size:13px;font-weight:700;'
            f'letter-spacing:.2px;padding-right:8px;background:transparent;')
        self.update()

        self.theme_btn.setStyleSheet(
            f'QPushButton{{background:transparent;border:none;border-radius:6px;}}'
            f'QPushButton:hover{{background:{theme.C_BTN_HOVER};}}'
            f'QPushButton:pressed{{background:{theme.C_BTN_PRESS};}}')
        self.theme_btn.set_colors(theme.C_TOOL_TEXT, theme.C_TEXT)

        for btn in (self.btn_min, self.btn_max):
            btn.setStyleSheet(
                f'QPushButton{{background:transparent;border:none;border-radius:6px;}}'
                f'QPushButton:hover{{background:{theme.C_BTN_HOVER};}}'
                f'QPushButton:pressed{{background:{theme.C_BTN_PRESS};}}')
            btn.set_colors(theme.C_TOOL_TEXT, theme.C_TEXT)

        # 关闭键：hover 是红底，图标必须翻白，否则几乎看不见
        self.btn_close.setStyleSheet(
            f'QPushButton{{background:transparent;border:none;border-radius:6px;}}'
            f'QPushButton:hover{{background:{theme.C_DANGER};}}'
            f'QPushButton:pressed{{background:{theme.C_DANGER};}}')
        self.btn_close.set_colors(theme.C_TOOL_TEXT, '#ffffff')

    # ---------- 绘制 / 拖拽 ----------

    def paintEvent(self, e) -> None:
        # 背景铺满整行（底线由 _bottom_line 负责，见 __init__ 注释）
        p = QPainter(self)
        p.fillRect(self.rect(), theme.C_BG)
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (e.globalPosition().toPoint()
                              - self.window().frameGeometry().topLeft())

    def mouseMoveEvent(self, e) -> None:
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e) -> None:
        self._drag_pos = None

    def mouseDoubleClickEvent(self, e) -> None:
        self._max()

"""结果栏：单卡「测量记录」。

一张卡内上下两段：
  ① 当前测量 —— 编号 / 牙号 / 角度 三个字段（牙号可直接编辑）；
  ② 已测记录 —— 同列宽的表格化列表，与上方字段列对齐。

样式统一从 theme 模块动态读取，切换主题时由 refresh_theme() 重设卡片背景，
并由主窗口 _refresh_panel() 重建内容，从而实时跟随深 / 亮主题。
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..model.protocol import EXCEPTION_THRESHOLD_DEG
from ..model.session import Tooth
from . import theme
from .theme import F_CAP, F_SM

# ---------- 列宽（编号 / 牙号 / 角度 / 方向）----------
# 「置信」列已移除（纯手工点选的标记，无自动推断、临床意义有限）。
# 四列不再各给死宽度，而是按权重瓜分整行剩余宽度：面板拉宽时四列一起变宽，
# 不会出现「左边几列挤成一坨、右边一大片空白」的样子。
# 表头与数据行必须用同一组权重 + 同一 PAD_L / GAP，否则列头会错位。
COL_WEIGHTS = (10, 10, 15, 13)   # 角度 / 方向里的内容更长，多给一点
GAP = 8           # 列间距（原来 6，偏紧）
PAD_L = 12        # 内容左右内边距（表头与数据行必须一致）
W_DEL = 22        # 行尾删除按钮的方框边长
DEL_GAP = 4       # 删除按钮与方向列之间的留白


# ---------- 样式构造（函数化，延迟取值，跟随 theme.C_*）----------
def _transparent() -> str:
    return 'background:transparent;border:none;'


def _style_card() -> str:
    # 用 ID 选择器，避免 QFrame 类型选择器向下污染卡片内的行 / 分组框
    return (f'QFrame#resultCard{{background:{theme.C_SURFACE};'
            f'border:1px solid {theme.C_BORDER};border-radius:10px;}}')


def _style_title() -> str:
    return (f'color:{theme.C_TEXT};font-size:{F_SM + 1}px;font-weight:600;'
            f'letter-spacing:.01em;{_transparent()}')


def _style_count() -> str:
    # 与表头同档（原来用第三档灰，在暗底上几乎看不清条数）
    return f'color:{theme.C_TEXT2};font-size:{F_CAP}px;{_transparent()}'


def _style_caption() -> str:
    """卡片内小标题（当前测量）。"""
    return (f'color:{theme.C_ACCENT_INK};font-size:{F_CAP}px;font-weight:600;'
            f'letter-spacing:.02em;{_transparent()}')


def _style_field_label() -> str:
    return f'color:{theme.C_TEXT2};font-size:{F_CAP}px;{_transparent()}'


def _style_field_value(color: Optional[str] = None) -> str:
    return (f'color:{color or theme.C_TEXT};font-size:15px;font-weight:600;'
            f'{_transparent()}')


def _style_angle_value(color: str, size: int = 19) -> str:
    return f'color:{color};font-size:{size}px;font-weight:700;{_transparent()}'


def _style_head_cell(align: str = 'l') -> str:
    a = {'l': 'left', 'r': 'right', 'c': 'center'}.get(align, 'left')
    return (f'color:{theme.C_TEXT2};font-size:{F_CAP}px;'
            f'letter-spacing:.04em;text-align:{a};{_transparent()}')


def _style_head_band() -> str:
    # 1px 透明边框是刻意加的：数据行有 1px 边框（选中态才上色），
    # 边框会吃掉行内 2px 内容宽度。表头不补这 1px，四列的 x 就会整体差 1~3px。
    return (f'QFrame#headBand{{background:{theme.C_HOVER};'
            f'border:1px solid transparent;border-radius:5px;}}')


def _style_sep() -> str:
    return f'background:{theme.C_BORDER};border:none;'


def _style_cur_box() -> str:
    """当前测量块：主色淡淡的一层，表示「正在进行」。"""
    return (f'QFrame{{background:{theme.C_ACCENT_SOFT};'
            f'border:1px solid {theme.C_ACCENT_LINE};border-radius:8px;}}')


def _style_row(selected: bool) -> str:
    if selected:
        return (f'QFrame{{background:{theme.C_ACCENT_SOFT};'
                f'border:1px solid {theme.C_ACCENT_LINE};border-radius:6px;}}')
    return (f'QFrame{{background:transparent;border:1px solid transparent;'
            f'border-radius:6px;}}')


def _style_fdi_edit() -> str:
    return (f'QLineEdit{{background:{theme.C_SURFACE2};color:{theme.C_TEXT};'
            f'border:1px solid {theme.C_BORDER};border-radius:5px;'
            f'padding:1px 6px;font-size:15px;font-weight:600;}}'
            f'QLineEdit:focus{{border-color:{theme.C_ACCENT};}}')


# ---------- 方向胶囊（近中 / 远中）----------
# 方案 B：给方向一词加一层淡底色胶囊，用色相区分近中（主色）与远中（紫）。
# 为什么不是纯文字着色：11px 的中文单靠色差在扫视时区分度不够，
# 胶囊有形状 + 底色 + 文字色三重差异，隔几行看也能一眼分堆。
DIR_CHIP_W, DIR_CHIP_H = 42, 18


def _dir_colors(direction: str) -> tuple[str, str, str]:
    """返回 (文字色, 底色, 描边色)；空方向走中性灰。"""
    if direction == '近中':
        return theme.C_DIR_MESIAL, theme.C_DIR_MESIAL_BG, theme.C_DIR_MESIAL_LINE
    if direction == '远中':
        return theme.C_DIR_DISTAL, theme.C_DIR_DISTAL_BG, theme.C_DIR_DISTAL_LINE
    return theme.C_TEXT3, 'transparent', theme.C_BORDER


def _style_dir_chip(direction: str) -> str:
    fg, bg, line = _dir_colors(direction)
    return (f'color:{fg};background:{bg};border:1px solid {line};'
            f'border-radius:{DIR_CHIP_H // 2}px;font-size:{F_CAP}px;'
            f'font-weight:600;')


def make_dir_chip(direction: str) -> QLabel:
    """方向胶囊：固定尺寸，保证列表与「当前测量」两处宽度一致。"""
    lbl = QLabel(direction or '—')
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedSize(DIR_CHIP_W, DIR_CHIP_H)
    lbl.setStyleSheet(_style_dir_chip(direction))
    if direction in ('近中', '远中'):
        lbl.setToolTip(f'牙轴向{direction}倾斜')
    return lbl


def _flex(widget: QWidget) -> QWidget:
    """让部件完全按 layout 权重分宽度。

    QBoxLayout 的 stretch 只分「扣掉各自 sizeHint 之后」的剩余空间：
    表头写「角度」、数据行写「−8.1°」，sizeHint 不同，同一权重也会错开几像素。
    把尺寸策略设成 Ignored，sizeHint 不再参与计算。
    """
    widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return widget


class DeleteButton(QPushButton):
    """行尾删除按钮：自绘的两笔交叉线，hover 淡红底 + 红线。

    为什么不用 `QPushButton('×')`：字符 × 的字形在 12~13px 下重心偏上、
    笔画粗细随字体变，和周边 0.5px 描边的 UI 不是一个手笔。自绘可以精确控制
    线宽（1.4px）、圆头端点、以及 hover 时才透出的淡红圆角底 —— 平时安静，
    鼠标移上去才提示「这条可以删」。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(W_DEL, W_DEL)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('删除该条')
        self.setFlat(True)
        self.setStyleSheet('background:transparent;border:none;padding:0;')
        self._hover = False

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            r = self.rect()
            active = self._hover or self.isDown()
            if active:
                # rgba 淡红底：QSS 不便表达随主题变化的半透明，直接按当前 danger 色取 alpha
                bg = QColor(theme.C_DANGER)
                bg.setAlpha(46 if self.isDown() else 28)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(bg)
                p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 8, 8)

            pen = QPen(QColor(theme.C_DANGER if active else theme.C_TEXT3), 1.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            # +0.5 让 1.4px 的线落在半像素上，避免抗锯齿把线糊成两像素灰边
            cx, cy = r.center().x() + 0.5, r.center().y() + 0.5
            d = 4.2
            p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
            p.drawLine(QPointF(cx - d, cy + d), QPointF(cx + d, cy - d))
        finally:
            p.end()


def _copy_on_click(lbl: QLabel, value: str, done: str = '已复制') -> None:
    """点数字复制到剪贴板，短暂回显提示。"""
    lbl.setCursor(Qt.CursorShape.PointingHandCursor)
    lbl.setToolTip('点击复制')
    original = lbl.text()
    # 定时器挂在 label 上：面板重建时 label 会被 deleteLater 销毁，定时器随之
    # 一起消失。早先用 QTimer.singleShot 的裸 lambda 捕获 label，700ms 内正好
    # 面板重建就会回调到已析构的 C++ 对象（RuntimeError: Internal C++ object
    # already deleted）；实测难复现，属于典型的定时器生命周期坑。
    timer = QTimer(lbl)
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: lbl.setText(original))

    def _on_click(_e):
        QApplication.clipboard().setText(value)
        lbl.setText(done)
        timer.start(700)

    lbl.mousePressEvent = _on_click


class ResultPanel(QWidget):
    fdiChanged = Signal(str)
    rowClicked = Signal(int)
    rowDeleteClicked = Signal(int)
    rowFdiEdited = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(336)
        self.setMaximumWidth(440)
        self._selected_seq: Optional[int] = None
        self._count = 0
        self._row_widgets: dict[int, QFrame] = {}
        self._head_cells: list[tuple[QLabel, str]] = []
        self._fdi_edit: Optional[QLineEdit] = None
        self._cur_sig: Optional[tuple] = None   # 当前测量块的内容签名，用于跳过重复重建
        self._list_sig: Optional[tuple] = None  # 列表内容签名，同理

        outer = QVBoxLayout(self)
        # 不留内衬：卡片直接撑满面板，才能和左侧画布卡上下边缘严格对齐
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName('resultCard')
        self._card.setStyleSheet(_style_card())
        card = QVBoxLayout(self._card)
        card.setContentsMargins(12, 12, 12, 10)
        card.setSpacing(8)

        # ---- 卡头：标题 + 计数 ----
        head = QHBoxLayout()
        head.setContentsMargins(2, 0, 2, 0)
        head.setSpacing(8)
        self._title = QLabel('测量记录')
        self._title.setStyleSheet(_style_title())
        head.addWidget(self._title)
        head.addStretch(1)
        self._count_lbl = QLabel('共 0 条')
        self._count_lbl.setStyleSheet(_style_count())
        head.addWidget(self._count_lbl)
        card.addLayout(head)

        # ---- ① 当前测量（内容可重建，容器常驻）----
        self._cur_box = QFrame()
        self._cur_box.setStyleSheet(_style_cur_box())
        self._cur_lay = QVBoxLayout(self._cur_box)
        self._cur_lay.setContentsMargins(12, 9, 12, 10)
        self._cur_lay.setSpacing(6)
        card.addWidget(self._cur_box)

        # ---- 分隔线 ----
        self._sep = QFrame()
        self._sep.setFixedHeight(1)
        self._sep.setStyleSheet(_style_sep())
        card.addWidget(self._sep)

        # ---- ② 表头（与数据行同列宽，保证对齐）----
        self._head_band = self._build_head_row()
        card.addWidget(self._head_band)

        # ---- ② 数据行 ----
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_container = QWidget()
        self._list_container.setStyleSheet('background:transparent;')
        self._list_lay = QVBoxLayout(self._list_container)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(1)
        self._list_lay.addStretch(1)
        self._scroll.setWidget(self._list_container)
        card.addWidget(self._scroll, 1)

        outer.addWidget(self._card, 1)

        self._render_current()
        self.refresh_list([], None)

    # ---------- 卡头 ----------

    def _set_count(self, n: int) -> None:
        self._count = n
        self._count_lbl.setText(f'共 {n} 条')

    # ---------- ① 当前测量 ----------

    def _clear_current(self) -> None:
        while self._cur_lay.count():
            item = self._cur_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # ⚠ 千万别 setParent(None)：那会把部件变成【无父的顶层窗口】，
                # 在 deleteLater 真正执行前，屏幕上会闪出几个无边框小框。
                # 只隐藏 + 延后销毁，父窗口仍是面板，绝不会单独上屏。
                w.hide()
                w.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                # ⚠ 千万别 setParent(None)：那会把部件变成【无父的顶层窗口】，
                # 在 deleteLater 真正执行前，屏幕上会闪出几个无边框小框。
                # 只隐藏 + 延后销毁，父窗口仍是面板，绝不会单独上屏。
                w.hide()
                w.deleteLater()
            elif item.layout() is not None:
                ResultPanel._clear_layout(item.layout())

    @staticmethod
    def _field(label: str, value_widget: QWidget, width: Optional[int] = None) -> QWidget:
        """小标题在上、值在下的字段块。"""
        box = QFrame()
        box.setStyleSheet(_transparent())
        if width:
            box.setFixedWidth(width)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        cap = QLabel(label)
        cap.setStyleSheet(_style_field_label())
        lay.addWidget(cap)
        lay.addWidget(value_widget)
        return box

    def _render_current(
        self,
        *,
        seq_text: str = '—',
        fdi: str = '',
        editable_fdi: bool = False,
        angle_text: str = '—',
        angle_color: Optional[str] = None,
        angle_copy: str = '',
        direction: str = '',
        hint: str = '',
        hint_color: Optional[str] = None,
    ) -> None:
        # 内容没变就不重建（清空会连发多个信号，重复建/删部件会闪）
        sig = (seq_text, fdi, editable_fdi, angle_text, angle_color,
               angle_copy, direction, hint, hint_color)
        if sig == self._cur_sig:
            return
        self._cur_sig = sig

        self._clear_current()
        self._fdi_edit = None

        cap = QLabel('当前测量')
        cap.setStyleSheet(_style_caption())
        self._cur_lay.addWidget(cap)

        fields = QHBoxLayout()
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setSpacing(16)

        # 编号
        seq_lbl = QLabel(seq_text)
        seq_lbl.setStyleSheet(_style_field_value(
            theme.C_TEXT if seq_text != '—' else theme.C_TEXT3))
        fields.addWidget(self._field('编号', seq_lbl, 40))

        # 牙号（完成态可直接编辑）
        if editable_fdi:
            edit = QLineEdit(fdi)
            edit.setPlaceholderText('待填')
            edit.setMaxLength(2)
            edit.setFixedWidth(56)
            edit.setStyleSheet(_style_fdi_edit())
            edit.editingFinished.connect(self._on_fdi_edited)
            self._fdi_edit = edit
            fdi_widget = edit
        else:
            fdi_lbl = QLabel(fdi or '—')
            fdi_lbl.setStyleSheet(_style_field_value(
                theme.C_TEXT if fdi else theme.C_TEXT3))
            fdi_widget = fdi_lbl
        fields.addWidget(self._field('牙号', fdi_widget, 56))

        # 角度（+ 方向后缀）
        ang_box = QFrame()
        ang_box.setStyleSheet(_transparent())
        ang_lay = QHBoxLayout(ang_box)
        ang_lay.setContentsMargins(0, 0, 0, 0)
        ang_lay.setSpacing(6)
        ang = QLabel(angle_text)
        ang_color = angle_color or (theme.C_TEXT3 if angle_text in ('—', '…')
                                   else theme.C_TEXT)
        ang.setStyleSheet(_style_angle_value(ang_color))
        ang.setFont(theme.numeric_font(ang.font()))   # 等宽数字：拖动读数不左右抖
        if angle_copy:
            _copy_on_click(ang, angle_copy)
        ang_lay.addWidget(ang, 0, Qt.AlignmentFlag.AlignVCenter)
        if direction:
            ang_lay.addWidget(make_dir_chip(direction), 0,
                              Qt.AlignmentFlag.AlignVCenter)
        ang_lay.addStretch(1)
        fields.addWidget(self._field('角度', ang_box), 1)

        self._cur_lay.addLayout(fields)

        if hint:
            hl = QLabel(hint)
            hl.setWordWrap(True)
            hl.setStyleSheet(
                f'color:{hint_color or theme.C_TEXT3};font-size:{F_CAP}px;'
                f'{_transparent()}')
            self._cur_lay.addWidget(hl)

    def _on_fdi_edited(self) -> None:
        # 延后一帧再发信号：主窗口收到后会重建本卡（会销毁这个输入框），
        # 直接在 editingFinished 里销毁 sender 不安全。
        if self._fdi_edit is not None:
            text = self._fdi_edit.text().strip()
            QTimer.singleShot(0, lambda t=text: self.fdiChanged.emit(t))

    # --- 三种状态 ---

    def show_blank(self, msg: str = '') -> None:
        """无选中记录的空白态；msg 可用于给出更具体的下一步提示。

        以前这个方法签名收 msg 却整条忽略、恒定显示同一句「先画参考线…」，
        调用方传什么都看不到 —— 参数是假的，要么用要么删。现在优先用调用方文案。
        """
        self._render_current(hint=msg or '先画参考线，再在牙上标记牙长轴')

    def show_measuring(self, step: int = 1, kind: str = 'tooth') -> None:
        if kind == 'ref':
            hint = '参考线 · 点击第一点' if step <= 1 else '参考线 · 点击第二点'
        else:
            hint = '牙长轴 · 点击牙根点' if step <= 1 else '牙长轴 · 点击牙冠点'
        self._render_current(angle_text='…', angle_color=theme.C_TEXT3, hint=hint)

    def show_result(self, tooth: Tooth) -> None:
        angle_text = '—'
        angle_color = theme.C_TEXT3
        angle_copy = ''
        if tooth.angle_deg is not None:
            angle_text = f'{tooth.angle_deg:+.1f}°'
            angle_copy = f'{tooth.angle_deg:+.1f}'
            angle_color = (theme.C_DANGER
                           if abs(tooth.angle_deg) > EXCEPTION_THRESHOLD_DEG
                           else theme.C_TEXT)

        # 提示行：异常 / 缺牙号，合并成一行，避免多行堆叠
        parts: List[str] = []
        if tooth.angle_deg is not None and abs(tooth.angle_deg) > EXCEPTION_THRESHOLD_DEG:
            parts.append(f'⚠ |角度| > {EXCEPTION_THRESHOLD_DEG:g}°，请复核')
        if not tooth.fdi:
            parts.append('牙号待填，± 方向可能需人工确认')
        hint = ' · '.join(parts)
        hint_color = (theme.C_DANGER if len(parts) > 1 else theme.C_WARN)

        self._render_current(
            seq_text=str(tooth.seq),
            fdi=tooth.fdi or '',
            editable_fdi=True,
            angle_text=angle_text,
            angle_color=angle_color,
            angle_copy=angle_copy,
            direction=tooth.direction or '—',
            hint=hint,
            hint_color=hint_color,
        )

    # ---------- ② 已测记录 ----------

    def _build_head_row(self) -> QFrame:
        w = QFrame()
        w.setObjectName('headBand')
        w.setFixedHeight(22)
        w.setStyleSheet(_style_head_band())
        lay = QHBoxLayout(w)
        lay.setContentsMargins(PAD_L, 0, PAD_L, 0)
        lay.setSpacing(GAP)

        def cell(text: str, align: str = 'l') -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(_style_head_cell(align))
            lbl.setAlignment({'l': Qt.AlignmentFlag.AlignLeft,
                              'r': Qt.AlignmentFlag.AlignRight,
                              'c': Qt.AlignmentFlag.AlignHCenter}[align]
                             | Qt.AlignmentFlag.AlignVCenter)
            self._head_cells.append((lbl, align))
            return _flex(lbl)

        # 与数据行同一组权重、同一套 item 结构，列头才会跟数据严格对齐。
        # 末尾必须放一个「固定 22 宽的透明 widget」而不是 addSpacing：相邻两个
        # spacer 之间 Qt 不插 spacing，而数据行那里是真控件会插，两者会差 8px。
        for text, align, weight in (('编号', 'l', COL_WEIGHTS[0]),
                                    ('牙号', 'l', COL_WEIGHTS[1]),
                                    ('角度', 'c', COL_WEIGHTS[2]),
                                    ('方向', 'l', COL_WEIGHTS[3])):
            lay.addWidget(cell(text, align), weight)
        lay.addSpacing(DEL_GAP)
        pad = QWidget()
        pad.setFixedWidth(W_DEL)
        pad.setStyleSheet(_transparent())
        lay.addWidget(pad)
        return w

    def refresh_list(self, teeth: List[Tooth], selected_seq: Optional[int]) -> None:
        # 内容签名一致则完全跳过重建，避免重复建/删行部件造成闪动
        sig = (selected_seq, tuple(
            (t.seq, t.fdi, t.angle_deg, t.direction) for t in teeth))
        if sig == self._list_sig:
            return
        self._list_sig = sig
        self._selected_seq = selected_seq
        # 清空旧行（保留末尾 stretch）
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # ⚠ 千万别 setParent(None)：那会把部件变成【无父的顶层窗口】，
                # 在 deleteLater 真正执行前，屏幕上会闪出几个无边框小框。
                # 只隐藏 + 延后销毁，父窗口仍是面板，绝不会单独上屏。
                w.hide()
                w.deleteLater()
        self._row_widgets.clear()

        self._set_count(len(teeth))

        if not teeth:
            empty = QLabel('暂无记录')
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f'color:{theme.C_TEXT3};font-size:{F_SM}px;padding:26px 0;'
                f'background:transparent;')
            self._list_lay.insertWidget(0, empty)
            return

        for tooth in teeth:
            row = self._build_row(tooth, selected_seq == tooth.seq)
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)


    def _build_row(self, tooth: Tooth, selected: bool) -> QFrame:
        row = QFrame()
        row.setStyleSheet(_style_row(selected))
        lay = QHBoxLayout(row)
        lay.setContentsMargins(PAD_L, 5, PAD_L, 5)
        lay.setSpacing(GAP)

        seq = QLabel(str(tooth.seq))
        seq.setStyleSheet(
            f'color:{theme.C_ACCENT_INK if selected else theme.C_TEXT3};'
            f'font-size:{F_CAP + 1}px;{_transparent()}')
        lay.addWidget(_flex(seq), COL_WEIGHTS[0])

        fdi = QLabel(tooth.fdi or '—')
        fdi.setStyleSheet(
            f'color:{theme.C_TEXT if tooth.fdi else theme.C_TEXT3};'
            f'font-size:{F_SM}px;{_transparent()}')
        lay.addWidget(_flex(fdi), COL_WEIGHTS[1])

        if tooth.angle_deg is not None:
            angle_txt = f'{tooth.angle_deg:+.1f}°'
            color = (theme.C_DANGER
                     if abs(tooth.angle_deg) > EXCEPTION_THRESHOLD_DEG
                     else theme.C_TEXT)
        else:
            angle_txt, color = '—', theme.C_TEXT3
        ang = QLabel(angle_txt)
        # 列宽按权重平均，角度取居中：固定宽度下右对齐会贴住方向列，看着偏挤
        ang.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        ang.setStyleSheet(
            f'color:{color};font-size:{F_SM}px;font-weight:600;{_transparent()}')
        ang.setFont(theme.numeric_font(ang.font()))   # 列表角度列同款等宽数字
        lay.addWidget(_flex(ang), COL_WEIGHTS[2])

        # 方向：容器跟着权重拉伸，胶囊靠左，与表头「方向」列起点对齐
        dir_wrap = QWidget()
        dir_wrap.setStyleSheet(_transparent())
        dir_lay = QHBoxLayout(dir_wrap)
        dir_lay.setContentsMargins(0, 0, 0, 0)
        dir_lay.setSpacing(0)
        direction = make_dir_chip(tooth.direction or '')
        dir_lay.addWidget(direction, 0, Qt.AlignmentFlag.AlignLeft
                          | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(_flex(dir_wrap), COL_WEIGHTS[3])

        lay.addSpacing(DEL_GAP)

        del_btn = DeleteButton()
        del_btn.clicked.connect(lambda _, s=tooth.seq: self.rowDeleteClicked.emit(s))
        lay.addWidget(del_btn)

        # 点击整行（及文字部分）选中
        for w in (row, seq, fdi, ang, direction):
            w.setCursor(Qt.CursorShape.PointingHandCursor)
            w.mousePressEvent = lambda _, s=tooth.seq: self.rowClicked.emit(s)

        self._row_widgets[tooth.seq] = row
        return row

    def scroll_to_seq(self, seq: int) -> None:
        row = self._row_widgets.get(seq)
        if row is not None:
            self._scroll.ensureWidgetVisible(row, 0, 24)

    def force_current_refresh(self) -> None:
        """让下一次 show_result 无视内容签名，强制重建「当前测量」块。

        用于拒绝非法输入后把输入框里的错字退回原值：模型没变时签名不变，
        不重置签名的话面板会认为「什么都没变」，不重建，错字就一直留在框里。
        """
        self._cur_sig = None

    # ---------- 主题 ----------

    def refresh_theme(self) -> None:
        """重设卡片与常驻部件样式（内容由主窗口 _refresh_panel 重建）。"""
        self._cur_sig = None    # 换主题后颜色全变，强制下次重建
        self._list_sig = None
        self._card.setStyleSheet(_style_card())
        self._cur_box.setStyleSheet(_style_cur_box())
        self._title.setStyleSheet(_style_title())
        self._count_lbl.setStyleSheet(_style_count())
        self._sep.setStyleSheet(_style_sep())
        self._head_band.setStyleSheet(_style_head_band())
        for lbl, align in self._head_cells:
            lbl.setStyleSheet(_style_head_cell(align))

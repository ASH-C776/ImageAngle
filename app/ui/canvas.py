"""图像画布：加载显示、缩放平移、画参考线/牙长轴、端点拖拽、取点放大镜、选中高亮。

交互约定：
- 画参考线 / 画牙长轴：左键依次点击两点；右键或 Esc 取消当前线。
- 模式为「无」时：左键拖拽空白处平移；滚轮缩放（以光标为中心）；
  点击线附近选中（高亮）；拖拽端点手柄可调整位置，角度实时重算。
- 牙长轴顺序固定为根 → 冠。

注：工具栏已不再提供「镜像」开关；`ImageData.flipped` 仅用于兼容历史
session.json（旧文件里 flipped=true 的图仍按原样翻转显示与换算）。
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFontMetricsF, QImage, QPainter, QPainterPath,
                           QPen)
from PySide6.QtWidgets import QWidget

from ..io.image_loader import is_supported
from ..model.angle import Point, apex_retreat_point, measure
from ..model.protocol import APEX_EXCLUSION_PCT
from ..model.session import Tooth, build_note
from . import theme

# 参考线在图上只做标识，不显示角度。
# 早先这里会标「参考线 90.0° · 偏离竖直 11.3°」并变色告警：那一版用参考线角度
# 参与符号判定，所以参考线画歪了会连带影响正负。现在符号只看「牙根在参考线哪
# 一侧」和「牙冠偏向」，参考线自身斜几度不影响结果，标出来只是噪音。
REFERENCE_LABEL = '参考线'

# 语义线条色：暗色工作区（近黑）用亮色线条；亮色工作区（浅灰/白）用深色线条，
# 保证两种主题下线条都有足够对比度（亮色浅灰底上原亮青/亮绿几乎不可见）。
_LINES = {
    'dark': {   # 暗色工作区：亮色线条
        'ref': (6, 182, 212),        # 参考线 青 #06b6d4
        'axis': (239, 68, 68),       # 牙长轴 红 #ef4444
        'axis_alt': (245, 158, 11),  # 未填牙位 琥珀 #f59e0b
        'root': (245, 158, 11),      # 根端点 琥珀
        'crown': (34, 197, 94),      # 冠端点 绿 #22c55e
    },
    'light': {  # 亮色工作区：深色线条（高对比）
        'ref': (13, 116, 144),       # 深青 #0e7490
        'axis': (209, 36, 47),       # 深红 #d1242f
        'axis_alt': (180, 83, 9),    # 深橙棕 #b45309
        'root': (180, 83, 9),        # 深橙棕
        'crown': (21, 128, 61),      # 深绿 #15803d
    },
}
COLOR_REF = QColor(*_LINES['dark']['ref'])
COLOR_AXIS = QColor(*_LINES['dark']['axis'])
COLOR_AXIS_ALT = QColor(*_LINES['dark']['axis_alt'])
COLOR_ROOT = QColor(*_LINES['dark']['root'])
COLOR_CROWN = QColor(*_LINES['dark']['crown'])

# 角度标注文字：正常态跟随线条色（红 / 琥珀），选中态改用薄荷绿。
# 这里刻意**不跟随主题**：文字画在 X 光片上（片子恒为深色），
# 用主题文字色会在亮色主题下变成近黑的深色，压在片子上直接看不见。
COLOR_SEL_TXT = QColor(34, 203, 168)   # #22cba8
_COLOR_HINT_ON_IMG = QColor(200, 200, 200)

# 角度标注文字的描边在 _draw_label 里按文字明暗自动取反（亮字描黑边、暗字描白边），
# 不随主题走 —— 片子本身的明暗才是决定可读性的因素。

# 辅助线 / 选中描边 / 放大镜描边（半透明，随主题切换深浅）
# 暗色用中性灰而非冷调石板灰，配合中性灰工作区不产生偏蓝观感。
_HALO = {'dark': (232, 232, 232, 120), 'light': (30, 58, 138, 130)}
_GUIDE = {'dark': (154, 154, 154, 175), 'light': (100, 116, 139, 190)}
_LOUPE = {'dark': (232, 232, 232, 145), 'light': (30, 58, 138, 150)}
COLOR_HALO = QColor(*_HALO['dark'])
COLOR_GUIDE = QColor(*_GUIDE['dark'])
COLOR_LOUPE = QColor(*_LOUPE['dark'])

# 随主题变化的 UI 颜色（由 refresh_theme 同步到当前主题令牌）
COLOR_WORKSPACE = QColor(theme.C_WORKSPACE)
COLOR_TEXT = QColor(theme.C_TEXT)
COLOR_HINT = QColor(theme.C_TEXT2)
COLOR_DOC_BORDER = QColor(theme.C_BORDER)

# 画布卡片圆角：与右侧「测量记录」卡（10px）保持一致，左右两框视觉统一
CARD_RADIUS = 10.0


def _dist(a: QPointF, b: QPointF) -> float:
    return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5


def _luma(c: QColor) -> float:
    """颜色的感知亮度（0 黑 ~ 1 白），用于决定文字衬边描黑还是描白。"""
    return (0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF())


def reference_label_text() -> str:
    """画布上参考线的文字标注：只写「参考线」，不写角度。

    参考线是方向判定的基准位置，它自己斜多少度不进入计算，标出来反而会让
    人以为「这条线偏了会不会影响结果」。
    """
    return REFERENCE_LABEL


def tooth_label_text(tooth: Tooth) -> str:
    """画布上牙长轴旁边的文字标注。

    只写带符号的度数：方向（近中 / 远中）、未填牙位提示都在右侧记录表里，
    图上再写一遍既遮挡牙体又增加噪音。
    """
    if tooth.angle_deg is None:
        return '无参考线'
    return f'{tooth.angle_deg:+.1f}°'


class Canvas(QWidget):
    referenceChanged = Signal()
    toothChanged = Signal()
    selectionChanged = Signal(object)  # seq 或 None
    statusText = Signal(str)
    fileDropped = Signal(str)
    modeChanged = Signal(int)
    drawStepChanged = Signal(int, str)  # (step 1|2, kind 'ref'|'tooth')
    contextMenuRequested = Signal(QPoint)  # 右键菜单（全局坐标），菜单内容由主窗口组装
    imageCloseRequested = Signal()      # 点左下角文件名浮层右侧的 × 

    MODE_NONE = 0
    MODE_REF = 1
    MODE_TOOTH = 2
    MODE_DRAG_REF1 = 3
    MODE_DRAG_REF2 = 4
    MODE_DRAG_ROOT = 5
    MODE_DRAG_CROWN = 6
    MODE_PAN = 7   # 中键临时平移（不再有独立的「抓手」工具模式）

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self._qimage: QImage | None = None
        self.image_data = None
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self.mode = self.MODE_NONE
        self._pending = None  # {'kind': 'ref'|'tooth', 'p1': QPointF(图像坐标)}
        self._cursor = QPointF(0.0, 0.0)
        self._hover = False   # 鼠标是否在画布内（决定是否画放大镜）
        self._drag = None
        self._selected_seq = None
        self._auto_fit = True     # 是否随窗口大小自动重排（用户手动缩放/平移后置 False）
        self._last_size = None    # 上一次的画布尺寸，用于 resize 时按比例挪 pan
        self._undo_stack: list = []
        self._hide_ref = False  # 重画参考线时临时隐藏旧线
        self._caption = ''      # 图片左下角的文件名浮层
        # 文件名浮层右侧关闭键的可点矩形（每帧绘制时更新，用于命中测试）
        self._caption_close: QRectF | None = None
        self._caption_hover = False
        # 画线时右键是「取消」，那一次右键不应该紧接着弹出上下文菜单
        self._suppress_menu = False

    # ---------- 图像加载 ----------

    def set_image(self, qimage: QImage, image_data) -> None:
        self._qimage = qimage
        self.image_data = image_data
        self.mode = self.MODE_NONE
        self._pending = None
        self._drag = None
        self._selected_seq = None
        self._auto_fit = True
        self._last_size = None
        # 撤销栈必须清空：栈里存的是「上一张图的第 N 条」「上一张图的旧参考线」，
        # 换图后继续沿用会把撤销作用到新图上（删错牙 / 恢复出别的图的参考线）。
        self._undo_stack.clear()
        self.update()
        self._fit_to_view()

    def set_caption(self, text: str) -> None:
        """图片左下角浮层文字（文件名 / 尺寸）。"""
        text = (text or '').strip()
        if text != self._caption:
            self._caption = text
            self.update()

    def caption(self) -> str:
        return self._caption

    def clear_image(self) -> None:
        self._qimage = None
        self.image_data = None
        self.mode = self.MODE_NONE
        self._pending = None
        self._drag = None
        self._caption = ''
        self._caption_close = None
        self._caption_hover = False
        self._auto_fit = True
        self._last_size = None
        self._undo_stack.clear()
        self.update()

    def has_image(self) -> bool:
        return self._qimage is not None and self.image_data is not None

    # ---------- 坐标 ----------

    def img_to_screen(self, p: QPointF) -> QPointF:
        if self.image_data and self.image_data.flipped:
            p = QPointF(self.image_data.width - 1 - p.x(), p.y())
        return QPointF(p.x() * self._zoom + self._pan.x(), p.y() * self._zoom + self._pan.y())

    def screen_to_img(self, s: QPointF) -> QPointF:
        x = (s.x() - self._pan.x()) / self._zoom
        y = (s.y() - self._pan.y()) / self._zoom
        if self.image_data and self.image_data.flipped:
            x = self.image_data.width - 1 - x
        return QPointF(x, y)

    def _fit_to_view(self) -> None:
        if not self._qimage:
            return
        iw, ih = self._qimage.width(), self._qimage.height()
        vw, vh = self.width(), self.height()
        if vw <= 1 or vh <= 1:
            return
        self._zoom = min(vw / iw, vh / ih) * 0.99
        self._pan = QPointF((vw - iw * self._zoom) / 2.0, (vh - ih * self._zoom) / 2.0)
        self._last_size = (vw, vh)
        self.update()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if not self._qimage:
            self._last_size = (self.width(), self.height())
            return
        if self._auto_fit:
            self._fit_to_view()
            return
        # 用户已经手动缩放 / 平移过：保持当前缩放，只按画布尺寸变化平移，
        # 让内容在视觉上留在原来的相对位置（之前是无条件 refit，放大后一改
        # 窗口大小就弹回整图，等于白放大）。
        old = self._last_size
        self._last_size = (self.width(), self.height())
        if old and old[0] > 0 and old[1] > 0:
            self._pan = QPointF(self._pan.x() + (self.width() - old[0]) / 2.0,
                                self._pan.y() + (self.height() - old[1]) / 2.0)
        self.update()

    def zoom_fit(self) -> None:
        self._auto_fit = True
        self._fit_to_view()

    def zoom_actual(self) -> None:
        """Ctrl+1：实际像素 100%。"""
        if not self._qimage:
            return
        self._auto_fit = False
        self._zoom = 1.0
        vw, vh = self.width(), self.height()
        iw, ih = self._qimage.width(), self._qimage.height()
        self._pan = QPointF((vw - iw) / 2.0, (vh - ih) / 2.0)
        self._last_size = (vw, vh)
        self.update()

    # ---------- 模式 ----------

    def _cursor_for_mode(self) -> Qt.CursorShape:
        if self.mode in (self.MODE_REF, self.MODE_TOOTH):
            return Qt.CursorShape.CrossCursor
        return Qt.CursorShape.ArrowCursor

    def set_mode(self, mode: int) -> None:
        self.mode = mode
        self._pending = None
        self._drag = None
        if mode != self.MODE_REF:
            self._hide_ref = False
        self.setCursor(self._cursor_for_mode())
        self.update()
        self.modeChanged.emit(mode)

    def cancel_pending(self) -> None:
        """Esc / 右键：取消当前未完成的线，并退出画线模式。

        之前的实现只在「已经落下第一点」时才做事：处于参考线模式但还没点第一点
        时按 Esc 既不退出模式，也不恢复被 `_hide_ref` 藏起来的旧参考线 ——
        表现是「点重画参考线 → 按 Esc → 原来那条线凭空消失」，而数据其实还在。
        """
        changed = False
        if self._pending is not None:
            self._pending = None
            self.statusText.emit('已取消当前画线')
            changed = True
        if self._hide_ref:
            self._hide_ref = False   # 恢复被临时隐藏的旧参考线
            changed = True
        if self.mode in (self.MODE_REF, self.MODE_TOOTH):
            self.set_mode(self.MODE_NONE)   # 会 emit modeChanged，按钮取消高亮
            changed = True
        if changed:
            self.update()

    # ---------- 测量数据 ----------

    def _has_ref(self) -> bool:
        return bool(self.image_data is not None and self.image_data.reference)

    def set_reference(self, p1: Point, p2: Point) -> None:
        if self.image_data is None:
            return
        old = self.image_data.reference
        self._undo_stack.append(('reference', old))
        self._hide_ref = False
        self.image_data.reference = {
            'x1': round(p1.x, 2), 'y1': round(p1.y, 2),
            'x2': round(p2.x, 2), 'y2': round(p2.y, 2),
            'type': 'palatal_midline',
        }
        self.recompute_all_teeth()
        self.referenceChanged.emit()
        self.statusText.emit('参考线已设置，全部牙角度已重算')

    def add_tooth(self, root: Point, crown: Point) -> Tooth:
        tooth = Tooth(
            seq=self.image_data.next_seq(),
            root={'x': round(root.x, 2), 'y': round(root.y, 2)},
            crown={'x': round(crown.x, 2), 'y': round(crown.y, 2)},
        )
        self.image_data.teeth.append(tooth)
        self._undo_stack.append(('add_tooth', len(self.image_data.teeth) - 1, tooth))
        self._compute_tooth(tooth)
        self._selected_seq = tooth.seq
        self.selectionChanged.emit(tooth.seq)
        self.toothChanged.emit()
        self.statusText.emit(f'已记录序号 {tooth.seq}')
        return tooth

    def _compute_tooth(self, tooth: Tooth) -> None:
        if self.image_data is None:
            return
        conflict = False
        side_unknown = False
        if not self._has_ref():
            tooth.angle_deg = None
            tooth.direction = None
        else:
            ref = self.image_data.reference
            res = measure(
                Point(tooth.root['x'], tooth.root['y']),
                Point(tooth.crown['x'], tooth.crown['y']),
                Point(ref['x1'], ref['y1']),
                Point(ref['x2'], ref['y2']),
                self.image_data.width,
                tooth.fdi,
                self.image_data.flipped,
            )
            tooth.angle_deg = res.angle_deg
            tooth.direction = res.direction
            conflict = res.conflict
            side_unknown = res.side == 'unknown'
        tooth.note = build_note(tooth.angle_deg, tooth.fdi, self._has_ref(),
                                conflict=conflict, side_unknown=side_unknown)

    def recompute_all_teeth(self) -> None:
        if self.image_data is None:
            return
        for t in self.image_data.teeth:
            self._compute_tooth(t)
        self.toothChanged.emit()

    def current_tooth(self) -> Tooth | None:
        """当前测量对象：优先选中的那条，否则取最新一条。"""
        if self.image_data is None or not self.image_data.teeth:
            return None
        if self._selected_seq is not None:
            for t in self.image_data.teeth:
                if t.seq == self._selected_seq:
                    return t
        return self.image_data.teeth[-1]

    def setSelected(self, seq) -> None:
        """外部设置选中行（从列表点击）。"""
        self._selected_seq = seq
        self.selectionChanged.emit(seq)
        self.update()

    def removeTooth(self, seq) -> bool:
        """删除指定序号的牙，返回是否成功。"""
        if self.image_data is None:
            return False
        for i, t in enumerate(self.image_data.teeth):
            if t.seq == seq:
                self._undo_stack.append(('remove_tooth', i, t))
                self.image_data.teeth.pop(i)
                if self._selected_seq == seq:
                    self._selected_seq = None
                    self.selectionChanged.emit(None)
                self.toothChanged.emit()
                self.statusText.emit(f'已删除序号 {seq}')
                return True
        return False

    def undo(self) -> bool:
        """撤销上一步操作。"""
        if not self._undo_stack:
            return False
        action = self._undo_stack.pop()
        if action[0] == 'add_tooth':
            _, idx, tooth = action
            if 0 <= idx < len(self.image_data.teeth):
                removed = self.image_data.teeth.pop(idx)
                if self._selected_seq == removed.seq:
                    self._selected_seq = None
                    self.selectionChanged.emit(None)
                self.toothChanged.emit()
                self.statusText.emit(f'已撤销：删除序号 {removed.seq}')
        elif action[0] == 'remove_tooth':
            _, idx, tooth = action
            self.image_data.teeth.insert(idx, tooth)
            self.toothChanged.emit()
            self.statusText.emit(f'已撤销：恢复序号 {tooth.seq}')
        elif action[0] == 'reference':
            _, old = action
            self.image_data.reference = old
            self.recompute_all_teeth()
            self.referenceChanged.emit()
            self.statusText.emit('已撤销参考线')
        elif action[0] == 'drag_ref':
            _, old = action
            self.image_data.reference = dict(old)
            self.recompute_all_teeth()
            self.referenceChanged.emit()
            self.statusText.emit('已撤销：参考线端点位置')
        elif action[0] == 'drag_tooth':
            _, seq, old_root, old_crown = action
            for t in self.image_data.teeth:
                if t.seq == seq:
                    t.root = dict(old_root)
                    t.crown = dict(old_crown)
                    self._compute_tooth(t)
                    self.toothChanged.emit()
                    self.statusText.emit(f'已撤销：序号 {seq} 端点位置')
                    break
        elif action[0] == 'clear_all':
            _, old_ref, old_teeth = action
            self.image_data.reference = old_ref
            self.image_data.teeth = old_teeth
            self.recompute_all_teeth()
            self.referenceChanged.emit()
            self.toothChanged.emit()
            self.statusText.emit('已恢复清空前的所有线')
        self.update()
        return True

    def clear_all(self) -> bool:
        """清空当前图所有参考线和牙长轴。返回是否有内容被清。"""
        if self.image_data is None:
            return False
        has_content = self.image_data.reference is not None or len(self.image_data.teeth) > 0
        if not has_content:
            return False
        # 快照进撤销栈
        snapshot_ref = self.image_data.reference
        snapshot_teeth = [Tooth(seq=t.seq, fdi=t.fdi, root=dict(t.root),
                                crown=dict(t.crown), angle_deg=t.angle_deg,
                                direction=t.direction, confidence=t.confidence, note=t.note)
                          for t in self.image_data.teeth]
        self._undo_stack.append(('clear_all', snapshot_ref, snapshot_teeth))
        self.image_data.reference = None
        self.image_data.teeth.clear()
        self._selected_seq = None
        self.selectionChanged.emit(None)
        self.referenceChanged.emit()
        self.toothChanged.emit()
        self.statusText.emit('已清空所有线（Ctrl+Z 可恢复）')
        self.update()
        return True

    # ---------- 鼠标事件 ----------

    def mousePressEvent(self, e) -> None:
        if not self.has_image():
            return
        self._hover = True
        # 左下角文件名的关闭键：优先于一切（画线过程中也能直接关图）
        if (e.button() == Qt.MouseButton.LeftButton
                and self._caption_close is not None
                and self._caption_close.contains(e.position())):
            self._caption_hover = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.imageCloseRequested.emit()
            return
        if e.button() == Qt.MouseButton.RightButton:
            drawing = (self.mode in (self.MODE_REF, self.MODE_TOOTH)
                       or self._pending is not None)
            # 正在画线：右键＝取消，这次右键不弹菜单（否则取消后菜单立刻弹出，
            # 用户点第二下就去点了菜单项，非常容易误触）
            self._suppress_menu = drawing
            self.cancel_pending()
            return
        s = e.position()
        img = self.screen_to_img(s)

        # PS 习惯：中键 = 抓手平移
        if e.button() == Qt.MouseButton.MiddleButton:
            self._auto_fit = False
            self._drag = {'submode': self.MODE_PAN, 'grab': s, 'start_pan': QPointF(self._pan)}
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            return

        if self.mode == self.MODE_REF:
            if self._pending is None:
                self._pending = {'kind': 'ref', 'p1': img}
                self.drawStepChanged.emit(2, 'ref')
                self.statusText.emit('参考线：点击第 2 点')
            else:
                self.set_reference(Point(self._pending['p1'].x(), self._pending['p1'].y()),
                                   Point(img.x(), img.y()))
                self._pending = None
                self.set_mode(self.MODE_NONE)
            self.update()
            return

        if self.mode == self.MODE_TOOTH:
            if self._pending is None:
                self._pending = {'kind': 'tooth', 'p1': img}
                self.drawStepChanged.emit(2, 'tooth')
                self.statusText.emit('牙长轴：点击牙冠中点')
            else:
                self.add_tooth(Point(self._pending['p1'].x(), self._pending['p1'].y()),
                               Point(img.x(), img.y()))
                self._pending = None
                self.set_mode(self.MODE_NONE)
            self.update()
            return

        # MODE_NONE：端点拖拽 / 选中（左键空白不平移，平移只走中键）
        hit = self._hit_test(s)
        if hit is not None:
            seq, submode, grab = hit
            self._selected_seq = seq
            self.selectionChanged.emit(seq)
            # 拖拽前拍快照，松手时若确实变了才压栈（逐帧压栈会把栈刷爆，
            # 完全不压栈则 Ctrl+Z 会跑去撤销更早的操作）。
            self._drag = {'submode': submode, 'grab': grab,
                          'before': self._drag_snapshot(submode, seq)}
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            self._selected_seq = None
            self.selectionChanged.emit(None)
        self.update()

    def _drag_snapshot(self, submode, seq):
        """记录一次拖拽开始前的状态（只覆盖端点/参考线端点拖拽）。"""
        if self.image_data is None:
            return None
        if submode in (self.MODE_DRAG_REF1, self.MODE_DRAG_REF2):
            ref = self.image_data.reference
            return {'kind': 'ref', 'ref': dict(ref)} if ref else None
        if submode in (self.MODE_DRAG_ROOT, self.MODE_DRAG_CROWN):
            for t in self.image_data.teeth:
                if t.seq == seq:
                    return {'kind': 'tooth', 'seq': seq,
                            'root': dict(t.root), 'crown': dict(t.crown)}
        return None

    def mouseMoveEvent(self, e) -> None:
        self._cursor = e.position()
        self._hover = True
        if not self.has_image():
            self.update()
            return
        if self._drag is not None:
            s = e.position()
            if self._drag['submode'] == self.MODE_PAN:
                d = s - self._drag['grab']
                self._pan = QPointF(self._drag['start_pan']) + d
            else:
                img = self.screen_to_img(s)
                self._apply_drag(img)
            self.update()
        else:
            # 悬停到关闭键上要换成手型，否则用户不知道那儿能点
            over = (self._caption_close is not None
                    and self._caption_close.contains(e.position()))
            if over != self._caption_hover:
                self._caption_hover = over
                self.setCursor(Qt.CursorShape.PointingHandCursor if over
                               else Qt.CursorShape.ArrowCursor)
                self.update()
            else:
                self.update()

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = False
        if self._caption_hover:
            self._caption_hover = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        moved = self._commit_drag_undo()
        self._drag = None
        self.setCursor(self._cursor_for_mode())
        self.update()
        if moved:
            # 拖动过程中为了保帧率刻意不发全量刷新（见 _apply_drag），松手补一次，
            # 否则右侧列表里的角度会停在拖动开始时的旧值上。
            self.toothChanged.emit()

    def is_dragging(self) -> bool:
        """是否正在拖端点 / 拖参考线（拖动中列表不重建，避免每帧建上百个控件）。"""
        return self._drag is not None and self._drag.get('submode') is not None

    def contextMenuEvent(self, e) -> None:
        """右键菜单：内容由主窗口组装（画布只负责「在哪弹、点了哪颗牙」）。"""
        if self._suppress_menu:
            self._suppress_menu = False
            e.accept()
            return
        if not self.has_image():
            return
        # 右键落在线条附近时先选中它，菜单里的「删除 / 复制角度」才有明确对象
        hit = self._hit_test(QPointF(e.pos()))
        if hit is not None:
            self.setSelected(hit[0])
        else:
            self.setSelected(None)
        self.contextMenuRequested.emit(e.globalPos())
        e.accept()

    def _commit_drag_undo(self) -> bool:
        """把一次「有实际位移」的拖拽压入撤销栈。没动就不记，避免刷屏。

        返回是否真的有位移。
        """
        d = self._drag
        if not d or self.image_data is None:
            return False
        before = d.get('before')
        if not before:
            return False
        if before['kind'] == 'ref':
            cur = self.image_data.reference
            if cur is not None and dict(cur) != before['ref']:
                self._undo_stack.append(('drag_ref', dict(before['ref'])))
                return True
        else:
            for t in self.image_data.teeth:
                if t.seq == before['seq']:
                    if (dict(t.root) != before['root']
                            or dict(t.crown) != before['crown']):
                        self._undo_stack.append(
                            ('drag_tooth', before['seq'],
                             dict(before['root']), dict(before['crown'])))
                        return True
                    break
        return False

    def _apply_drag(self, img: QPointF) -> None:
        sub = self._drag['submode']
        if sub is None:
            # 只是点在线上选中，没有拖端点：什么都不用改，更不必每帧重算 + 发信号
            return
        if sub == self.MODE_DRAG_REF1:
            ref = self.image_data.reference
            ref['x1'], ref['y1'] = round(img.x(), 2), round(img.y(), 2)
            self.recompute_all_teeth()
            self.referenceChanged.emit()
        elif sub == self.MODE_DRAG_REF2:
            ref = self.image_data.reference
            ref['x2'], ref['y2'] = round(img.x(), 2), round(img.y(), 2)
            self.recompute_all_teeth()
            self.referenceChanged.emit()
        else:
            tooth = self._selected_tooth()
            if tooth is None:
                return
            if sub == self.MODE_DRAG_ROOT:
                tooth.root = {'x': round(img.x(), 2), 'y': round(img.y(), 2)}
            elif sub == self.MODE_DRAG_CROWN:
                tooth.crown = {'x': round(img.x(), 2), 'y': round(img.y(), 2)}
            self._compute_tooth(tooth)
            self.toothChanged.emit()

    def _selected_tooth(self) -> Tooth | None:
        if self.image_data is None:
            return None
        for t in self.image_data.teeth:
            if t.seq == self._selected_seq:
                return t
        return None

    def _hit_test(self, s: QPointF):
        """返回 (seq, submode, 抓取点图像坐标) 或 None。"""
        if self.image_data is None:
            return None
        t = 10.0 / max(self._zoom, 1e-6)
        ref = self.image_data.reference
        if ref:
            p1 = QPointF(ref['x1'], ref['y1'])
            p2 = QPointF(ref['x2'], ref['y2'])
            for submode, p in ((self.MODE_DRAG_REF1, p1), (self.MODE_DRAG_REF2, p2)):
                if _dist(self.screen_to_img(s), p) <= t:
                    return (None, submode, p)
        best = None
        best_d = 8.0 / max(self._zoom, 1e-6)
        for tooth in self.image_data.teeth:
            r = QPointF(tooth.root['x'], tooth.root['y'])
            c = QPointF(tooth.crown['x'], tooth.crown['y'])
            for submode, pt in ((self.MODE_DRAG_ROOT, r), (self.MODE_DRAG_CROWN, c)):
                if _dist(self.screen_to_img(s), pt) <= t:
                    return (tooth.seq, submode, pt)
            d = _seg_dist(self.screen_to_img(s), r, c)
            if d <= best_d:
                best = (tooth.seq, None, None)
                best_d = d
        return best

    def wheelEvent(self, e) -> None:
        if not self.has_image():
            return
        self._auto_fit = False   # 用户手动缩放后，窗口变化不再自动重排
        factor = 1.25 if e.angleDelta().y() > 0 else 1.0 / 1.25
        new_zoom = max(0.1, min(8.0, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-9:
            return
        cursor = e.position()
        img_before = self.screen_to_img(cursor)
        self._zoom = new_zoom
        self._pan = QPointF(cursor.x() - img_before.x() * new_zoom,
                           cursor.y() - img_before.y() * new_zoom)
        self.update()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.cancel_pending()
            return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if e.key() == Qt.Key.Key_0:
                self.zoom_fit()
                self.statusText.emit('适应窗口（Ctrl+0）')
                return
            if e.key() == Qt.Key.Key_1:
                self.zoom_actual()
                self.statusText.emit('实际像素 100%（Ctrl+1）')
                return
        super().keyPressEvent(e)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            for u in e.mimeData().urls():
                if u.isLocalFile() and is_supported(u.toLocalFile()):
                    e.acceptProposedAction()
                    return

    def dropEvent(self, e) -> None:
        for u in e.mimeData().urls():
            if u.isLocalFile() and is_supported(u.toLocalFile()):
                self.fileDropped.emit(u.toLocalFile())
                return

    # ---------- 主题 ----------

    def refresh_theme(self) -> None:
        """切换主题后同步工作区 / 线条 / 文字 / 提示等颜色并重绘。"""
        global COLOR_WORKSPACE, COLOR_TEXT, COLOR_HINT, COLOR_DOC_BORDER
        global COLOR_REF, COLOR_AXIS, COLOR_AXIS_ALT, COLOR_ROOT, COLOR_CROWN
        global COLOR_HALO, COLOR_GUIDE, COLOR_LOUPE
        COLOR_WORKSPACE = QColor(theme.C_WORKSPACE)
        COLOR_TEXT = QColor(theme.C_TEXT)
        COLOR_HINT = QColor(theme.C_TEXT2)
        COLOR_DOC_BORDER = QColor(theme.C_BORDER)
        key = 'light' if not theme.is_dark() else 'dark'
        d = _LINES[key]
        COLOR_REF = QColor(*d['ref'])
        COLOR_AXIS = QColor(*d['axis'])
        COLOR_AXIS_ALT = QColor(*d['axis_alt'])
        COLOR_ROOT = QColor(*d['root'])
        COLOR_CROWN = QColor(*d['crown'])
        COLOR_HALO = QColor(*_HALO[key])
        COLOR_GUIDE = QColor(*_GUIDE[key])
        COLOR_LOUPE = QColor(*_LOUPE[key])
        self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 卡片化：圆角 + 1px 描边，与右侧结果卡同规格；所有内容裁进圆角内
        card = QPainterPath()
        card.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                            CARD_RADIUS, CARD_RADIUS)
        p.fillPath(card, COLOR_WORKSPACE)
        p.setClipPath(card)

        def finish() -> None:
            p.setClipping(False)
            p.setPen(QPen(COLOR_DOC_BORDER, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(card)
            p.end()

        if not self.has_image():
            self._paint_empty(p)
            finish()
            return
        iw, ih = self._qimage.width(), self._qimage.height()
        target = QRectF(self._pan.x(), self._pan.y(), iw * self._zoom, ih * self._zoom)
        # 缩小用平滑，放大到 100%+ 用最近邻保持像素锐利；图直接铺满画布，无边框投影
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._zoom < 1.0)
        if self.image_data and self.image_data.flipped:
            p.save()
            p.translate(target.center().x(), 0)
            p.scale(-1.0, 1.0)
            p.drawImage(QRectF(-target.width() / 2, target.top(), target.width(), target.height()), self._qimage)
            p.restore()
        else:
            p.drawImage(target, self._qimage)
        self._paint_reference(p)
        self._paint_teeth(p)
        self._paint_preview(p)
        self._paint_loupe(p)
        p.setPen(QPen(COLOR_HINT, 1))
        p.drawText(12, 22, f'{self._zoom * 100:.0f}%')
        self._paint_mode_hint(p)
        self._paint_caption(p)
        self._paint_pan_hint(p)
        finish()

    def _paint_pan_hint(self, p: QPainter) -> None:
        """右下角常驻一行操作提示。

        抓手工具删掉之后，「按住中键拖动」这个唯一的平移方式在界面上没有任何
        文字说明，新用户会以为放大后没法挪图。
        """
        if self.mode in (self.MODE_REF, self.MODE_TOOTH):
            return      # 画线时鼠标附近有放大镜，别再叠一行提示添乱
        if self.width() < 520:
            return
        text = '滚轮缩放 · 按住中键平移 · 右键更多'
        font = p.font()
        font.setPointSizeF(9.0)
        p.setFont(font)
        fm = QFontMetricsF(font)
        th = fm.height()
        tw = fm.horizontalAdvance(text)
        pad_x, pad_y = 8.0, 5.0
        box = QRectF(self.width() - 14.0 - tw - pad_x * 2,
                     self.height() - 14.0 - th - pad_y * 2,
                     tw + pad_x * 2, th + pad_y * 2)
        dark = theme.is_dark()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 110) if dark else QColor(255, 255, 255, 180))
        rr = box.height() / 2.0
        p.drawRoundedRect(box, rr, rr)
        p.setPen(QPen(QColor(205, 205, 205) if dark else QColor(45, 45, 45), 1))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_caption(self, p: QPainter) -> None:
        """图片左下角文件名浮层：半透明胶囊底，右侧带一个关闭键。

        关闭键直接画在浮层里而不是另放一个 QPushButton：浮层位置跟着画布
        尺寸走，单独放控件在缩放 / 面板折叠时很容易与浮层错位。
        可点区域记到 `self._caption_close`，由鼠标事件做命中测试。
        """
        text = self._caption
        if not text:
            self._caption_close = None
            self._caption_hover = False
            return
        font = p.font()
        font.setPointSizeF(9.0)
        p.setFont(font)
        fm = QFontMetricsF(font)
        pad_x, pad_y = 10.0, 5.0
        gap = 9.0                      # 文字与关闭键之间的留白，分隔线居中
        close_w = fm.height() + 4.0    # 关闭键可点区域：与胶囊同高，方正好点
        max_tw = max(80.0, min(self.width() - 28.0 - close_w - gap, 560.0))
        txt = fm.elidedText(text, Qt.TextElideMode.ElideMiddle, max_tw)
        tw = fm.horizontalAdvance(txt)
        th = fm.height()
        box = QRectF(14.0,
                     self.height() - 14.0 - th - pad_y * 2,
                     pad_x * 2 + tw + gap + close_w,
                     th + pad_y * 2)
        dark = theme.is_dark()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150) if dark else QColor(255, 255, 255, 205))
        r = box.height() / 2.0
        p.drawRoundedRect(box, r, r)

        # 文字区单独裁一下：文件名很长被省略时也不会压到分隔线上
        p.save()
        p.setClipRect(QRectF(box.left() + pad_x, box.top(), tw + 1.0, box.height()))
        p.setPen(QPen(QColor(theme.C_TEXT) if dark else QColor(24, 24, 24), 1))
        p.drawText(QRectF(box.left() + pad_x, box.top(), tw, box.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, txt)
        p.restore()

        # 分隔线
        dx = box.left() + pad_x + tw + gap / 2.0
        p.setPen(QPen(QColor(255, 255, 255, 46) if dark else QColor(0, 0, 0, 38), 1))
        p.drawLine(QPointF(dx, box.top() + 6), QPointF(dx, box.bottom() - 6))

        # 关闭键：常态是柔和的叉，悬停时变红底白叉（与标题栏关闭键一致）
        cr = QRectF(box.right() - pad_x - close_w, box.top(), close_w, box.height())
        self._caption_close = cr
        hover = self._caption_hover
        if hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.C_DANGER))
            p.drawRoundedRect(cr.adjusted(1.0, 3.0, -1.0, -3.0), 5.0, 5.0)
        col = QColor('#ffffff') if hover else (
            QColor(theme.C_TEXT) if dark else QColor(24, 24, 24))
        pen = QPen(col, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        c = cr.center()
        a = 3.6
        p.drawLine(QPointF(c.x() - a, c.y() - a), QPointF(c.x() + a, c.y() + a))
        p.drawLine(QPointF(c.x() - a, c.y() + a), QPointF(c.x() + a, c.y() - a))

    def _paint_mode_hint(self, p: QPainter) -> None:
        """画布左上角显示当前工具与「该点第几个点」，避免点了按钮不知道怎么下手。"""
        if self.mode == self.MODE_REF:
            hint = ('参考线 · 点击第 2 点' if self._pending
                    else '参考线 · 点击第 1 点')
            color = COLOR_REF
        elif self.mode == self.MODE_TOOTH:
            hint = ('牙长轴 · 点击牙冠点' if self._pending
                    else '牙长轴 · 点击牙根点（根 → 冠）')
            color = COLOR_AXIS
        else:
            return
        if self._pending:
            hint += '（右键取消）'
        font = p.font()
        font.setPointSize(10)
        p.setFont(font)
        p.setPen(QPen(color, 1))
        p.drawText(12, 44, hint)

    def _paint_empty(self, p: QPainter) -> None:
        p.setPen(QPen(COLOR_HINT, 1))
        font = p.font()
        font.setPointSize(13)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                   '拖入图片，或点击上方「打开 / 文件夹」（Ctrl+O）\n支持 JPG / JPEG / PNG / TIFF / BMP')

    def _paint_reference(self, p: QPainter) -> None:
        ref = self.image_data.reference
        if ref is None or self._hide_ref:
            return
        p1s = self.img_to_screen(QPointF(ref['x1'], ref['y1']))
        p2s = self.img_to_screen(QPointF(ref['x2'], ref['y2']))
        pen = QPen(COLOR_REF, 2.5, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(p1s, p2s)
        p.setPen(QPen(COLOR_REF, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for pt in (p1s, p2s):
            p.drawEllipse(pt, 5, 5)
        self._draw_label(p, QPointF(p1s.x() + 8, p1s.y() - 10),
                         reference_label_text(), COLOR_REF)

    def _paint_teeth(self, p: QPainter) -> None:
        if self.image_data is None:
            return
        for tooth in self.image_data.teeth:
            self._paint_tooth(p, tooth)

    def _paint_tooth(self, p: QPainter, tooth: Tooth) -> None:
        r = QPointF(tooth.root['x'], tooth.root['y'])
        c = QPointF(tooth.crown['x'], tooth.crown['y'])
        selected = tooth.seq == self._selected_seq
        color = COLOR_AXIS if tooth.fdi else COLOR_AXIS_ALT
        width = 3.5 if selected else 2.5
        ret = apex_retreat_point(Point(r.x(), r.y()), Point(c.x(), c.y()), APEX_EXCLUSION_PCT)
        rs = self.img_to_screen(r)
        cs = self.img_to_screen(c)
        rets = self.img_to_screen(QPointF(ret.x, ret.y))

        if selected:
            p.setPen(QPen(COLOR_HALO, width + 2))
            p.drawLine(rs, cs)
        p.setPen(QPen(color, width))
        p.drawLine(rs, cs)
        pen = QPen(COLOR_GUIDE, 1.5, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(rs, rets)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(COLOR_ROOT)
        p.drawEllipse(rs, 5, 5)
        p.setBrush(COLOR_CROWN)
        p.drawEllipse(cs, 5, 5)

        angle = tooth.angle_deg
        if angle is None:
            col = _COLOR_HINT_ON_IMG    # 同样不跟随主题，保证在片子上可见
        else:
            col = QColor(*_LINES['dark']['axis' if tooth.fdi else 'axis_alt'])
            if selected:
                col = COLOR_SEL_TXT
        self._draw_label(p, QPointF(cs.x() + 10, cs.y() - 14),
                         tooth_label_text(tooth), col)

    def _draw_label(self, p: QPainter, at: QPointF, txt: str, col: QColor) -> None:
        """在图片上写角度文字：先描一圈衬边，再填色。

        片子明暗差别极大（有的地方全黑、有的全白），单色文字在某种底色上必然吃亏。
        衬边取与文字明暗相反的颜色：亮字描黑边、暗字描白边，于是无论底下是骨头
        还是空气，字都能读清。
        """
        font = p.font()
        old = font
        font.setPointSize(11)
        font.setBold(True)
        p.setFont(font)
        path = QPainterPath()
        path.addText(at, font, txt)
        halo = QColor(0, 0, 0, 170) if _luma(col) > 0.40 else QColor(255, 255, 255, 205)
        p.setPen(QPen(halo, 3.0, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setFont(old)

    def _paint_preview(self, p: QPainter) -> None:
        if self._pending is None:
            return
        p1s = self.img_to_screen(self._pending['p1'])
        color = COLOR_REF if self._pending['kind'] == 'ref' else COLOR_AXIS
        p.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
        p.drawLine(p1s, self._cursor)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(COLOR_ROOT if self._pending['kind'] == 'tooth' else COLOR_REF)
        p.drawEllipse(p1s, 5, 5)

    def _paint_loupe(self, p: QPainter) -> None:
        # 只要处于「参考线 / 牙长轴」模式就显示放大镜（不限已落第一点）：
        # 第一点恰恰是最需要精确定位的，之前只在第二点才出现，取点体验不一致。
        if self.mode not in (self.MODE_REF, self.MODE_TOOTH):
            return
        if not self._qimage or not self._hover:
            return
        r = 46.0
        margin = 2.0
        center = loupe_center(self._cursor, float(self.width()), float(self.height()),
                              r, margin)
        img_c = self.screen_to_img(self._cursor)
        src_size = 2.0 * r / (2.5 * max(self._zoom, 1e-6))
        src = QRectF(img_c.x() - src_size / 2, img_c.y() - src_size / 2, src_size, src_size)
        p.save()
        path = QPainterPath()
        path.addEllipse(center, r, r)
        p.setClipPath(path)
        p.drawImage(QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r), self._qimage, src)
        p.setClipping(False)
        p.setPen(QPen(COLOR_LOUPE, 1))
        p.drawLine(center.x(), center.y() - r, center.x(), center.y() + r)
        p.drawLine(center.x() - r, center.y(), center.x() + r, center.y())
        p.setPen(QPen(COLOR_REF, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(center, r, r)
        p.restore()
        # 「2×」写在圆内左上角：写在外侧时，圆被顶到画布上边缘就会把文字留在外面。
        txt_at = QPointF(center.x() - r + 9, center.y() - r + 17)
        self._draw_label(p, txt_at, '2×',
                         self._on_image_text_color(self.screen_to_img(txt_at + QPointF(10, 0))))

    def _on_image_text_color(self, img_pt: QPointF) -> QColor:
        """按该处「画面上实际是什么底色」返回可读文字色（白 / 近黑）。

        注意先判断点是否落在图片范围内：贴近画布边缘时圆里的这一角其实是
        画布底色（图片没铺到），拿图片边缘像素取色会判反。
        """
        if not self._qimage:
            return QColor(255, 255, 255)
        x, y = img_pt.x(), img_pt.y()
        if not (0 <= x < self._qimage.width() and 0 <= y < self._qimage.height()):
            return QColor(255, 255, 255) if theme.is_dark() else QColor(24, 24, 24)
        c = self._qimage.pixelColor(int(x), int(y))
        luma = 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()
        return QColor(255, 255, 255) if luma < 0.55 else QColor(24, 24, 24)


def loupe_center(cursor: QPointF, w: float, h: float,
                 r: float = 46.0, margin: float = 2.0,
                 off: float = 64.0) -> QPointF:
    """放大镜圆心：默认在鼠标右上 off 像素，贴边时翻到另一侧并夹进可视区。

    以前圆心恒为 cursor+(64,-64)，鼠标靠上 / 靠右时整个圆跑出画布被裁掉，
    用户正在精确定位的地方反而看不到放大图。
    """
    dx, dy = off, -off
    if cursor.x() + dx + r > w - margin:
        dx = -dx
    if cursor.y() + dy - r < margin:
        dy = -dy
    cx = cursor.x() + dx
    cy = cursor.y() + dy
    cx = w / 2.0 if w < 2 * r + 2 * margin else max(margin + r, min(cx, w - margin - r))
    cy = h / 2.0 if h < 2 * r + 2 * margin else max(margin + r, min(cy, h - margin - r))
    return QPointF(cx, cy)


def _seg_dist(pt: QPointF, a: QPointF, b: QPointF) -> float:
    """点到线段距离。"""
    abx, aby = b.x() - a.x(), b.y() - a.y()
    if abx == 0 and aby == 0:
        return _dist(pt, a)
    t = ((pt.x() - a.x()) * abx + (pt.y() - a.y()) * aby) / (abx * abx + aby * aby)
    t = max(0.0, min(1.0, t))
    return _dist(pt, QPointF(a.x() + t * abx, a.y() + t * aby))

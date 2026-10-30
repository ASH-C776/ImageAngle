"""回归：画完一条牙轴后，「当前测量」必须立刻显示这条的结果。

历史 bug（牙轴改为常亮模式时引入）：`add_tooth()` 内部 `toothChanged` 是同步
连接，主窗口已经把面板刷成刚测出的结果；随后 canvas 又补发了一个
`drawStepChanged(1, 'tooth')`，主窗口把它转成 `show_measuring(1)`，于是面板
被覆盖回「… 牙长轴 · 点击牙根点」——用户看到的现象就是「测完了但当前测量
不显示数据」。修复方式是不再补发 step=1（下一次点击时 canvas 自然会发 step=2）。
"""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage

from app.model.session import ImageData
from app.ui.canvas import Canvas
from app.ui.result_panel import ResultPanel


class _Click:
    """最小鼠标事件替身：mousePressEvent 只用到 button() 与 position()。"""

    def __init__(self, x: float, y: float):
        from PySide6.QtCore import Qt
        self._p = QPointF(x, y)
        self._btn = Qt.MouseButton.LeftButton

    def button(self):
        return self._btn

    def position(self):
        return self._p


def _pt(x, y):
    from app.model.angle import Point
    return Point(x, y)


def _canvas_with_ref() -> tuple[Canvas, ImageData]:
    img = QImage(800, 600, QImage.Format.Format_Grayscale8)
    img.fill(0)
    data = ImageData(file='demo.png', width=800, height=600)
    c = Canvas()
    c.resize(800, 600)
    c.set_image(img, data)
    c.set_reference(_pt(400, 560), _pt(400, 60))   # 竖直参考线
    # 屏幕坐标 == 图像坐标，方便直接喂点击坐标
    c._zoom, c._pan, c._auto_fit = 1.0, QPointF(0.0, 0.0), False
    return c, data


def test_tooth_result_shows_immediately(qapp):
    """走真实点击路径（两次左键）：画完后「当前测量」必须是结果，不是「…」。"""
    c, data = _canvas_with_ref()
    panel = ResultPanel()

    c.toothChanged.connect(lambda: panel.show_result(c.current_tooth()))
    c.drawStepChanged.connect(lambda step, kind: panel.show_measuring(step, kind=kind))

    c.set_mode(Canvas.MODE_TOOTH)
    c.mousePressEvent(_Click(400.0, 400.0))   # 牙根点
    c.mousePressEvent(_Click(470.0, 120.0))   # 牙冠点 → 生成记录

    tooth = c.current_tooth()
    assert tooth is not None and tooth.angle_deg is not None
    assert panel._cur_sig is not None
    angle_text = panel._cur_sig[3]
    assert angle_text != '…', '画完后「当前测量」被画线提示覆盖了'
    assert '°' in angle_text, f'当前测量应显示角度，实际是 {angle_text!r}'


def test_measuring_step_still_reachable(qapp):
    """常亮模式下再点第一点，仍要回到「点击牙冠点」提示（step=2 链路没被删）。"""
    c, _ = _canvas_with_ref()
    panel = ResultPanel()
    c.drawStepChanged.connect(lambda step, kind: panel.show_measuring(step, kind=kind))
    c.set_mode(Canvas.MODE_TOOTH)
    c.drawStepChanged.emit(2, 'tooth')
    assert panel._cur_sig[3] == '…'

"""画布测量闭环测试（offscreen）：参考线 + 牙长轴 + 空白结果 + 自动补算。"""
from PySide6.QtGui import QImage

from app.model.angle import Point
from app.model.session import ImageData
from app.ui.canvas import Canvas


def _make_canvas(path='x.jpg'):
    img = QImage(400, 200, QImage.Format.Format_RGB888)
    img.fill(0x10101C)
    c = Canvas()
    c.resize(400, 300)
    c.set_image(img, ImageData(file=path, width=400, height=200))
    return c


def test_draw_reference_and_tooth(qapp):
    c = _make_canvas()
    c.set_reference(Point(200, 20), Point(200, 180))  # 竖直参考线
    assert c.image_data.reference is not None
    assert c.image_data.reference['type'] == 'palatal_midline'

    # 左半侧牙：冠偏右（向中线）= 近中 = 正
    c.add_tooth(Point(150, 120), Point(170, 70))
    t = c.image_data.teeth[-1]
    assert t.seq == 1
    assert t.angle_deg is not None and t.angle_deg > 0
    assert t.direction == '近中'


def test_blank_without_reference_then_autofill(qapp):
    c = _make_canvas('y.jpg')
    c.add_tooth(Point(100, 100), Point(120, 50))
    t = c.image_data.teeth[-1]
    assert t.angle_deg is None and t.direction is None
    assert '无参考线' in t.note

    # 补画参考线 → 自动补算
    c.set_reference(Point(200, 20), Point(200, 180))
    assert t.angle_deg is not None and t.angle_deg > 0
    assert '无参考线' not in t.note


def test_reference_drag_recomputes_all(qapp):
    c = _make_canvas()
    c.set_reference(Point(200, 20), Point(200, 180))
    c.add_tooth(Point(150, 120), Point(170, 70))
    t = c.image_data.teeth[-1]
    before = t.angle_deg
    # 拖动参考线端点（重画为斜向），角度应变化
    c.image_data.reference['x2'] = 260.0
    c.recompute_all_teeth()
    assert t.angle_deg is not None and t.angle_deg != before


def test_endpoint_drag_updates_tooth(qapp):
    c = _make_canvas()
    c.set_reference(Point(200, 20), Point(200, 180))
    c.add_tooth(Point(150, 120), Point(170, 70))
    t = c.image_data.teeth[-1]
    before = t.angle_deg
    t.crown = {'x': 190.0, 'y': 70.0}  # 冠点右移 → 更向近中
    c.recompute_all_teeth()
    assert t.angle_deg is not None and t.angle_deg > before


def test_current_tooth_and_seq(qapp):
    c = _make_canvas()
    c.set_reference(Point(200, 20), Point(200, 180))
    c.add_tooth(Point(100, 100), Point(120, 50))
    c.add_tooth(Point(300, 100), Point(280, 50))
    assert c.image_data.next_seq() == 3
    assert c.current_tooth().seq == 2

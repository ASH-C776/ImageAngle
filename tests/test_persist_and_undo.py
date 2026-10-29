"""本轮修复的回归测试：

1. 测量结果落盘 / 重开恢复（会话持久化）
2. 撤销栈跨图片不再串（换图即清空）
3. 拖动端点可以撤销（且没位移时不留垃圾栈项）
4. 窗口 resize 不再把用户手动放大重置回整图
5. 关闭画线工具后「当前测量」恢复，而不是停在画线提示
6. 重画参考线时按 Esc / 右键取消，旧线要重新可见并退出模式
"""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage

from app.model.angle import Point
from app.ui.canvas import Canvas


def _make_png(tmp_path, name='pano.png', w=800, h=400):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor('#7a7a7a'))
    p = tmp_path / name
    assert img.save(str(p))
    return str(p)


def _canvas(qapp):
    from app.model.session import ImageData

    c = Canvas()
    c.resize(800, 600)
    img = QImage(400, 200, QImage.Format.Format_RGB32)
    img.fill(QColor('#666666'))
    data = ImageData(file='x.png', width=400, height=200)
    c.set_image(img, data)
    c.show()                 # 隐藏的 widget 收不到 resizeEvent，必须 show 才能测缩放行为
    qapp.processEvents()
    return c


# ---------- 1. 会话持久化 ----------

def test_measurements_survive_reopen(qapp, tmp_path, monkeypatch):
    """画完线关掉软件，重开同一张图应恢复参考线和记录。"""
    from app.ui import main_window

    monkeypatch.setattr(main_window, '_SESSION_PATH', str(tmp_path / 'session.json'))
    p = _make_png(tmp_path)

    win = main_window.MainWindow()
    win._open_path(p)
    win.canvas.set_reference(Point(400, 20), Point(400, 180))
    win.canvas.add_tooth(Point(150, 150), Point(170, 60))
    win.close()
    qapp.processEvents()

    win2 = main_window.MainWindow()
    win2._open_path(p)
    assert win2.canvas._has_ref()
    assert len(win2.canvas.image_data.teeth) == 1
    assert win2.canvas.image_data.teeth[0].angle_deg is not None
    win2.close()


def test_switching_images_keeps_both(qapp, tmp_path, monkeypatch):
    """A 画完切到 B 再切回 A，A 的线还在（之前每次打开都是白纸）。"""
    from app.ui import main_window

    monkeypatch.setattr(main_window, '_SESSION_PATH', str(tmp_path / 'session.json'))
    pa = _make_png(tmp_path, 'a.png')
    pb = _make_png(tmp_path, 'b.png')

    win = main_window.MainWindow()
    win._open_path(pa)
    win.canvas.set_reference(Point(400, 20), Point(400, 180))
    win.canvas.add_tooth(Point(150, 150), Point(170, 60))

    win._open_path(pb)
    assert len(win.canvas.image_data.teeth) == 0
    win.canvas.add_tooth(Point(200, 150), Point(220, 60))
    assert len(win.canvas.image_data.teeth) == 1

    win._open_path(pa)
    assert len(win.canvas.image_data.teeth) == 1
    assert win.canvas._has_ref()
    win.close()


def test_blank_images_are_not_written_to_session(qapp, tmp_path, monkeypatch):
    """只是打开看一眼、没画线的图，不该在 session.json 里留空条目。"""
    import json

    from app.ui import main_window

    sp = tmp_path / 'session.json'
    monkeypatch.setattr(main_window, '_SESSION_PATH', str(sp))
    p = _make_png(tmp_path)

    win = main_window.MainWindow()
    win._open_path(p)
    win.close()
    qapp.processEvents()

    data = json.loads(sp.read_text(encoding='utf-8'))
    assert data.get('images', {}) == {}


def test_image_size_change_invalidates_old_coordinates(qapp, tmp_path, monkeypatch):
    """同一路径的图被换成不同尺寸时，旧像素坐标必须丢弃，否则标注错位。"""
    from app.model.session import ImageData, Tooth
    from app.ui import main_window

    monkeypatch.setattr(main_window, '_SESSION_PATH', str(tmp_path / 'session.json'))
    p = _make_png(tmp_path, w=800, h=400)

    win = main_window.MainWindow()
    stale = ImageData(file=p, width=1600, height=800)
    stale.teeth = [Tooth(seq=1, fdi='16', angle_deg=10.0)]
    stale.reference = {'x1': 1, 'y1': 2, 'x2': 3, 'y2': 4, 'type': 'palatal_midline'}
    win.session.images[p] = stale

    win._open_path(p)
    assert win.canvas.image_data.teeth == []
    assert win.canvas.image_data.reference is None
    assert (win.canvas.image_data.width, win.canvas.image_data.height) == (800, 400)
    win.close()


# ---------- 2. 撤销栈跨图 ----------

def test_undo_stack_cleared_when_image_changes(qapp):
    c = _canvas(qapp)
    c.set_reference(Point(200, 20), Point(200, 180))
    c.add_tooth(Point(100, 150), Point(120, 60))
    assert len(c._undo_stack) == 2
    old_data = c.image_data

    img = QImage(400, 200, QImage.Format.Format_RGB32)
    img.fill(QColor('#333333'))
    from app.model.session import ImageData
    new_data = ImageData(file='y.png', width=400, height=200)
    c.set_image(img, new_data)

    assert c._undo_stack == []      # 换图后不能残留上一张的撤销项
    assert len(old_data.teeth) == 1
    c.add_tooth(Point(210, 150), Point(230, 60))
    assert c.undo() is True
    assert len(new_data.teeth) == 0   # 只撤销新图自己的操作
    assert len(old_data.teeth) == 1   # 上一张图不受影响


# ---------- 3. 拖动端点可撤销 ----------

def _drag(c, submode, seq, to):
    c._drag = {'submode': submode, 'grab': QPointF(0, 0),
               'before': c._drag_snapshot(submode, seq)}
    c._apply_drag(to)
    c._commit_drag_undo()
    c._drag = None


def test_dragging_reference_endpoint_is_undoable(qapp):
    c = _canvas(qapp)
    c.set_reference(Point(200, 20), Point(200, 180))
    before = dict(c.image_data.reference)
    n = len(c._undo_stack)

    _drag(c, c.MODE_DRAG_REF1, None, QPointF(160, 40))
    assert c.image_data.reference['x1'] == 160
    assert len(c._undo_stack) == n + 1

    assert c.undo() is True
    assert c.image_data.reference == before


def test_dragging_tooth_endpoint_is_undoable(qapp):
    c = _canvas(qapp)
    c.set_reference(Point(200, 20), Point(200, 180))
    t = c.add_tooth(Point(100, 150), Point(120, 60))
    before = (dict(t.root), dict(t.crown))
    n = len(c._undo_stack)

    _drag(c, c.MODE_DRAG_CROWN, t.seq, QPointF(140, 40))
    assert t.crown['x'] == 140
    assert len(c._undo_stack) == n + 1

    assert c.undo() is True
    assert (t.root, t.crown) == before


def test_click_without_move_does_not_push_undo(qapp):
    """只是点一下线选中（没有拖动），不该往撤销栈里塞空操作。"""
    c = _canvas(qapp)
    c.set_reference(Point(200, 20), Point(200, 180))
    t = c.add_tooth(Point(100, 150), Point(120, 60))
    n = len(c._undo_stack)

    c._drag = {'submode': None, 'grab': None, 'before': None}
    c._apply_drag(QPointF(999, 999))   # 点在线身上，submode=None
    c._commit_drag_undo()
    c._drag = None
    assert len(c._undo_stack) == n
    assert t.crown['x'] == 120


# ---------- 4. resize 不再重置缩放 ----------

def test_resize_keeps_manual_zoom(qapp):
    c = _canvas(qapp)
    fit = c._zoom
    c._zoom = fit * 3
    c._auto_fit = False
    c._last_size = (c.width(), c.height())

    c.resize(c.width() + 120, c.height() + 80)
    assert abs(c._zoom - fit * 3) < 1e-9     # 放大状态保留


def test_resize_refits_after_fit_button(qapp):
    """点过「适应窗口」后，窗口变化仍自动重排（这是用户明确要的整图状态）。"""
    c = _canvas(qapp)
    c.zoom_fit()
    z0 = c._zoom
    c.resize(c.width() - 200, c.height() - 100)
    assert c._zoom != z0
    assert c._auto_fit is True


def test_wheel_zoom_disables_auto_fit(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QWheelEvent

    c = _canvas(qapp)
    before = c._auto_fit
    ev = QWheelEvent(QPointF(100, 100), QPointF(100, 100),
                     QPoint(0, 0), QPoint(0, 120),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    c.wheelEvent(ev)
    assert before is True and c._auto_fit is False


# ---------- 5/6. 工具启停与面板提示 ----------

def test_toggling_tool_off_restores_current_measurement(qapp, tmp_path, monkeypatch):
    from app.ui import main_window

    monkeypatch.setattr(main_window, '_SESSION_PATH', str(tmp_path / 'session.json'))
    p = _make_png(tmp_path)

    win = main_window.MainWindow()
    win._open_path(p)
    win.canvas.set_reference(Point(400, 20), Point(400, 180))
    win.canvas.add_tooth(Point(150, 150), Point(170, 60))
    ang = win.canvas.image_data.teeth[0].angle_deg

    win.act_ref.trigger()          # 进入参考线模式
    assert '参考线' in (win.panel._cur_sig[-2] or '')
    win.act_ref.trigger()          # 再点一次退出
    qapp.processEvents()

    assert win.canvas.mode == Canvas.MODE_NONE
    sig = win.panel._cur_sig
    assert '参考线' not in (sig[-2] or '')
    assert sig[3] == f'{ang:+.1f}°'     # 当前测量恢复成真实角度
    win.close()


def test_escape_restores_hidden_reference(qapp, tmp_path, monkeypatch):
    """重画参考线时按 Esc：旧线要重新显示，并退出画线模式。"""
    from app.ui import main_window

    monkeypatch.setattr(main_window, '_SESSION_PATH', str(tmp_path / 'session.json'))
    p = _make_png(tmp_path)

    win = main_window.MainWindow()
    win._open_path(p)
    win.canvas.set_reference(Point(400, 20), Point(400, 180))

    win.act_ref.trigger()          # 有参考线 → 重画模式，旧线暂时隐藏
    assert win.canvas._hide_ref is True
    assert win.canvas.mode == Canvas.MODE_REF

    win.canvas.cancel_pending()    # 等价于按 Esc
    assert win.canvas._hide_ref is False
    assert win.canvas.mode == Canvas.MODE_NONE
    win.close()

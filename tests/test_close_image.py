"""关闭图片（画布左下角文件名右侧的 ×）相关的回归测试。

三件事必须成立：
1. 启动是空白工作区，不自动打开上次的图；
2. 关闭后画布 / 面板 / 状态栏一起回到「未打开图片」，不留上一张的残留；
3. 关闭**不删数据** —— 重新打开同一张图，历史测量还在。
"""
import json

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent

from app.model.angle import Point


def _make_png(tmp_path, name='close.png', w=800, h=400):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor('#6f6f6f'))
    p = tmp_path / name
    assert img.save(str(p))
    return str(p)


def _click(widget, pos: QPointF, button=Qt.MouseButton.LeftButton) -> None:
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, pos, widget.mapToGlobal(pos),
                     button, button, Qt.KeyboardModifier.NoModifier)
    widget.mousePressEvent(ev)


def test_caption_has_close_hit_area(qapp, tmp_path):
    """有文件名时应该画出一个可点的关闭键矩形，且落在浮层右端。"""
    from app.ui.main_window import MainWindow

    win = MainWindow()
    win.resize(1100, 720)
    win.show()
    win._open_path(_make_png(tmp_path))
    qapp.processEvents()

    rect = win.canvas._caption_close
    assert rect is not None
    assert rect.width() >= 14 and rect.height() >= 14, '太小点不中'
    # 在浮层垂直范围内、且靠近左下角
    assert rect.bottom() > win.canvas.height() - 60
    assert rect.left() < win.canvas.width() * 0.6
    win.close()


def test_click_close_emits_and_clears(qapp, tmp_path):
    """点关闭键 → 画布清空、面板清空、状态栏提示、没有残留记录。"""
    from app.ui.main_window import MainWindow

    win = MainWindow()
    win.resize(1100, 720)
    win.show()
    win._open_path(_make_png(tmp_path))
    qapp.processEvents()
    win.canvas.set_reference(Point(400, 20), Point(400, 380))
    win.canvas.add_tooth(Point(200, 300), Point(220, 120))
    win._refresh_panel()
    assert len(win.canvas.image_data.teeth) == 1

    rect = win.canvas._caption_close
    fired = []
    win.canvas.imageCloseRequested.connect(lambda: fired.append(1))
    _click(win.canvas, rect.center())

    assert fired == [1]
    assert not win.canvas.has_image()
    assert win.canvas.caption() == ''
    assert win.canvas._caption_close is None
    assert win._current_path is None
    assert win.panel._row_widgets == {}          # 列表行已清掉
    assert '已关闭图片' in win.statusBar().currentMessage()
    assert not win.act_ref.isEnabled()           # 工具栏回到未打开状态
    win.close()


def test_close_keeps_measurements_in_session(qapp, tmp_path):
    """关闭 ≠ 删除：重新打开同一张图，参考线和牙长轴都还在。"""
    from app.ui.main_window import MainWindow

    p = _make_png(tmp_path)
    win = MainWindow()
    win.resize(1100, 720)
    win.show()
    win._open_path(p)
    win.canvas.set_reference(Point(400, 20), Point(400, 380))
    win.canvas.add_tooth(Point(200, 300), Point(220, 120))
    win.canvas.imageCloseRequested.emit()

    win._open_path(p)
    assert win.canvas.has_image()
    assert win.canvas.image_data.reference is not None
    assert len(win.canvas.image_data.teeth) == 1
    win.close()


def test_click_elsewhere_in_caption_does_not_close(qapp, tmp_path):
    """点文件名本身（不是右侧的叉）不应该关图。"""
    from app.ui.main_window import MainWindow

    win = MainWindow()
    win.resize(1100, 720)
    win.show()
    win._open_path(_make_png(tmp_path))
    qapp.processEvents()
    rect = win.canvas._caption_close
    left_of_close = QPointF(rect.left() - 20, rect.center().y())
    _click(win.canvas, left_of_close)
    assert win.canvas.has_image()
    win.close()


def test_panel_hint_matches_image_state(qapp, tmp_path):
    """没打开图片时面板提示「先打开」，打开后才提示「先画参考线」。"""
    from app.ui.main_window import MainWindow

    win = MainWindow()
    win.show()
    win._refresh_panel()
    assert '打开' in win.panel._cur_sig[7]

    win._open_path(_make_png(tmp_path))
    win._refresh_panel()
    assert '参考线' in win.panel._cur_sig[7]
    win.close()


def test_close_while_drawing_resets_tool(qapp, tmp_path):
    """画线途中点 × ：工具按钮要跟着退回未勾选，否则再点一次像是失灵。"""
    from app.ui.canvas import Canvas
    from app.ui.main_window import MainWindow

    win = MainWindow()
    win.resize(1100, 720)
    win.show()
    win._open_path(_make_png(tmp_path))
    win.canvas.set_mode(Canvas.MODE_REF)
    win.act_ref.setChecked(True)
    win.canvas.imageCloseRequested.emit()
    assert win.canvas.mode == Canvas.MODE_NONE
    assert not win.act_ref.isChecked()
    win.close()


def test_startup_does_not_auto_open(qapp, tmp_path, monkeypatch):
    """窗口偏好里存着 last_path，启动也不能自动加载图片。"""
    from app.ui import main_window

    p = _make_png(tmp_path)
    monkeypatch.setattr(
        main_window, '_WIN_PREF_PATH', str(tmp_path / 'pref.json'), raising=False)
    with open(tmp_path / 'pref.json', 'w', encoding='utf-8') as f:
        json.dump({'geometry': [80, 80, 1100, 700], 'maximized': False,
                   'last_path': p}, f)

    win = main_window.MainWindow()
    assert not win.canvas.has_image()
    assert win._current_path is None
    assert win._last_dir == str(tmp_path)     # 但记得上次的文件夹
    win.close()

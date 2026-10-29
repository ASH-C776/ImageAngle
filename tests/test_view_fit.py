"""「适应窗口」按钮（替代原「抓手」工具）：放大 / 平移后一键回到整图大小。"""
from PySide6.QtGui import QColor, QImage


def _make_png(tmp_path, w=800, h=400):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor('#7a7a7a'))
    p = tmp_path / 'fit_demo.png'
    assert img.save(str(p))
    return str(p)


def test_fit_action_resets_zoom_and_pan(qapp, tmp_path, monkeypatch):
    from app.ui import main_window

    monkeypatch.setattr(main_window, '_SESSION_PATH', str(tmp_path / 'session.json'))
    win = main_window.MainWindow()
    win.resize(1000, 700)
    win.show()
    qapp.processEvents()

    # 无图片时按钮不可用
    assert not win.act_fit.isEnabled()

    win._open_path(_make_png(tmp_path))
    qapp.processEvents()
    assert win.act_fit.isEnabled()

    fit_zoom = win.canvas._zoom
    fit_pan = (win.canvas._pan.x(), win.canvas._pan.y())

    # 模拟放大 + 平移
    win.canvas.zoom_actual()
    win.canvas._pan = win.canvas._pan + type(win.canvas._pan)(-120, -80)
    assert win.canvas._zoom == 1.0

    win.act_fit.trigger()
    qapp.processEvents()
    assert abs(win.canvas._zoom - fit_zoom) < 1e-9
    assert abs(win.canvas._pan.x() - fit_pan[0]) < 1e-6
    assert abs(win.canvas._pan.y() - fit_pan[1]) < 1e-6

    win.close()
    qapp.processEvents()


def test_fit_action_without_image_is_safe(qapp, tmp_path, monkeypatch):
    from app.ui import main_window

    monkeypatch.setattr(main_window, '_SESSION_PATH', str(tmp_path / 'session.json'))
    win = main_window.MainWindow()
    win.show()
    qapp.processEvents()
    win._on_fit()          # 不应抛异常
    assert not win.canvas.has_image()
    win.close()
    qapp.processEvents()

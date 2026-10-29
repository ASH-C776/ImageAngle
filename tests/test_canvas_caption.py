"""文件名浮层：打开图片后显示在画布左下角，而不再占结果面板底部一行。"""
from PySide6.QtGui import QColor, QImage


def _make_png(tmp_path):
    img = QImage(640, 320, QImage.Format.Format_RGB32)
    img.fill(QColor('#808080'))
    p = tmp_path / 'panorama_demo.png'
    assert img.save(str(p))
    return str(p)


def test_caption_moves_from_panel_to_canvas(qapp, tmp_path, monkeypatch):
    from app.ui import main_window

    monkeypatch.setattr(main_window, '_SESSION_PATH', str(tmp_path / 'session.json'))
    win = main_window.MainWindow()
    win.show()
    qapp.processEvents()

    path = _make_png(tmp_path)
    win._open_path(path)
    qapp.processEvents()

    assert win.canvas.caption() == 'panorama_demo.png · 640 × 320'
    # 结果面板里已经没有「底部状态行」这个东西了（文件名只在画布浮层出现）
    assert not hasattr(win.panel, '_status')
    win.close()
    qapp.processEvents()


def test_caption_set_and_cleared(qapp):
    from app.ui.canvas import Canvas

    c = Canvas()
    c.set_caption('  a.png · 1 × 1  ')
    assert c.caption() == 'a.png · 1 × 1'
    c.set_caption('')
    assert c.caption() == ''

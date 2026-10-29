"""主窗口冒烟测试（offscreen）：构造 + 显示 + 关闭，验证装配无误。"""
import os


def test_main_window_constructs(qapp):
    from app.ui.main_window import MainWindow

    win = MainWindow()
    assert win.canvas is not None
    assert win.panel is not None
    win.show()
    qapp.processEvents()
    win.close()
    qapp.processEvents()


def test_main_window_saves_session_on_close(qapp, tmp_path, monkeypatch):
    from app.ui import main_window
    from app.ui.main_window import MainWindow

    monkeypatch.setattr(main_window, '_SESSION_PATH', str(tmp_path / 'session.json'))
    win = MainWindow()
    win.session.patient_id = 'P_TEST'
    win.close()
    assert (tmp_path / 'session.json').exists()

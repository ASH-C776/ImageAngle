import os
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
# 会话 / 偏好文件默认写到 %APPDATA%\ImageAngle：测试必须在任何 app 模块被导入
# **之前**改掉数据目录，否则 main_window 模块级的 _SESSION_PATH 已经指向真实目录了。
os.environ.setdefault('IMAGEANGLE_DATA_DIR',
                      tempfile.mkdtemp(prefix='imageangle-test-'))

import pytest


@pytest.fixture(scope='session')
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolate_session_file(tmp_path, monkeypatch):
    """任何测试都不许写项目根目录的 session.json。

    历史上好几个测试直接 MainWindow() 然后 close()，closeEvent 会把当前会话
    写回真文件 —— 结果 session.json 里混进一堆 pytest 临时路径。这里统一
    重定向到本用例的 tmp_path，测试之间也顺带互不干扰。
    """
    from app.ui import main_window

    monkeypatch.setattr(main_window, '_SESSION_PATH',
                        str(tmp_path / 'session.json'), raising=False)
    # 窗口尺寸 / 面板开关偏好同样不能落到项目根目录（否则全量跑完就多一个
    # window_pref.json，还会让下一个用例以「上一个用例的窗口尺寸」启动）
    monkeypatch.setattr(main_window, '_WIN_PREF_PATH',
                        str(tmp_path / 'window_pref.json'), raising=False)


@pytest.fixture(autouse=True)
def _cleanup_windows(qapp):
    """每个用例结束后关掉所有顶层窗口。

    不清理的话，前一个用例的 MainWindow 还活着，它那个 700ms 防抖保存定时器
    会在后一个用例 processEvents() 时触发 —— 而那时 `_SESSION_PATH` 已经被
    改指到后一个用例的临时文件，于是把前一个窗口的会话写进了后一个用例的
    session.json（表现为「单独跑能过、全量跑就挂」）。
    """
    yield
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for w in list(app.topLevelWidgets()):
        try:
            w.close()
            w.deleteLater()
        except Exception:
            pass
    app.processEvents()

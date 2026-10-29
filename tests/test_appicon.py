"""任务栏 / 窗口图标的回归测试。

打包成 exe 后任务栏只有一个空白方块 —— 原因是程序从未设置窗口图标，
而资源管理器显示的是 EXE 文件里的图标资源，两者互不相干。这里锁住三件事：
图标能被找到、会被设到 QApplication 上、Windows 任务栏身份会自报。

（离屏环境下拿不到真实任务栏，只能验证到「Qt 已经拿到非空图标」这一层。）
"""
import sys


def test_resource_dir_points_to_existing_dir():
    from app.io import resources

    d = resources.resource_dir()
    assert d.endswith('resources')
    assert __import__('os').path.isdir(d)


def test_icon_path_prefers_ico():
    from app.io import resources

    p = resources.icon_path()
    assert p, 'resources/icon.ico 或 icon.png 必须存在'
    assert p.lower().endswith('.ico'), '优先用多尺寸 ico，任务栏小图标才清晰'


def test_set_taskbar_identity_returns_bool():
    from app.io import resources

    ok = resources.set_taskbar_identity()
    assert isinstance(ok, bool)
    if sys.platform.startswith('win'):
        assert ok is True


def test_apply_window_icon_sets_non_null_icon(qapp):
    from app.io import resources

    assert resources.apply_window_icon(qapp) is True
    icon = qapp.windowIcon()
    assert not icon.isNull()
    # 真实像素尺寸应覆盖任务栏需要的 16px 与 Alt+Tab 的 32px
    sizes = {(s.width(), s.height()) for s in icon.availableSizes()}
    assert (16, 16) in sizes
    assert (32, 32) in sizes


def test_main_window_inherits_window_icon(qapp):
    """QApplication 的默认图标要被新建窗口继承（否则任务栏还是空白）。"""
    from app.io import resources
    from app.ui.main_window import MainWindow

    resources.apply_window_icon(qapp)
    win = MainWindow()
    assert not win.windowIcon().isNull()
    win.close()
    qapp.processEvents()

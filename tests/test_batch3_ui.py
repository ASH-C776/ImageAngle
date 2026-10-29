"""第三批（交互 / UI）修复的回归测试。

覆盖：面板与列表图标区分、画布右键菜单（含画线时右键只取消不弹菜单）、
参考线标注只写「参考线」不显示自身角度、状态栏不再互相顶掉、
实际像素 100% 入口、窗口几何与面板开关的持久化。
"""
import json

import pytest
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QColor, QContextMenuEvent, QImage

from app.model.angle import Point


def _make_png(tmp_path, name='b3.png', w=800, h=400):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor('#7a7a7a'))
    p = tmp_path / name
    assert img.save(str(p))
    return str(p)


def _win(tmp_path, w=1100, h=720):
    from app.ui import main_window

    win = main_window.MainWindow()
    win.resize(w, h)
    win.show()
    from PySide6.QtWidgets import QApplication

    QApplication.instance().processEvents()
    return win


# ---------- 图标区分 ----------

def test_panel_icon_differs_from_list_icon(qapp):
    """「面板」（抽屉开关）与「列表」（图片列表）不能用同一个图标。"""
    from app.ui.icons import get_icon

    a = get_icon('panel').pixmap(18, 18).toImage()
    b = get_icon('list').pixmap(18, 18).toImage()
    assert not a.isNull()
    assert a != b


def test_toolbar_uses_distinct_icons(qapp):
    win = _win(__import__('pathlib').Path('.'))
    assert win.act_panel.icon().cacheKey() != win.act_list.icon().cacheKey()
    win.close()


# ---------- 画布右键菜单 ----------

def _menuless_canvas():
    """只测画布信号，不连主窗口（否则 menu.exec 会阻塞测试）。"""
    from app.model.session import ImageData
    from app.ui.canvas import Canvas

    c = Canvas()
    c.resize(600, 400)
    img = QImage(400, 300, QImage.Format.Format_RGB32)
    img.fill(QColor('#333333'))
    c.set_image(img, ImageData(file='x.png', width=400, height=300))
    return c


def _ctx_event(pos=QPoint(50, 50)):
    return QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, pos)


def test_context_menu_signal_emitted(qapp):
    c = _menuless_canvas()
    got = []
    c.contextMenuRequested.connect(got.append)
    c.contextMenuEvent(_ctx_event())
    assert len(got) == 1
    assert isinstance(got[0], QPoint)


def test_context_menu_selects_hit_tooth(qapp):
    c = _menuless_canvas()
    c.add_tooth(Point(100, 250), Point(100, 100))
    c._selected_seq = None
    got = []
    c.contextMenuRequested.connect(got.append)
    # 把牙轴向屏幕坐标转一下再右键，确保落在命中范围内
    mid = c.img_to_screen(QPointF(100, 175))
    c.contextMenuEvent(_ctx_event(QPoint(int(mid.x()), int(mid.y()))))
    assert c._selected_seq == c.image_data.teeth[0].seq
    assert len(got) == 1


def test_right_click_while_drawing_cancels_without_menu(qapp):
    """画线时右键语义是「取消」，这次右键不应紧接着弹出菜单。"""
    c = _menuless_canvas()
    c.set_mode(c.MODE_REF)
    got = []
    c.contextMenuRequested.connect(got.append)

    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent, Qt

    press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(100, 100), QPointF(100, 100),
                        Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
                        Qt.KeyboardModifier.NoModifier)
    c.mousePressEvent(press)
    assert c.mode == c.MODE_NONE          # 右键已取消画线
    c.contextMenuEvent(_ctx_event())
    assert got == []                      # 但没弹菜单
    # 下一次右键（不在画线中）应恢复正常
    c.contextMenuEvent(_ctx_event())
    assert len(got) == 1


# ---------- 参考线标注 ----------

def test_reference_label_shows_no_angle(qapp):
    """参考线旁只写名称：它自己斜几度不参与计算，标出来是噪音。"""
    from app.ui.canvas import reference_label_text

    txt = reference_label_text()
    assert txt == '参考线'
    assert '°' not in txt
    assert '腭中缝' not in txt


# ---------- 状态栏不再互相顶掉 ----------

def test_status_keeps_filename_and_nav(qapp, tmp_path):
    from app.ui import main_window

    win = _win(tmp_path)
    d = tmp_path / 'shots'
    d.mkdir()
    for name in ('a.png', 'b.png'):
        _make_png(tmp_path, name)
        (d / name).write_bytes((tmp_path / name).read_bytes())
    exts = {'.png'}
    files = sorted(str(p) for p in d.iterdir() if p.suffix.lower() in exts)
    win._folder_images = files
    win._goto(0)
    msg = win.statusBar().currentMessage()
    assert '第 1 / 2 张' in msg
    assert 'a.png' in msg
    win.close()


# ---------- 实际像素 100% ----------

def test_actual_pixels_resets_zoom(qapp, tmp_path):
    win = _win(tmp_path)
    win._open_path(_make_png(tmp_path))
    win.canvas._zoom = 0.42
    win._on_actual_pixels()
    assert win.canvas._zoom == pytest.approx(1.0)
    assert '实际像素' in win.statusBar().currentMessage()
    win.close()


# ---------- 窗口偏好持久化 ----------

def _pref_path():
    from app.ui import main_window

    return main_window._WIN_PREF_PATH


def test_window_pref_roundtrip(qapp, tmp_path):
    from app.ui import main_window

    win = main_window.MainWindow()
    win.setGeometry(140, 120, 1120, 700)
    win._save_window_pref()
    data = json.load(open(_pref_path(), encoding='utf-8'))
    assert data['geometry'][2:] == [1120, 700]
    win.close()

    win2 = main_window.MainWindow()
    assert win2.width() == 1120 and win2.height() == 700
    assert win2.x() == 140 and win2.y() == 120
    win2.close()


def test_window_pref_ignores_offscreen_geometry(qapp, tmp_path):
    """多屏改单屏 / 分辨率变小后，上次记的坐标可能在屏幕外，必须丢弃。"""
    from app.ui import main_window

    with open(_pref_path(), 'w', encoding='utf-8') as f:
        json.dump({'geometry': [99999, 99999, 1000, 700], 'maximized': False}, f)
    win = main_window.MainWindow()
    assert win.x() < 99999 and win.y() < 99999
    win.close()


def test_window_pref_restores_panel_override(qapp, tmp_path):
    from app.ui import main_window

    win = main_window.MainWindow()
    win.act_panel.setChecked(False)   # 用户关掉结果面板
    win._save_window_pref()
    win.close()

    win2 = main_window.MainWindow()
    assert win2._panel_user_override is False
    assert win2._panel_hidden is True
    win2.close()


def test_window_pref_corrupt_file_is_ignored(qapp, tmp_path):
    from app.ui import main_window

    with open(_pref_path(), 'w', encoding='utf-8') as f:
        f.write('{ not json')
    win = main_window.MainWindow()   # 不应抛异常
    assert win.width() >= win.minimumWidth()
    win.close()


def test_startup_is_empty_even_after_last_image(qapp, tmp_path):
    """启动必须是一张空白工作区：不自动打开上次的图，只看它记不记得测量。"""
    from app.ui import main_window

    p = _make_png(tmp_path, 'last.png')
    win = main_window.MainWindow()
    win._open_path(p)
    win.canvas.set_reference(Point(400, 20), Point(400, 380))
    win.canvas.add_tooth(Point(200, 300), Point(220, 120))
    win.close()                     # closeEvent 里写 last_path

    win2 = main_window.MainWindow()
    assert win2._current_path is None       # 不自动打开
    assert not win2.canvas.has_image()
    assert win2.canvas.caption() == ''
    # 但历史测量没丢：重新打开同一张图就都回来了
    win2._open_path(p)
    assert len(win2.canvas.image_data.teeth) == 1
    win2.close()


def test_startup_remembers_last_dir(qapp, tmp_path):
    """「打开」对话框要落在上次那个文件夹，这是 last_path 现在唯一的用途。"""
    from app.ui import main_window

    with open(_pref_path(), 'w', encoding='utf-8') as f:
        json.dump({'geometry': [80, 80, 1100, 700], 'maximized': False,
                   'last_path': str(tmp_path / 'gone.png')}, f)
    win = main_window.MainWindow()
    assert not win.canvas.has_image()
    assert win._last_dir == str(tmp_path)
    win.close()


def test_missing_last_image_is_skipped(qapp, tmp_path):
    from app.ui import main_window

    with open(_pref_path(), 'w', encoding='utf-8') as f:
        json.dump({'geometry': [80, 80, 1100, 700], 'maximized': False,
                   'last_path': str(tmp_path / 'gone.png')}, f)
    win = main_window.MainWindow()
    assert not win.canvas.has_image()      # 文件不在了就静默跳过
    win.close()

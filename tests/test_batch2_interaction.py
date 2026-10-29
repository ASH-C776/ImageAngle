"""第二批交互修复的回归测试。

覆盖：牙号校验（格式 / 重复）、工具栏按钮可用性、拖动端点不重建列表、
列表自动滚到选中行、拖入图片重置翻页列表、放大镜贴边不被裁。
"""
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage

from app.model.angle import Point


def _make_png(tmp_path, name='inter.png', w=800, h=400):
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


# ---------- 牙号（FDI）校验 ----------

@pytest.mark.parametrize('text', ['', '16', '18', '21', '28', '31', '38', '41', '48',
                                  '51', '55', '61', '85', ' 16 '])
def test_fdi_accepts_valid_codes(text):
    from app.model.protocol import is_valid_fdi

    assert is_valid_fdi(text)


@pytest.mark.parametrize('text', ['1', '19', '10', '49', '59', '86', 'ab', '00',
                                  'A1', '1a', '123'])
def test_fdi_rejects_invalid_codes(text):
    from app.model.protocol import is_valid_fdi

    assert not is_valid_fdi(text)


def test_invalid_fdi_is_rejected_and_restored(qapp, tmp_path):
    win = _win(tmp_path)
    p = _make_png(tmp_path)
    win._open_path(p)
    win.canvas.add_tooth(Point(100, 300), Point(120, 200))
    tooth = win.canvas.image_data.teeth[-1]

    win._apply_fdi(tooth, 'ab')
    assert tooth.fdi == ''
    assert '不合法' in win.statusBar().currentMessage()

    win._apply_fdi(tooth, '16')
    assert tooth.fdi == '16'
    win.close()


def test_duplicate_fdi_warns_but_is_kept(qapp, tmp_path):
    win = _win(tmp_path)
    win._open_path(_make_png(tmp_path))
    win.canvas.add_tooth(Point(100, 300), Point(120, 200))
    first = win.canvas.image_data.teeth[-1]
    win._apply_fdi(first, '16')
    win.canvas.add_tooth(Point(200, 300), Point(220, 200))
    second = win.canvas.image_data.teeth[-1]
    win._apply_fdi(second, '16')
    assert second.fdi == '16'          # 允许，但必须提示
    assert '重复' in win.statusBar().currentMessage()
    win.close()


# ---------- 工具栏按钮可用性 ----------

def test_tool_buttons_reflect_state(qapp, tmp_path):
    win = _win(tmp_path)
    # 未打开图片：除了打开 / 文件夹 / 面板，其余都该灰掉
    for act in (win.act_ref, win.act_tooth, win.act_fit, win.act_undo,
                win.act_del, win.act_clear, win.act_export):
        assert not act.isEnabled(), act.text()

    win._open_path(_make_png(tmp_path))
    qapp.processEvents()
    assert win.act_ref.isEnabled() and win.act_tooth.isEnabled()
    assert win.act_fit.isEnabled()
    # 空白图：没东西可撤销 / 删除 / 清空 / 导出
    assert not win.act_undo.isEnabled()
    assert not win.act_del.isEnabled()
    assert not win.act_clear.isEnabled()
    assert not win.act_export.isEnabled()

    win.canvas.add_tooth(Point(100, 300), Point(120, 200))
    qapp.processEvents()
    assert win.act_undo.isEnabled()
    assert win.act_del.isEnabled()
    assert win.act_clear.isEnabled()
    assert win.act_export.isEnabled()
    win.close()


# ---------- 拖动端点不逐帧重建列表 ----------

def test_drag_does_not_rebuild_list_each_frame(qapp, tmp_path):
    win = _win(tmp_path)
    win._open_path(_make_png(tmp_path))
    c = win.canvas
    for i in range(3):
        c.add_tooth(Point(100 + i * 60, 300), Point(120 + i * 60, 200))
    qapp.processEvents()

    calls = []
    orig = win.panel.refresh_list

    def counting(teeth, selected):
        calls.append(len(teeth))
        return orig(teeth, selected)

    win.panel.refresh_list = counting
    tooth = c.image_data.teeth[-1]
    c._selected_seq = tooth.seq
    c._drag = {'submode': c.MODE_DRAG_CROWN, 'grab': QPointF(0, 0),
               'before': c._drag_snapshot(c.MODE_DRAG_CROWN, tooth.seq)}

    for i in range(10):
        c._apply_drag(QPointF(400 + i, 180))
        qapp.processEvents()
    assert c.is_dragging()
    assert calls == [], '拖动过程中不应重建记录列表'

    c.mouseReleaseEvent(None)          # 松手：补一次全量刷新
    qapp.processEvents()
    assert not c.is_dragging()
    assert len(calls) == 1
    win.close()


# ---------- 列表自动滚到选中行 ----------

def test_new_tooth_scrolls_list_into_view(qapp, tmp_path):
    win = _win(tmp_path)
    win._open_path(_make_png(tmp_path))
    seen = []
    win.panel.scroll_to_seq = lambda seq: seen.append(seq)
    win.canvas.add_tooth(Point(100, 300), Point(120, 200))
    qapp.processEvents()
    assert seen == [1]
    assert win._scroll_to_seq is None   # 消费后清空，避免重复滚动
    win.close()


# ---------- 拖入图片重置翻页列表 ----------

def test_file_drop_resets_folder_navigation(qapp, tmp_path):
    win = _win(tmp_path)
    win._folder_images = ['a.png', 'b.png']
    win._folder_index = 1
    win._on_file_dropped(_make_png(tmp_path, 'dropped.png'))
    assert win._folder_images == []
    assert win._folder_index == -1
    assert not win.act_next.isEnabled()
    assert not win.act_prev.isEnabled()
    win.close()


# ---------- 放大镜贴边 ----------

def test_loupe_center_follows_cursor_when_there_is_room():
    from app.ui.canvas import loupe_center

    c = loupe_center(QPointF(400, 300), 800, 600)
    assert (c.x(), c.y()) == (464, 236)


@pytest.mark.parametrize('pos', [(2, 2), (798, 2), (2, 598), (798, 598),
                                 (400, 3), (797, 300)])
def test_loupe_center_stays_inside_canvas(pos):
    from app.ui.canvas import loupe_center

    r = 46.0
    c = loupe_center(QPointF(*pos), 800, 600, r)
    assert c.x() - r >= 0 and c.x() + r <= 800
    assert c.y() - r >= 0 and c.y() + r <= 600


def test_loupe_center_on_tiny_canvas():
    from app.ui.canvas import loupe_center

    c = loupe_center(QPointF(10, 10), 60, 40)
    assert (c.x(), c.y()) == (30, 20)

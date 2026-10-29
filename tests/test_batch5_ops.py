"""运维性优化：清空需确认、日志与异常兜底、图片列表显示已测条数。"""
import logging
import os
import sys

from PySide6.QtWidgets import QListWidget, QMessageBox

from app import applog


def _make_window(qapp, tmp_path, monkeypatch):
    from app.ui import main_window

    monkeypatch.setattr(main_window, '_SESSION_PATH', str(tmp_path / 'session.json'),
                        raising=False)
    monkeypatch.setattr(main_window, '_WIN_PREF_PATH', str(tmp_path / 'pref.json'),
                        raising=False)
    win = main_window.MainWindow()
    win.show()
    qapp.processEvents()
    return win


def _fake_image_data():
    from app.model.session import ImageData, Tooth

    d = ImageData(file='x.png', width=400, height=400)
    d.reference = {'x1': 200, 'y1': 20, 'x2': 200, 'y2': 380, 'type': 'palatal_midline'}
    d.teeth.append(Tooth(seq=1, fdi='16', root={'x': 100.0, 'y': 300.0},
                         crown={'x': 110.0, 'y': 100.0}, angle_deg=3.0))
    return d


def _load_canvas(win):
    """给画布塞一张图 + 一条牙长轴（不走文件，避免依赖磁盘图片）。"""
    from PySide6.QtGui import QColor, QImage

    qimg = QImage(400, 400, QImage.Format.Format_RGB32)
    qimg.fill(QColor('#333333'))
    win._current_path = None       # 不往 session 里登记
    win.canvas.set_image(qimg, _fake_image_data())
    win._refresh_panel()
    return win.canvas.image_data


# ---------- 清空：确认 + 键位 ----------

def test_clear_asks_for_confirmation(qapp, tmp_path, monkeypatch):
    """弹了确认、用户没点「清空」→ 一条都不许删。"""
    win = _make_window(qapp, tmp_path, monkeypatch)
    data = _load_canvas(win)
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: 0)
    win._on_clear()
    assert len(data.teeth) == 1
    win.close()


def test_clear_proceeds_when_confirmed(qapp, tmp_path, monkeypatch):
    win = _make_window(qapp, tmp_path, monkeypatch)
    data = _load_canvas(win)

    def _click_yes(box):
        for b in box.buttons():
            if b.text() == '清空':
                b.click()
        return 1

    monkeypatch.setattr(QMessageBox, 'exec', _click_yes)
    win._on_clear()
    assert not data.teeth
    assert data.reference is None
    # 清空进撤销栈，Ctrl+Z 能回来
    assert win.canvas.undo() is True
    assert len(data.teeth) == 1
    win.close()


def test_clear_shortcut_is_no_longer_redo_keys(qapp, tmp_path, monkeypatch):
    win = _make_window(qapp, tmp_path, monkeypatch)
    seq = win.act_clear.shortcut().toString()
    assert seq == 'Ctrl+Shift+Del'
    assert 'Z' not in seq
    win.close()


def test_clear_on_empty_image_does_not_prompt(qapp, tmp_path, monkeypatch):
    """没有任何内容时不该弹窗打扰。"""
    win = _make_window(qapp, tmp_path, monkeypatch)
    called = []
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: called.append(1) or 0)
    win._on_clear()
    assert not called
    win.close()


# ---------- 日志 ----------

def _reset_logger():
    applog._configured = False
    logger = logging.getLogger('imageangle')
    for h in list(logger.handlers):
        logger.removeHandler(h)


def test_logging_writes_to_data_dir(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv('IMAGEANGLE_DATA_DIR', str(tmp_path / 'data'))
    _reset_logger()
    applog.setup_logging()
    applog.get_logger('ui.test').warning('一条测试日志')
    for h in logging.getLogger('imageangle').handlers:
        h.flush()

    text = open(applog.log_path(), encoding='utf-8').read()
    assert '一条测试日志' in text
    assert 'imageangle.ui.test' in text


def test_excepthook_logs_and_notifies(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv('IMAGEANGLE_DATA_DIR', str(tmp_path / 'data2'))
    _reset_logger()
    applog.setup_logging()

    notes = []
    monkeypatch.setattr(applog, '_notify', notes.append)
    old = sys.excepthook
    try:
        applog.install_excepthook()
        try:
            raise ValueError('boom')
        except ValueError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = old

    assert notes and 'ValueError' in notes[0]
    for h in logging.getLogger('imageangle').handlers:
        h.flush()
    text = open(applog.log_path(), encoding='utf-8').read()
    assert '未捕获异常' in text and 'boom' in text


# ---------- 图片列表显示已测条数 ----------

def test_image_list_marks_measured_counts(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from app.model.session import ImageData, Tooth

    win = _make_window(qapp, tmp_path, monkeypatch)
    a = str(tmp_path / 'a.png')
    b = str(tmp_path / 'b.png')
    win._folder_images = [a, b]
    win._folder_index = 0
    img = ImageData(file=os.path.abspath(a))
    img.teeth = [Tooth(seq=1), Tooth(seq=2)]
    win.session.images[os.path.abspath(a)] = img

    captured = {}

    def _fake_exec(dlg):
        lw = dlg.findChild(QListWidget)
        captured['items'] = [lw.item(i).text() for i in range(lw.count())]
        captured['tooltip'] = lw.item(0).toolTip()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, 'exec', _fake_exec)
    win._show_image_list()

    assert '已测 2 条' in captured['items'][0]
    assert '（当前）' in captured['items'][0]
    assert '未测' in captured['items'][1]
    assert '已测 2 条' in captured['tooltip']
    win.close()

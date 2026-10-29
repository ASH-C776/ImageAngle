"""第四批修复的回归测试：角度符号同源、数据目录、CSV 路径列、面板空白态文案。"""
import json
import os

from app.model.angle import Point, compute_angle, measure

# 参考线：明显向右倾（画成从上往下，测试「画线方向不影响结果」）
_REF_UP_RIGHT = (Point(0, 100), Point(20, 0))


def test_vertical_tooth_against_tilted_reference():
    """牙轴完全竖直、参考线斜 11°：幅值照给，但不臆造方向。

    旧实现用「角度差」定符号，会给出一个 −11.31°「远中」—— 可牙冠根本没偏。
    现在方向只看 dx（=0）→ 无方向，角度只报幅值。
    """
    res = measure(Point(100, 100), Point(100, 50), *_REF_UP_RIGHT, 400, '16')
    assert abs(abs(res.angle_deg) - 11.31) < 0.05
    assert res.angle_deg > 0
    assert res.direction is None


def test_reference_draw_direction_does_not_matter():
    """参考线从上往下画 / 从下往上画，结果必须完全一致。"""
    a = compute_angle(Point(100, 100), Point(120, 50), Point(0, 100), Point(0, 0), 400, '16')
    b = compute_angle(Point(100, 100), Point(120, 50), Point(0, 0), Point(0, 100), 400, '16')
    assert a == b


def test_subpixel_jitter_does_not_flip_direction():
    """牙轴接近竖直时 ±0.4px 抖动不应让符号翻转（落在死区内 → 无方向）。"""
    ref = _REF_UP_RIGHT
    a = measure(Point(100, 100), Point(100.4, 50), *ref, 400, '16')
    b = measure(Point(100, 100), Point(99.6, 50), *ref, 400, '16')
    assert a.direction is None and b.direction is None
    assert (a.angle_deg > 0) == (b.angle_deg > 0)


def test_zero_degree_has_no_direction():
    """竖直牙轴 = 0°，不该被标成「近中」。"""
    res = measure(Point(100, 100), Point(100, 50), Point(0, 0), Point(0, 100), 400, '16')
    assert res.angle_deg == 0
    assert res.direction is None


# ---------- 数据目录 ----------

def test_data_dir_honours_env(tmp_path, monkeypatch):
    from app.io import paths

    monkeypatch.setenv('IMAGEANGLE_DATA_DIR', str(tmp_path / 'd'))
    assert paths.data_dir() == str(tmp_path / 'd')
    assert os.path.isdir(paths.data_dir())
    assert paths.session_path().endswith('session.json')


def test_migrate_legacy_copies_without_overwriting(tmp_path, monkeypatch):
    from app.io import paths

    legacy = tmp_path / 'legacy'
    legacy.mkdir()
    (legacy / 'session.json').write_text('{"old": 1}', encoding='utf-8')
    (legacy / 'theme_pref.json').write_text('light', encoding='utf-8')
    target = tmp_path / 'data'
    target.mkdir()
    (target / 'theme_pref.json').write_text('dark', encoding='utf-8')

    monkeypatch.setattr(paths, '_LEGACY_DIR', str(legacy))
    monkeypatch.setenv('IMAGEANGLE_DATA_DIR', str(target))
    moved = paths.migrate_legacy()

    assert moved == ['session.json']          # theme_pref 已存在，不覆盖
    assert json.loads((target / 'session.json').read_text(encoding='utf-8')) == {'old': 1}
    assert (target / 'theme_pref.json').read_text(encoding='utf-8') == 'dark'


# ---------- CSV ----------

def test_csv_has_full_image_path_and_case_fields(tmp_path):
    from app.io.csv_exporter import export_session_csv
    from app.model.session import ImageData, Session, Tooth

    img = ImageData(file=str(tmp_path / 'sub' / '01.png'), width=10, height=10)
    img.teeth.append(Tooth(seq=1, fdi='16', angle_deg=1.5))
    s = Session(patient_id='P-1', operator_id='李医生')
    out = tmp_path / 'o.csv'
    export_session_csv(s, str(out), images=[img])

    head, row = out.read_text(encoding='utf-8-sig').splitlines()[:2]
    cols = head.split(',')
    assert 'image_path' in cols
    vals = dict(zip(cols, row.split(',')))
    assert vals['patient_id'] == 'P-1'
    assert vals['operator_id'] == '李医生'
    assert vals['image_file'] == '01.png'
    assert vals['image_path'].replace('\\', '/').endswith('sub/01.png')


# ---------- 面板空白态 ----------

def test_show_blank_uses_given_message(qapp):
    from app.ui.result_panel import ResultPanel

    panel = ResultPanel()
    panel.show_blank('自定义提示')
    assert panel._cur_sig[7] == '自定义提示'
    panel.show_blank('')
    assert panel._cur_sig[7] == '先画参考线，再在牙上标记牙长轴'
    panel.close()


# ---------- 导出前的病例信息对话框 ----------

def test_patient_dialog_cancel_keeps_session(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from app.ui import main_window

    win = main_window.MainWindow()
    win.session.patient_id = 'P0'
    monkeypatch.setattr(QDialog, 'exec', lambda self: QDialog.DialogCode.Rejected)
    assert win._ask_patient_info() is False
    assert win.session.patient_id == 'P0'
    win.close()


def test_patient_dialog_ok_writes_session(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QLineEdit

    from app.ui import main_window

    win = main_window.MainWindow()
    win.session.patient_id = 'P-20261029'
    win.session.operator_id = '李医生'

    def _fake_exec(dlg):
        # 对话框里的输入框已用 session 的值预填，这里确认预填 + 走「确定」
        edits = dlg.findChildren(QLineEdit)
        assert [e.text() for e in edits] == ['P-20261029', '李医生']
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, 'exec', _fake_exec)
    assert win._ask_patient_info() is True
    assert (win.session.patient_id, win.session.operator_id) == ('P-20261029', '李医生')
    win.close()


def test_runtime_files_live_outside_program_dir(qapp, monkeypatch):
    """运行期文件必须落在用户数据目录，而不是程序目录（打包后那里只读）。"""
    from app.io import paths

    program_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(paths.__file__))))
    for p in (paths.session_path(), paths.window_pref_path(), paths.theme_pref_path()):
        assert os.path.dirname(p) == paths.data_dir()
        assert os.path.abspath(os.path.dirname(p)) != os.path.abspath(program_dir)

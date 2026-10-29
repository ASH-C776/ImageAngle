"""CSV 导出回归：导出内容必须来自当前画布数据、字段值为英文码、表格首行是表头。

历史 bug（2026-10-29 发现）：`_on_export_csv` 传 `only_path` 让导出器去
`session.images[路径]` 取图，但打开的图片从未登记进 session（打开即新建空白
ImageData）。结果：路径没登记过 → KeyError 导出失败；路径恰好是历史图 → 导出
上一次会话的旧测量数据。
"""
import csv
import io

from PySide6.QtGui import QColor, QImage

from app.model.protocol import NOTE_NO_FDI

from app.io.csv_exporter import CSV_FIELDS, export_session_csv
from app.model.angle import Point
from app.model.session import ImageData, Session, Tooth


def _img(with_data=True):
    img = ImageData(file='/tmp/panorama_甲.png', width=1600, height=700)
    img.reference = {'x1': 800.0, 'y1': 60.0, 'x2': 800.0, 'y2': 640.0,
                     'type': 'palatal_midline'}
    if with_data:
        img.teeth = [
            Tooth(seq=1, fdi='16', root={'x': 480.0, 'y': 480.0},
                  crown={'x': 521.0, 'y': 326.0}, angle_deg=14.91,
                  direction='近中', confidence='高', note=''),
            Tooth(seq=2, fdi='', root={'x': 1120.0, 'y': 480.0},
                  crown={'x': 1080.0, 'y': 326.0}, angle_deg=-14.56,
                  direction='远中', confidence='',
                  note=NOTE_NO_FDI),
        ]
    return img


def _read(path):
    raw = open(path, encoding='utf-8-sig').read()
    return raw, list(csv.DictReader(io.StringIO(raw)))


def test_export_is_plain_table_with_english_values(tmp_path):
    out = tmp_path / 'out.csv'
    n = export_session_csv(Session(), str(out), images=[_img()])
    assert n == 2

    raw, rows = _read(str(out))
    assert raw.startswith('patient_id,'), '首行必须是表头，不能有 # 注释行'
    assert list(rows[0].keys()) == CSV_FIELDS
    assert rows[0]['direction'] == 'mesial'
    assert rows[0]['confidence'] == 'high'
    assert rows[0]['tooth_fdi'] == '16'
    assert rows[0]['axis_inclination_deg'] == '14.91'
    assert rows[0]['image_file'] == 'panorama_甲.png'
    assert rows[0]['flipped'] == 'false'
    assert rows[1]['direction'] == 'distal'
    assert rows[1]['confidence'] == ''
    assert rows[1]['flags'] == 'no_fdi'


def test_export_uses_canvas_data_not_other_session_images(tmp_path, qapp):
    """导出的是画布上这张图的数据，会话里别的图的记录不能混进来。

    早期实现按「当前路径」去 session.images 反查，打开的新图没登记时要么
    KeyError、要么导出上一次会话的旧数据。现在改成直接导画布数据。
    """
    from app.ui import main_window

    qapp_img = QImage(400, 200, QImage.Format.Format_RGB32)
    qapp_img.fill(QColor('#666666'))
    p = tmp_path / 'x.png'
    assert qapp_img.save(str(p))

    win = main_window.MainWindow()
    # 会话里有另一张图的记录（角度 99°，明显不该出现在本次导出里）
    other_path = str(tmp_path / 'other.png')
    stale = ImageData(file=other_path, width=400, height=200)
    stale.teeth = [Tooth(seq=9, fdi='11', angle_deg=99.0, direction='近中')]
    win.session.images[other_path] = stale

    win._open_path(str(p))
    win.canvas.set_reference(Point(200, 20), Point(200, 180))
    win.canvas.add_tooth(Point(100, 150), Point(120, 60))
    win.canvas.image_data.teeth[-1].fdi = '21'

    out = tmp_path / 'cur.csv'
    n = export_session_csv(win.session, str(out), images=[win.canvas.image_data])
    _, rows = _read(str(out))
    assert n == 1 and len(rows) == 1
    assert rows[0]['tooth_fdi'] == '21'
    assert rows[0]['axis_inclination_deg'] != '99.00'
    win.close()


def test_export_without_reference_and_empty_image(tmp_path):
    out = tmp_path / 'a.csv'
    img = _img()
    img.reference = None
    img.teeth[0].angle_deg = None
    img.teeth[0].direction = None
    img.teeth[0].note = '无参考线'
    n = export_session_csv(Session(), str(out), images=[img])
    _, rows = _read(str(out))
    assert n == 2
    assert rows[0]['axis_inclination_deg'] == ''
    assert rows[0]['direction'] == ''
    assert rows[0]['flags'] == 'no_reference'
    assert rows[0]['ref_x1'] == ''


def test_missing_only_path_is_not_an_error(tmp_path):
    out = tmp_path / 'b.csv'
    n = export_session_csv(Session(), str(out), only_path='/nope/none.png')
    assert n == 0
    raw, _ = _read(str(out))
    assert raw.strip().startswith('patient_id,')


def test_include_meta_still_available(tmp_path):
    out = tmp_path / 'c.csv'
    export_session_csv(Session(), str(out), images=[_img()], include_meta=True)
    raw = open(str(out), encoding='utf-8-sig').read()
    assert raw.startswith('# ImageAngle export')
    assert 'direction_convention=radiological' in raw

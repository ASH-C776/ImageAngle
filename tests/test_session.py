"""会话模型测试：保存/恢复往返、序号、重复牙位查找。"""
from app.model.session import ImageData, Session, Tooth


def test_save_load_roundtrip(tmp_path):
    s = Session(operator_id='op1', patient_id='P1')
    img = ImageData(file=r'D:\x\a.jpg')
    s.images[img.file] = img
    img.width, img.height = 3000, 1200
    img.reference = {'x1': 0, 'y1': 0, 'x2': 0, 'y2': 100, 'type': 'palatal_midline'}
    img.teeth.append(Tooth(seq=1, fdi='16', root={'x': 1.0, 'y': 2.0},
                           crown={'x': 3.0, 'y': 4.0}, angle_deg=12.5,
                           direction='近中', confidence='中'))
    p = tmp_path / 'session.json'
    s.save(str(p))

    s2 = Session.load(str(p))
    assert s2.operator_id == 'op1'
    assert s2.patient_id == 'P1'
    assert s2.direction_convention == 'radiological'
    img2 = s2.images[r'D:\x\a.jpg']
    assert img2.width == 3000 and img2.height == 1200
    assert img2.flipped is False
    assert img2.reference['type'] == 'palatal_midline'
    t = img2.teeth[0]
    assert t.seq == 1 and t.fdi == '16'
    assert t.angle_deg == 12.5 and t.direction == '近中' and t.confidence == '中'


def test_next_seq_and_empty_fdi():
    img = ImageData(file='a.jpg')
    img.teeth.append(Tooth(seq=1, fdi='16'))
    img.teeth.append(Tooth(seq=2, fdi=''))
    assert img.next_seq() == 3
    assert [t.fdi for t in img.teeth] == ['16', '']

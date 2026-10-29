"""方向算法修复的回归测试：上颌/下颌同规则、旧会话按新算法重算。"""
import os

from app.model.angle import Point, measure

REF = (Point(200, 380), Point(200, 20))   # 竖直参考线，中线 x=200


def test_upper_and_lower_produce_same_sign():
    """上颌（冠在下）与下颌（冠在上）在同样朝中线倾斜时，符号必须相同。

    这是 v1.0 的 bug：用「牙轴角度 − 参考线角度」定符号，normalize 折叠到
    [-90, 90] 后，牙轴朝下的符号含义翻转，导致上颌牙全部反号。
    """
    upper = measure(Point(100, 150), Point(120, 250), *REF, 400, '11')
    lower = measure(Point(100, 250), Point(120, 150), *REF, 400, '41')
    assert upper.direction == lower.direction == '近中'
    assert upper.angle_deg == lower.angle_deg > 0


def test_all_four_quadrants_mesial_when_crown_toward_midline():
    """四象限各取一颗，牙冠都朝中线 → 全部近中、全为正。"""
    cases = [
        ('11', Point(100, 150), Point(120, 250)),
        ('21', Point(300, 150), Point(280, 250)),
        ('41', Point(100, 250), Point(120, 150)),
        ('31', Point(300, 250), Point(280, 150)),
    ]
    for fdi, root, crown in cases:
        res = measure(root, crown, *REF, 400, fdi)
        assert res.direction == '近中', fdi
        assert res.angle_deg > 0, fdi


def test_open_path_recomputes_legacy_angle(qapp, tmp_path):
    """旧会话里存着按旧算法算错的角度，打开后必须按新算法重算。"""
    from PySide6.QtGui import QImage

    from app.model.session import ImageData, Session, Tooth
    from app.ui import main_window
    from app.ui.main_window import MainWindow

    png = tmp_path / 'legacy.png'
    img = QImage(400, 200, QImage.Format.Format_RGB32)
    img.fill(0)
    img.save(str(png))
    path = os.path.abspath(str(png))

    sess = Session()
    data = ImageData(file=path, width=400, height=200)
    data.reference = {'x1': 200, 'y1': 20, 'x2': 200, 'y2': 180}
    # 上颌牙冠偏右（朝中线）本该是 +21.8 近中，旧算法存成了反号
    data.teeth.append(Tooth(seq=1, fdi='16', root={'x': 100.0, 'y': 40.0},
                            crown={'x': 121.0, 'y': 140.0},
                            angle_deg=-24.9, direction='远中'))
    sess.images[path] = data
    sess.save(main_window._SESSION_PATH)

    win = MainWindow()
    try:
        win._open_path(path)
        t = win.canvas.image_data.teeth[0]
        assert t.angle_deg > 0, f'旧值没被重算：{t.angle_deg}'
        assert t.direction == '近中'
    finally:
        win.close()
        qapp.processEvents()

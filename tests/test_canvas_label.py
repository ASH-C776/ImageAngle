"""画布上的角度标注：只显示度数；选中记录时标注变绿（不再是近黑色）。"""
import pytest


def _tooth(angle, fdi='16', direction='近中'):
    from app.model.session import Tooth

    t = Tooth(seq=1, root={'x': 100, 'y': 200}, crown={'x': 110, 'y': 100})
    t.fdi = fdi
    t.angle_deg = angle
    t.direction = direction
    return t


@pytest.mark.parametrize('angle', [16.7, -14.74, 0.0, 45.0])
def test_label_shows_only_degrees(angle):
    from app.ui.canvas import tooth_label_text

    txt = tooth_label_text(_tooth(angle))
    assert txt == f'{angle:+.1f}°'
    # 方向词、牙位提示等附加信息一律不再出现在画面上
    for extra in ('近中', '远中', '未填牙位', '（', '）'):
        assert extra not in txt


def test_label_keeps_sign_and_one_decimal():
    from app.ui.canvas import tooth_label_text

    assert tooth_label_text(_tooth(6.34)) == '+6.3°'
    assert tooth_label_text(_tooth(-14.74)) == '-14.7°'


def test_label_when_no_reference():
    from app.ui.canvas import tooth_label_text

    t = _tooth(None)
    assert tooth_label_text(t) == '无参考线'


def test_selected_label_color_is_not_theme_text():
    """选中态曾经用主题文字色，亮色主题下是近黑色，压在 X 光片上看不见。"""
    from app.ui import theme
    from app.ui import canvas as cv

    for name in ('dark', 'light'):
        theme.set_theme(name)
        # 选中色不随主题变化（画在片子上，必须始终够亮）
        assert cv.COLOR_SEL_TXT == cv.QColor(34, 203, 168)
        luma = cv._luma(cv.COLOR_SEL_TXT)
        assert 0.4 < luma < 0.8, '选中色应当够亮，且不是纯白'
        # 与默认红色有明显色相差，一眼能区分
        assert abs(cv.COLOR_SEL_TXT.green() - cv.COLOR_SEL_TXT.red()) > 80
        # 与主题文字色不同（正是旧实现的 bug 来源）
        assert cv.COLOR_SEL_TXT != cv.QColor(theme.C_TEXT)
    theme.set_theme('dark')


def test_label_halo_contrasts_with_text():
    from app.ui.canvas import _luma
    from PySide6.QtGui import QColor

    bright = QColor(239, 68, 68)     # 亮红：应当描黑边
    dark = QColor(40, 40, 40)        # 近黑：应当描白边
    assert _luma(bright) > 0.40
    assert _luma(dark) < 0.40

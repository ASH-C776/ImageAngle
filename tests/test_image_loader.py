"""图片加载测试：中文路径、格式覆盖、16 位影像转换。"""
import numpy as np
from PySide6.QtGui import QImage

from app.io.image_loader import convert_for_qt, image_size, load_image, to_uint8


def _save_qimage(qimg, path, fmt=None):
    ok = qimg.save(str(path), fmt) if fmt else qimg.save(str(path))
    assert ok, f'测试图写入失败: {path}'


def _rgb_image(w=30, h=20, value=(30, 60, 90)):
    arr = np.zeros((h, w, 3), np.uint8)
    arr[:, :] = value
    return QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def _gray16_image(vals, h=40, w=60):
    arr = np.ascontiguousarray(np.asarray(vals, np.uint16).reshape(h, w))
    return QImage(arr.data, w, h, 2 * w, QImage.Format.Format_Grayscale16).copy(), arr


def test_load_unicode_path(tmp_path):
    p = tmp_path / '全景片_测试.png'
    _save_qimage(_rgb_image(), p)

    img = load_image(str(p))
    w, h = image_size(img)
    assert (w, h) == (30, 20)


def test_unsupported_format(tmp_path):
    p = tmp_path / 'a.txt'
    p.write_text('x', encoding='utf-8')
    try:
        load_image(str(p))
    except ValueError as exc:
        assert '不支持' in str(exc)
    else:
        raise AssertionError('应抛出 ValueError')


def test_missing_file(tmp_path):
    p = tmp_path / 'not_exist.jpg'
    try:
        load_image(str(p))
    except ValueError as exc:
        assert '不存在' in str(exc)
    else:
        raise AssertionError('应抛出 ValueError')


def test_corrupt_file_reports_decode_error(tmp_path):
    p = tmp_path / 'broken.png'
    p.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 40)
    try:
        load_image(str(p))
    except ValueError as exc:
        assert '解码' in str(exc)
    else:
        raise AssertionError('应抛出 ValueError')


def test_rgb_pixel_order_is_rgb(tmp_path):
    """加载后通道序必须是 RGB（Qt 约定），颜色不能红蓝互换。"""
    p = tmp_path / 'color.png'
    _save_qimage(_rgb_image(value=(10, 120, 240)), p)
    img = load_image(str(p))
    assert img.ndim == 3 and img.shape[2] == 3
    r, g, b = (int(img[0, 0, i]) for i in range(3))
    assert abs(r - 10) <= 1 and abs(g - 120) <= 1 and abs(b - 240) <= 1


def test_rgba_png_keeps_four_channels(tmp_path):
    p = tmp_path / 'alpha.png'
    arr = np.zeros((20, 30, 4), np.uint8)
    arr[:, :] = (200, 40, 40, 128)
    q = QImage(arr.data, 30, 20, 120, QImage.Format.Format_RGBA8888).copy()
    _save_qimage(q, p)
    img = load_image(str(p))
    assert img.ndim == 3 and img.shape[2] == 4


# ---------- 16 位 / 非 8 位影像 ----------

def test_to_uint8_16bit_keeps_gradient():
    """16 位线性渐变 → 8 位后仍是渐变，且用满 0~255（不是除以 65535 的暗图）。"""
    arr = np.linspace(0, 65535, 64 * 64).reshape(64, 64).astype(np.uint16)
    out = to_uint8(arr)
    assert out.dtype == np.uint8
    assert out.min() <= 3
    assert out.max() >= 250
    # 单调不减（同一行从左到右应越来越亮）
    row = out[0]
    assert np.all(np.diff(row.astype(int)) >= 0)


def test_to_uint8_12bit_data_is_not_crushed():
    """12 位数据（0~4095）不能因为按 16 位归一化而变成一片黑。"""
    arr = np.linspace(0, 4095, 100).astype(np.uint16).reshape(10, 10)
    out = to_uint8(arr)
    assert out.max() >= 250


def test_to_uint8_passthrough_for_8bit():
    arr = np.arange(256, dtype=np.uint8).reshape(16, 16)
    assert to_uint8(arr) is arr


def test_convert_16bit_tiff_is_monochrome(tmp_path):
    """16 位灰度 TIFF 之前会被当成 RGB888 解释，显示成彩色花屏。"""
    p = tmp_path / 'wide.tif'
    q, _ = _gray16_image(np.linspace(0, 65535, 40 * 60))
    _save_qimage(q, p, 'TIFF')

    loaded = load_image(str(p))
    assert loaded.dtype == np.uint16
    assert loaded.shape == (40, 60)
    q = convert_for_qt(loaded)
    assert q.width() == 60 and q.height() == 40

    # 同一个像素的 R/G/B 必须相等（灰度），且明暗与实际亮度一致
    dark = q.pixelColor(0, 0)
    bright = q.pixelColor(59, 39)
    assert dark.red() == dark.green() == dark.blue()
    assert bright.red() == bright.green() == bright.blue()
    assert bright.red() > dark.red() + 200


def test_16bit_tiff_roundtrip_preserves_values(tmp_path):
    """16 位 TIFF 进出一次，像素值不能被量化/截断（12 位设备靠这个保精度）。"""
    p = tmp_path / 'lzw.tif'
    q, _ = _gray16_image((np.arange(40 * 60) * 3).astype(np.uint16))
    _save_qimage(q, p, 'TIFF')
    loaded = load_image(str(p))
    assert loaded.dtype == np.uint16
    assert int(loaded.max()) == int(40 * 60 * 3 - 3)

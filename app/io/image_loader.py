"""图片读取：JPG/JPEG/PNG/TIFF/BMP。

解码交给 Qt 自带的 QImageReader，不再依赖 OpenCV：

* **Unicode 路径**：QImageReader 在 Windows 上直接吃中文路径；OpenCV 的 imread
  不行（原先要靠 ``np.fromfile`` + ``cv2.imdecode`` 绕一圈）。
* **位深**：16 位 TIFF 读出来是 ``Format_Grayscale16``，位深完整保留，交给
  :func:`to_uint8` 按 0.5%~99.5% 分位拉伸。
* **体积**：OpenCV 会给安装包塞进 41 MB（cv2.pyd + ffmpeg 视频后端），而本程序
  只用得上「解码」一件事。

返回值的通道序是 **RGB / RGBA**（Qt 的心智模型），不是 OpenCV 的 BGR ——
转换到 QImage 时不再需要交换通道。灰度影像返回二维数组。
"""
from __future__ import annotations

import os
from typing import Tuple

import numpy as np
from PySide6.QtGui import QImage, QImageReader

from ..model.protocol import IMAGE_EXTENSIONS

#: 16 位（每通道两字节）的 QImage 格式
_16BIT_FORMATS = frozenset({
    QImage.Format.Format_Grayscale16,
    QImage.Format.Format_RGBX64,
    QImage.Format.Format_RGBA64,
    QImage.Format.Format_RGBA64_Premultiplied,
})


def is_supported(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def load_image(path: str):
    """读取图片，返回 (h, w) 灰度 或 (h, w, 3)/(h, w, 4) 的 ndarray。

    8 位图返回 uint8，16 位图返回 uint16（由 :func:`to_uint8` 负责拉伸）。
    失败抛 ValueError。
    """
    if not is_supported(path):
        raise ValueError(f'不支持的图片格式: {path}')
    if not os.path.exists(path):
        raise ValueError(f'文件不存在: {path}')
    if os.path.getsize(path) == 0:
        raise ValueError(f'文件为空: {path}')

    reader = QImageReader(path)
    # 按文件内容判断格式，而不是只看扩展名：导出的片子经常扩展名和内容不符
    reader.setDecideFormatFromContent(True)
    qimg = reader.read()
    if qimg.isNull():
        detail = reader.errorString() or '未知错误'
        raise ValueError(f'无法解码图片（文件损坏或格式不支持）: {path}（{detail}）')
    return qimage_to_array(qimg)


def qimage_to_array(qimg: QImage) -> np.ndarray:
    """QImage → ndarray，尽量少拷贝、少改格式。"""
    fmt = qimg.format()

    if fmt == QImage.Format.Format_Grayscale8:
        return _as_array(qimg, 1, np.uint8)
    if fmt == QImage.Format.Format_Grayscale16:
        return _as_array(qimg, 1, np.uint16)

    if fmt in _16BIT_FORMATS:
        # 16 位彩色（少见，但有些设备会导出）：统一成 RGBA64 再取 4 通道
        return _as_array(qimg.convertToFormat(QImage.Format.Format_RGBA64), 4, np.uint16)

    if qimg.hasAlphaChannel():
        return _as_array(qimg.convertToFormat(QImage.Format.Format_RGBA8888), 4, np.uint8)

    # RGB32/ARGB32/Indexed8 等一律落到紧凑的 RGB888
    if fmt != QImage.Format.Format_RGB888:
        qimg = qimg.convertToFormat(QImage.Format.Format_RGB888)
    return _as_array(qimg, 3, np.uint8)


def _as_array(qimg: QImage, channels: int, dtype) -> np.ndarray:
    """把 QImage 的像素缓冲按行拷成连续 ndarray（处理 bytesPerLine 的行尾填充）。"""
    width, height = qimg.width(), qimg.height()
    stride = qimg.bytesPerLine()
    itemsize = np.dtype(dtype).itemsize
    row_bytes = width * channels * itemsize

    raw = np.frombuffer(qimg.constBits(), dtype=np.uint8, count=stride * height)
    rows = raw.reshape(height, stride)[:, :row_bytes].copy()   # 去掉每行末尾的对齐填充
    arr = rows.view(dtype) if itemsize > 1 else rows
    if channels == 1:
        return arr.reshape(height, width)
    return arr.reshape(height, width, channels)


def image_size(img) -> Tuple[int, int]:
    """返回 (width, height)。"""
    h, w = img.shape[:2]
    return w, h


def to_uint8(img):
    """把 16 位 / 有符号 / 浮点影像线性拉伸到 8 位。

    全景机导出的 TIFF 常见 16 位（有的实际只用 12/14 位），若直接把 uint16
    的内存按 RGB888 解释，高低字节会被当成两个像素通道 —— 画面变成满屏
    花绿噪点。这里按 0.5%~99.5% 分位拉伸到 0~255：既不会整体发黑（除以
    65535 会让 12 位数据只剩 1/16 亮度），也不会被个别过曝像素压扁动态范围。

    8 位输入原样返回（不做对比度调整，保留医生看到的原始观感）。
    """
    if img.dtype == np.uint8:
        return img
    if img.dtype.kind not in 'ui f':
        return img.astype(np.uint8)

    # 有 alpha 通道时只按颜色通道定标，否则恒为满值的 alpha 会把分位数顶到 65535
    sample = img
    if img.ndim == 3 and img.shape[2] in (2, 4):
        sample = img[:, :, 0]
    flat = sample.reshape(-1)
    lo, hi = np.percentile(flat.astype(np.float32), (0.5, 99.5))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo, hi = float(flat.min()), float(flat.max())
        if hi <= lo:
            hi = lo + 1.0
    out = (img.astype(np.float32) - lo) * (255.0 / (hi - lo))
    return np.clip(out, 0, 255).astype(np.uint8)


def convert_for_qt(img):
    """ndarray(RGB/RGBA/灰度，8/16 位) → QImage。"""
    img = to_uint8(img)
    arr = np.ascontiguousarray(img)

    if arr.ndim == 3 and arr.shape[2] == 1:
        arr = arr[:, :, 0]
    if arr.ndim == 2:
        h, w = arr.shape
        return QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8).copy()

    h, w, channels = arr.shape
    if channels == 2:
        # 灰度 + Alpha（部分 PNG）：丢掉 alpha，按灰度显示
        gray = np.ascontiguousarray(arr[:, :, 0])
        return QImage(gray.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    if channels == 4:
        return QImage(arr.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()
    return QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()

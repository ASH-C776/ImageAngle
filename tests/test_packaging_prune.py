"""打包瘦身的回归测试：裁剪规则不能裁到关键插件，也不能把「启动即崩」的模块排掉。

背景（都是实测踩过的坑）：
* PySide6 的 hook 绕过 import 图直接扫包目录收 dll，所以 ``excludes`` 管不住
  Qt6Quick.dll —— 必须靠 packaging/qt_prune.py 在 Analysis 之后再过滤；
* 排掉 ``urllib`` → pyi_rth_inspect → zipfile → pathlib 启动即崩；
* 排掉 ``numpy.linalg`` → import numpy 时 numpy.lib → matrixlib 启动即崩；
* 裁掉 ``qjpeg/qtiff/qico`` 插件 → 片子读不出来 / 窗口图标空白。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'packaging'))

from qt_prune import EXCLUDES, should_drop  # noqa: E402


# ---------- 必须保留 ----------

def test_keeps_qt_modules_in_use():
    for name in ('Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll', 'Qt6Svg.dll'):
        assert not should_drop(f'PySide6\\{name}'), name


def test_keeps_required_plugins():
    keep = [
        'PySide6\\plugins\\platforms\\qwindows.dll',
        'PySide6\\plugins\\imageformats\\qjpeg.dll',
        'PySide6\\plugins\\imageformats\\qtiff.dll',
        'PySide6\\plugins\\imageformats\\qico.dll',
        'PySide6\\plugins\\styles\\qmodernwindowsstyle.dll',
        'PySide6\\translations\\qtbase_zh_CN.qm',
    ]
    for name in keep:
        assert not should_drop(name), name


def test_keeps_python_runtime_bits():
    for name in ('python312.dll', 'PySide6\\QtGui.pyd',
                 'numpy\\_core\\_multiarray_umath.cp312-win_amd64.pyd',
                 'resources\\icon.ico'):
        assert not should_drop(name), name


# ---------- 必须裁掉 ----------

def test_drops_unused_qt_binaries():
    drop = [
        'PySide6\\opengl32sw.dll',
        'PySide6\\Qt6Quick.dll',
        'PySide6\\Qt6Qml.dll',
        'PySide6\\Qt6Pdf.dll',
        'PySide6\\Qt6Network.dll',
        'PySide6\\Qt6OpenGL.dll',
        'PySide6\\plugins\\platforms\\qdirect2d.dll',
        'PySide6\\plugins\\imageformats\\qwebp.dll',
        'PySide6\\plugins\\tls\\qopensslbackend.dll',
        'PySide6\\translations\\qtbase_de.qm',
        'libcrypto-3-x64.dll',
        'libssl-3.dll',
    ]
    for name in drop:
        assert should_drop(name), name


def test_opencv_fully_removed():
    """解码已交给 QImageReader，业务代码里不能再 import cv2。"""
    import re

    from app.io import image_loader
    src = open(image_loader.__file__, encoding='utf-8').read()
    assert not re.search(r'^\s*(?:import|from)\s+cv2', src, re.M)
    assert not hasattr(image_loader, 'cv2')

    req = open(os.path.join(ROOT, 'requirements.txt'), encoding='utf-8').read().lower()
    assert 'opencv' not in req


# ---------- 那些「排了就启动崩」的模块 ----------

def test_excludes_do_not_break_startup_chain():
    # urllib → pathlib → zipfile（pyi_rth_inspect 会用到）
    for mod in ('urllib', 'email', 'http', 'pathlib', 'zipfile'):
        assert mod not in EXCLUDES, mod
    # numpy.lib → matrixlib 在 import numpy 时就拉 linalg
    for mod in ('numpy.linalg', 'numpy.random', 'numpy.fft'):
        assert mod not in EXCLUDES, mod


def test_excludes_cover_network_and_dev_tools():
    for mod in ('PySide6.QtNetwork', 'PySide6.QtQuick', 'ssl', '_ssl', 'pytest'):
        assert mod in EXCLUDES, mod

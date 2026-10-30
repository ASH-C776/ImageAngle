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
    # numpy.lib → matrixlib 在 import numpy 时就拉 linalg，排了就启动即崩。
    # （random / fft 是 numpy 2.x 的懒加载子模块，可以排 —— 见下一个测试，
    #   这里只锁 linalg。）
    assert 'numpy.linalg' not in EXCLUDES


def test_pruned_numpy_submodules_are_really_unused():
    """排掉 numpy.random / fft / polynomial / testing 后，程序仍然跑得通。

    这几个模块耗时不小（randint 一套 pyd 约 1.1 MB），但 numpy 2.x 是懒加载，
    只有在真正访问 np.random 这类属性时才会去 import。这里在**子进程**里
    装一个 meta_path 拦截器把这几个模块封死，再走一遍真实的取像 → 转 8 位
    流程（percentile / clip / astype 都在里面），确认没有任何一处偷偷用到。
    """
    import subprocess

    code = (
        "import sys, importlib.abc\n"
        "BLOCK = {'numpy.random', 'numpy.fft', 'numpy.polynomial', 'numpy.testing'}\n"
        "class B(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name in BLOCK or any(name.startswith(b + '.') for b in BLOCK):\n"
        "            raise ImportError('blocked: ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, B())\n"
        "import numpy as np\n"
        "from app.io import image_loader as il\n"
        "img = np.linspace(0, 65535, 4096, dtype=np.uint16).reshape(64, 64)\n"
        "out = il.to_uint8(img)\n"
        "assert out.dtype == np.uint8 and out.max() == 255, out.dtype\n"
        "print('ok')\n")
    proc = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=120)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-1500:]
    assert 'ok' in proc.stdout
    for mod in ('numpy.random', 'numpy.fft'):
        assert mod in EXCLUDES, f'{mod} 应已排除（省体积）'


def test_excludes_cover_network_and_dev_tools():
    for mod in ('PySide6.QtNetwork', 'PySide6.QtQuick', 'ssl', '_ssl', 'pytest'):
        assert mod in EXCLUDES, mod

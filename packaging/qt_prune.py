"""打包时的 Qt / 二进制裁剪规则（供 ImageAngle.spec 与验证探针共用）。

为什么需要这个模块：
    PyInstaller 的 ``excludes`` 只作用于 **Python 的 import 依赖图**；而 PySide6
    官方 hook 是用 ``collect_dynamic_libs`` **直接扫包目录**收集 dll 和插件的，
    根本不看 import 图。所以哪怕 excludes 里写了 QtQuick，exe 里照样躺着
    Qt6Quick.dll（历史版本实测多出 19 MB）。

    正确做法是 Analysis 跑完之后，对 ``a.binaries`` / ``a.datas`` 再过滤一遍 ——
    就是这里的 :func:`prune`。
"""
from __future__ import annotations

import os
import re

#: Python 侧要排除的模块
EXCLUDES = [
    # ---- Qt 模块（程序只用到 Core/Gui/Widgets/Svg）----
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
    'PySide6.QtWebChannel', 'PySide6.QtWebSockets', 'PySide6.QtNetwork',
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQuick3D',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs',
    'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras',
    'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtPrintSupport',
    'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtDesigner',
    'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtPositioning',
    'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtSerialBus',
    'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtStateMachine',
    'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
    # ---- OpenSSL 链（已排除 QtNetwork，程序不联网）----
    # 只能排 ssl/_ssl/_hashlib。urllib、email 千万别排：pathlib 依赖 urllib.parse，
    # 而 PyInstaller 的 pyi_rth_inspect → zipfile 依赖 pathlib，一排除就是启动即崩
    # （实测报 ModuleNotFoundError: No module named 'urllib'）。
    'ssl', '_ssl', 'hashlib', '_hashlib',
    # ---- 开发期依赖 ----
    'tkinter', 'unittest', 'pydoc', 'doctest', 'pytest', '_pytest',
    # ---- numpy 构建期工具 ----
    # 别顺手排 numpy.linalg：import numpy 时 numpy.lib → matrixlib 就会拉 linalg，
    # 排掉是启动即崩（实测报 No module named 'numpy.linalg'）。
    'numpy.f2py', 'numpy.distutils',
    # 这几个是 numpy 2.x 的懒加载子模块，本程序一个都没用到（只用
    # frombuffer / percentile / clip / astype 这类基础运算）。
    # 删掉前用「屏蔽 import + 跑全量测试」验证过，确认无依赖。
    'numpy.random', 'numpy.fft', 'numpy.polynomial', 'numpy.testing',
]

#: 用不到的 Qt6*.dll（QtSvg 要留：窗口内的 SVG 图标靠它渲染）
_DROP_QT_DLL = re.compile(
    r'Qt6(?:'
    r'Quick|QuickControls2\w*|QuickTemplates2|QuickDialogs2\w*|QuickWidgets|QuickParticles|'
    r'Qml|QmlModels|QmlMeta|QmlWorkerScript|QmlCompiler|QmlLocalStorage|'
    r'Pdf|OpenGL|OpenGLWidgets|Network|VirtualKeyboard|ShaderTools|'
    r'Designer|DesignerComponents|UiTools|Help|PrintSupport|'
    r'Labs\w*|3D\w*|Charts|DataVisualization|Graphs|Multimedia\w*|'
    r'WebEngine\w*|WebChannel|WebSockets|SerialPort|Sql|Test'
    r')\.dll$',
    re.IGNORECASE,
)

#: imageformats 白名单：jpeg 是主格式、tiff 是全景机导出格式、ico 是窗口图标
_KEEP_IMAGE_PLUGINS = {'qjpeg', 'qtiff', 'qico'}
#: platforms 白名单：qdirect2d / qoffscreen / qminimal 都是调试或多屏后端
_KEEP_PLATFORM_PLUGINS = {'qwindows'}
#: 翻译白名单：程序没有装 QTranslator，只留中文包给 QMessageBox 标准按钮兜底
_KEEP_TRANSLATIONS = {'qtbase_zh_CN.qm', 'qt_zh_CN.qm'}

_DROP_OPENSSL = re.compile(r'(?:libssl|libcrypto)[\w.-]*\.dll$', re.IGNORECASE)


def should_drop(name: str) -> bool:
    """判断归档里的某个条目要不要丢掉（name 可能是正斜杠或反斜杠）。"""
    n = name.replace('/', '\\')

    if _DROP_OPENSSL.search(n):
        return True

    m = re.match(r'^PySide6\\(.*)$', n)
    if not m:
        return False
    inner = m.group(1)

    # 软件 OpenGL 回退（7 MB）：纯 Widgets 程序不做 3D
    if inner.lower() == 'opengl32sw.dll':
        return True
    if _DROP_QT_DLL.search(inner):
        return True

    if inner.startswith('translations\\'):
        return os.path.basename(inner) not in _KEEP_TRANSLATIONS

    if inner.startswith('plugins\\'):
        parts = inner.split('\\')
        if len(parts) < 3:
            return True
        kind = parts[1]
        leaf = os.path.splitext(parts[-1])[0]
        if kind == 'platforms':
            return leaf not in _KEEP_PLATFORM_PLUGINS
        if kind == 'imageformats':
            return leaf not in _KEEP_IMAGE_PLUGINS
        if kind in ('tls', 'networkinformation', 'platforminputcontexts',
                    'generic', 'iconengines', 'egldeviceintegrations'):
            return True
        return False

    return False


def prune(analysis):
    """就地裁剪 Analysis 的 binaries/datas，并打印裁剪前后条目数。"""
    binaries = [b for b in analysis.binaries if not should_drop(b[0])]
    datas = [d for d in analysis.datas if not should_drop(d[0])]
    print(f'[qt_prune] 二进制瘦身: {len(analysis.binaries)} → {len(binaries)} 项，'
          f'资源 {len(analysis.datas)} → {len(datas)} 项')
    analysis.binaries = binaries
    analysis.datas = datas
    return analysis

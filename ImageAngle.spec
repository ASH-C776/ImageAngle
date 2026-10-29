# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（单文件 GUI 程序）。

用法：
    py -m PyInstaller ImageAngle.spec --noconfirm

为什么用 spec 而不是命令行：图标、版本信息、Qt 瘦身三项都要写死在配置里，
否则下次谁重新打包都会漏掉某一项（典型后果是 exe 变成白板图标、文件属性里
没有版本号，或者体积从 34 MB 涨回 100 MB）。

Qt 瘦身的规则在 ``packaging/qt_prune.py``，那里有详细说明（一句话：PySide6 的
hook 绕过 import 图直接扫包目录收 dll，所以 excludes 管不住它，必须在 Analysis
之后对 binaries/datas 再过滤一遍）。
"""
import os
import sys

root = os.path.abspath(SPECPATH)          # noqa: F821  (PyInstaller 注入)

# 直接 import 模块文件，而不是 import packaging —— 后者会撞上 PyPI 的 packaging 包
sys.path.insert(0, os.path.join(root, 'packaging'))
from qt_prune import EXCLUDES, prune       # noqa: E402

sys.path.insert(0, root)
from app import __version__                # noqa: E402  版本单一来源


a = Analysis(                               # noqa: F821
    [os.path.join(root, 'run.py')],
    pathex=[root],
    binaries=[],
    # 图标要同时打两份：
    #   - EXE(icon=...) 那份写进 exe 资源，资源管理器/桌面快捷方式用它；
    #   - datas 这份解压到 _MEIPASS/resources，运行时 QIcon 加载它设窗口图标。
    # 少了 datas 里的这份，任务栏和 Alt+Tab 就没有图标（窗口没有 WM_SETICON）。
    datas=[
        (os.path.join(root, 'resources', 'icon.ico'), 'resources'),
        (os.path.join(root, 'resources', 'icon.png'), 'resources'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

prune(a)

pyz = PYZ(a.pure)                           # noqa: F821

exe = EXE(                                  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f'ImageAngle-{__version__}-便携包',   # 产物名固定带版本，避免 dist 里一堆同名文件分不清
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # 归档内部已 zlib 压缩，UPX 只能压外壳（实测 <1%），还会拉高杀软误报
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # GUI 程序：不要黑色控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(root, 'resources', 'icon.ico'),
    version=os.path.join(root, 'packaging', 'version_info.txt'),
)

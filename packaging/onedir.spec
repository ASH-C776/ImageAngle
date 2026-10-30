# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（目录版 / onedir）。

这是「安装包」的原料：产出一个可运行的目录，再交给 Inno Setup 压成 setup.exe。
和单文件版（``ImageAngle.spec``）走完全相同的 Analysis 与裁剪规则，区别只在
最后一步 —— 单文件版把 binaries/datas 塞进 EXE 归档（每次启动解压 81 MB），
目录版用 COLLECT 摊在磁盘上（启动不解压，实测 570 ms vs 1400 ms）。

通常不直接调用本文件，用 ``py scripts/build.py`` 一条命令出两个包。
"""
import os
import sys

root = os.path.dirname(os.path.abspath(SPECPATH))      # noqa: F821  (PyInstaller 注入)
sys.path.insert(0, root)
sys.path.insert(0, os.path.join(root, 'packaging'))

from app import __version__                            # noqa: E402
from qt_prune import EXCLUDES, prune                   # noqa: E402

a = Analysis(                                           # noqa: F821
    [os.path.join(root, 'run.py')],
    pathex=[root],
    binaries=[],
    datas=[
        (os.path.join(root, 'resources', 'icon.ico'), 'resources'),
        (os.path.join(root, 'resources', 'icon.png'), 'resources'),
        # 关于页打赏区：微信 / 支付宝收款码（已裁掉姓名文字的正方形 PNG）
        (os.path.join(root, 'resources', 'donate_wechat.png'), 'resources'),
        (os.path.join(root, 'resources', 'donate_alipay.png'), 'resources'),
        # 关于页「减弱动效」复选框的对勾图标
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,      # 同单文件版：丢 docstring / assert，见 ImageAngle.spec 的注释
)

prune(a)

pyz = PYZ(a.pure)                                       # noqa: F821

exe = EXE(                                              # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # 关键：dll 不塞进 exe，交给 COLLECT 摊到目录里
    name='ImageAngle',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(root, 'resources', 'icon.ico'),
    version=os.path.join(root, 'packaging', 'version_info.txt'),
)

coll = COLLECT(                                         # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=f'ImageAngle-{__version__}',   # 目录名带版本，安装包里的内容一目了然
)

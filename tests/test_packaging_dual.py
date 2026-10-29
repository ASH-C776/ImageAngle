"""双产物打包配置的守门测试。

这里测的不是"能不能打包"（那要 2 分钟，不该进单测），而是**配置有没有被改坏**：
两个 spec 是否共用同一套裁剪规则、产物名是否还带版本号、安装脚本的关键项是否还在。
历史上踩过的坑是「有人只改了一个 spec」，于是安装包体积悄悄翻三倍。
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


def version() -> str:
    m = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", read('app', '__init__.py'), re.M)
    assert m, 'app/__init__.py 里找不到 __version__'
    return m.group(1)


def test_two_specs_share_prune_rules():
    """两个 spec 必须都走 qt_prune，否则装的那一份会重新胖回去。"""
    for spec in ('ImageAngle.spec', os.path.join('packaging', 'onedir.spec')):
        src = read(spec)
        assert 'from qt_prune import EXCLUDES, prune' in src, f'{spec} 没用共享裁剪规则'
        assert 'excludes=EXCLUDES' in src, f'{spec} 的 Analysis 没传 EXCLUDES'
        assert re.search(r'^prune\(a\)$', src, re.M), f'{spec} 没调用 prune(a)'


def test_artifact_names_carry_version():
    """产物名 = 名字 + 版本 + 便携包/安装包，版本只从 __version__ 取。"""
    ver = version()
    portable = read('ImageAngle.spec')
    assert 'from app import __version__' in portable
    assert "-便携包" in portable

    onedir = read('packaging', 'onedir.spec')
    assert 'from app import __version__' in onedir

    iss = read('installer', 'ImageAngle.iss')
    assert 'OutputBaseFilename=ImageAngle-{#AppVer}-安装包' in iss
    assert 'AppVersion={#AppVer}' in iss
    assert ver  # 版本号本身非空即可，具体值不钉死


def test_build_script_reads_version_without_importing_qt():
    """build.py 读版本靠正则，不能 import app —— 那会在打包机上拉起 Qt。"""
    src = read('scripts', 'build.py')
    assert 're.search' in src
    assert 'from app import' not in src
    assert 'import app' not in src


def test_installer_key_decisions():
    """安装脚本里几个关键决定，改之前想清楚后果。"""
    iss = read('installer', 'ImageAngle.iss')
    # 免管理员：诊所电脑常常没有管理员权限
    assert 'PrivilegesRequired=lowest' in iss
    # 数据在 %APPDATA%，卸载不能删
    assert 'UninstallDelete' not in iss
    # 图标：安装程序本身 + 控制面板卸载项
    assert 'SetupIconFile=' in iss
    assert 'UninstallDisplayIcon={app}\\{#AppExe}' in iss
    # 中文界面
    assert 'ChineseSimplified.isl' in iss
    # 覆盖安装沿用旧目录，避免装成两份
    assert 'UsePreviousAppDir=yes' in iss


def test_chinese_language_file_present():
    """语言包随仓库走：Inno Setup 官方安装里没有中文，不能指望打包机上有。"""
    p = os.path.join(ROOT, 'installer', 'ChineseSimplified.isl')
    assert os.path.exists(p), '缺中文语言包，安装向导会变英文'
    text = open(p, encoding='utf-8-sig').read()
    assert 'LanguageName' in text
    assert len(text) > 10000, '语言包像是被截断了（正常约 1.4 万字符）'

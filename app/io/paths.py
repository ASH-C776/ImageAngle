"""用户数据文件位置（会话 / 窗口偏好 / 主题偏好）。

为什么不再写在程序目录：打包成 exe 安装到 `C:/Program Files/...` 后，程序目录
对普通用户是**只读**的，`open(path, 'w')` 会抛 PermissionError —— 而这些写入
处处都套着 `except Exception: pass`，表现就是「主题/测量数据静默不保存」，
而且完全没有任何提示，排查起来极其费时。

现在的规则：
- 默认写到 `%APPDATA%\\ImageAngle`（Windows）；非 Windows 用
  `~/.local/share/ImageAngle`（遵循 XDG）。
- 环境变量 `IMAGEANGLE_DATA_DIR` 可覆盖（测试与便携版用）。
- 首次启动时，把程序目录下的旧文件**复制**到新位置（不删原文件），
  老用户升级后测量数据不会凭空消失。
"""
from __future__ import annotations

import os
import shutil
import sys

APP_DIR_NAME = 'ImageAngle'
_ENV_OVERRIDE = 'IMAGEANGLE_DATA_DIR'


def _legacy_dir() -> str:
    """旧位置（程序目录）。

    开发时是仓库根目录；打包后 `__file__` 落在 PyInstaller 的临时解压目录
    （`_MEIPASS`），拿它当旧位置等于永远找不到旧文件 —— 必须用 exe 所在目录，
    这样「绿色版 exe 旁边带着 session.json」也能被迁移进来。
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_LEGACY_DIR = _legacy_dir()

_LEGACY_FILES = ('session.json', 'window_pref.json', 'theme_pref.json')


def data_dir() -> str:
    """用户数据目录（不存在则创建）。"""
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        path = override
    elif os.name == 'nt':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
        path = os.path.join(base, APP_DIR_NAME)
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.join(
            os.path.expanduser('~'), '.local', 'share')
        path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def data_path(name: str) -> str:
    return os.path.join(data_dir(), name)


def session_path() -> str:
    return data_path('session.json')


def window_pref_path() -> str:
    return data_path('window_pref.json')


def theme_pref_path() -> str:
    return data_path('theme_pref.json')


def migrate_legacy() -> list:
    """把程序目录下的旧数据文件搬到用户数据目录（只复制，不删）。

    返回实际迁移的文件名列表；已存在同名新文件时不覆盖。
    """
    moved = []
    target_dir = data_dir()
    if os.path.abspath(target_dir) == os.path.abspath(_LEGACY_DIR):
        return moved
    for name in _LEGACY_FILES:
        src = os.path.join(_LEGACY_DIR, name)
        dst = os.path.join(target_dir, name)
        if not os.path.isfile(src) or os.path.exists(dst):
            continue
        try:
            shutil.copy2(src, dst)
            moved.append(name)
        except OSError:
            pass
    return moved

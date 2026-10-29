"""资源文件定位 + Windows 任务栏应用身份。

打包成 exe 后这里有两个坑，都只在「双击 exe」时才暴露：

1. **没用 `setWindowIcon()`，任务栏就没有图标。**
   资源管理器显示的那个图标读的是 EXE 文件里的图标资源（PyInstaller 的
   `icon=` 参数写进去的），而任务栏按钮显示的图标来自窗口的 WM_SETICON。
   两条完全独立的路：exe 有图标不代表窗口有图标，不设就只剩一个空白方块。

2. **不自报 AppUserModelID，任务栏会把程序当成「别人的子进程」。**
   Windows 按 AppUserModelID 给任务栏按钮分组与取图标。进程没显式设置时，
   onefile 的引导程序从临时目录启动，任务栏拿不到稳定身份，图标也就退回默认。

对应到使用上：①在 `main()` 里 `app.setWindowIcon(...)`；②在任何窗口创建之前
调用 `set_taskbar_identity()`。两者都做了，任务栏、Alt+Tab、窗口左上角才会
一致地显示应用图标。
"""
from __future__ import annotations

import os
import sys

# 固定不变的身份串：改了它，用户已经固定在任务栏上的旧图标会变成另一条记录
APP_USER_MODEL_ID = 'ImageAngle.PanoramaGoniometer.1'


def resource_dir() -> str:
    """资源目录。打包后是 PyInstaller 的临时解压目录（_MEIPASS）。"""
    bundled = getattr(sys, '_MEIPASS', None)
    if bundled:
        return os.path.join(bundled, 'resources')
    # 开发态：app/io/resources.py → 上三级是仓库根
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'resources')


def icon_path() -> str:
    """应用图标路径；找不到时返回空串。

    优先 .ico：里面含 16/24/32/48/64/128/256 多尺寸，任务栏小图标和
    Alt+Tab 大图标各自取到最清晰的那一档，不会被缩放糊掉。
    """
    for name in ('icon.ico', 'icon.png'):
        p = os.path.join(resource_dir(), name)
        if os.path.isfile(p):
            return p
    return ''


def set_taskbar_identity(app_id: str = APP_USER_MODEL_ID) -> bool:
    """告诉 Windows「我是谁」，用于任务栏分组与图标归属。非 Windows 直接跳过。"""
    if not sys.platform.startswith('win'):
        return False
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        return True
    except Exception:      # 老系统 / 被安全软件拦截：不该因此启动失败
        return False


def apply_window_icon(app) -> bool:
    """给 QApplication 设默认窗口图标，后续创建的窗口自动继承。"""
    from PySide6.QtGui import QIcon

    icon = QIcon()
    path = icon_path()
    if path:
        icon = QIcon(path)
    if icon.isNull() and getattr(sys, 'frozen', False):
        # 资源文件万一没打进去，还能从 exe 自身的图标资源里抠出来
        icon = QIcon(sys.executable)
    if icon.isNull():
        return False
    app.setWindowIcon(icon)
    return True

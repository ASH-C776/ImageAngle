"""ImageAngle 入口。"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui import theme
from .io import paths, resources
from . import applog
from . import __version__

# 高 DPI 适配：Qt6 起高 DPI 缩放与像素图缩放默认开启，AA_UseHighDpiPixmaps /
# AA_EnableHighDpiScaling 已废弃（设置只会产生 DeprecationWarning），故不再设置；
# 这里只对 Windows 的分数缩放（125% / 150%）采用 PassThrough 取整策略，
# 让 1.5 倍屏不被向上取整成 2 倍，图标与线条更贴合真实像素。
def _setup_high_dpi() -> None:
    policy = getattr(Qt, 'HighDpiScaleFactorRoundingPolicy', None)
    if policy is None:
        return
    app_cls = getattr(QApplication, 'setHighDpiScaleFactorRoundingPolicy', None)
    if app_cls is not None:
        app_cls(policy.PassThrough)


def main() -> int:
    # 日志要最先起来：后面每一步（迁移、建窗口、读图片）出错才有记录可查。
    # 打包成 exe 后没有控制台，没有这行就等于所有异常都消失在空气里。
    applog.setup_logging()
    applog.install_excepthook()

    _setup_high_dpi()

    # 必须在建任何窗口之前自报身份：Windows 靠它给任务栏按钮分组、取图标。
    # 不设的话 onefile 从临时目录启动，任务栏图标会退回到默认空白。
    has_aumid = resources.set_taskbar_identity()

    app = QApplication(sys.argv)
    app.setApplicationName('ImageAngle')
    app.setApplicationDisplayName('ImageAngle 图片量角器')
    app.setApplicationVersion(__version__)
    # 窗口图标（任务栏、Alt+Tab、标题栏左上都用它）。
    # 注意这与 exe 文件自己的图标是两回事，必须单独设。
    has_icon = resources.apply_window_icon(app)
    # 「任务栏图标不对」这类问题在别人机器上没法远程看，落一行日志好排查：
    # 两个 False 基本就等于图标文件没打进包 / 系统拒绝设置 AUMID。
    applog.get_logger().info(
        '窗口图标 %s（%s）| 任务栏身份 %s（%s）',
        '已设置' if has_icon else '**失败**',
        resources.icon_path() or '回退 exe 内置资源',
        '已设置' if has_aumid else '跳过',
        resources.APP_USER_MODEL_ID)
    # 老版本把 session.json / theme_pref.json 写在程序目录里：升级到「用户数据目录」
    # 后先把旧文件复制过来，否则老用户会觉得测量数据凭空消失了。
    paths.migrate_legacy()
    app.setStyleSheet(theme.build_qss())
    win = MainWindow()
    win.show()
    # show 后窗口尺寸才确定，按真实宽度重算工具栏混合布局（避免初始默认尺寸误判溢出）
    win._update_responsive(win.width(), force=True)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())

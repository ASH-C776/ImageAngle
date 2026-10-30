"""主窗口：工具栏 + 画布 + 结果栏（P1 单图核心）。

P1 可用：打开图片（含拖入）、画参考线 / 重画参考线、画牙长轴、
无参考线空白结果、画参考线后自动补算、牙位补填重算。
P2+：撤销 / 删除 / 上一张 / 下一张 / 导出 CSV（按钮保留，后续阶段启用）。
"""
from __future__ import annotations

import os
import json
import ctypes
from ctypes.wintypes import DWORD, HWND, LPARAM, WPARAM

# 无边框窗口四边拖拽缩放：Windows 上拦截 WM_NCHITTEST 返回对应边/角命中，
# 使无边框窗口的左右/底部边缘可拖拽调整大小；顶部区域保留给自定义标题栏
# （移动 / 窗口按钮），不在此处理，避免误伤标题栏内容。
_WM_NCHITTEST = 0x0084
_HTLEFT, _HTRIGHT, _HTBOTTOM = 10, 11, 15


def hit_test_edges(mx: float, my: float,
                   win_x: float, win_y: float,
                   win_w: float, win_h: float,
                   edge: float) -> int:
    """无边框窗口的边缘命中判定（**全部参数必须是物理像素**）。

    参数
    ----
    mx, my           : 鼠标屏幕坐标（物理像素，即 WM_NCHITTEST 的 lParam）
    win_x, win_y     : 窗口左上角屏幕坐标（物理像素）
    win_w, win_h     : 窗口宽高（物理像素）
    edge             : 边缘抓手宽度（物理像素）

    返回
    ----
    -1 : 落在顶部条，交给标题栏处理（移动 / 窗口按钮）
     0 : 客户区（正常处理为 HTCLIENT）
    正数: HTLEFT / HTRIGHT / HTBOTTOM 的按位或

    注意：调用方负责把 Qt 的**逻辑像素** frameGeometry 乘以 devicePixelRatio
    转成物理像素。历史上这里混用过逻辑与物理坐标，在 225% 缩放下会把整个
    客户区误判成右边缘，导致标题栏按钮点不动、画布也画不了线。
    """
    lx = mx - win_x
    ly = my - win_y
    if ly <= edge:
        return -1
    res = 0
    if lx <= edge:
        res |= _HTLEFT
    elif lx >= win_w - edge:
        res |= _HTRIGHT
    if ly >= win_h - edge:
        res |= _HTBOTTOM
    return res


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", HWND), ("message", DWORD),
        ("wParam", WPARAM), ("lParam", LPARAM),
        ("time", DWORD), ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long), ("lPrivate", DWORD),
    ]


from PySide6.QtCore import QEvent, QPoint, Qt, QSize, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizeGrip,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..io.image_loader import convert_for_qt, image_size, load_image
from ..io.csv_exporter import export_session_csv
from ..io import paths
from ..model.protocol import is_valid_fdi
from ..model.session import ImageData, Session
from .. import applog
from . import theme
from .about import show_help
from .canvas import Canvas
from .icons import get_icon
from .result_panel import ResultPanel
from .title_bar import TitleBar
from .win_round import set_round_corners

# 会话 / 窗口偏好 / 主题偏好都写在**用户数据目录**（%APPDATA%\ImageAngle），
# 不再写程序目录 —— 装到 Program Files 后那里是只读的，写入会静默失败。
# 首次启动由 paths.migrate_legacy() 把旧文件复制过来。
_SESSION_PATH = paths.session_path()
_WIN_PREF_PATH = paths.window_pref_path()
_IMAGE_FILTER = '图片文件 (*.jpg *.jpeg *.png *.tif *.tiff *.bmp)'

_log = applog.get_logger('ui.main_window')


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        # 无边框 + 自定义标题栏（暗色一体化）；保留系统边框缩放需改用 CustomizeWindowHint，
        # 这里用 FramelessWindowHint 以获得完全可控的暗色外观，右下角放 QSizeGrip 维持可缩放。
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle('ImageAngle 图片量角器')
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)
        # 面板折叠 / 响应式状态（抽屉）——必须在 _restore_window_pref 之前初始化，
        # 否则读到偏好里的面板开关会被这里的默认值覆盖掉。
        self._panel_user_override = None  # None=跟随自适应；True/False=用户强制
        self._panel_auto_collapsed = False
        self._panel_hidden = False
        # 恢复上次窗口位置 / 大小 / 面板开关（首次运行则用上面的默认值）
        self._pending_maximize = False
        self._pending_open = ''
        self._restore_window_pref()
        # 工具栏布局复算（事件循环后跑一次；用 QTimer 子对象，窗口销毁即失效，
        # 避免 singleShot 在窗口已析构后再回调）
        self._resp_recheck_pending = False
        self._resp_timer = QTimer(self)
        self._resp_timer.setSingleShot(True)
        self._resp_timer.setInterval(0)
        self._resp_timer.timeout.connect(self._recheck_responsive)
        # 应用持久化主题偏好（默认暗色）
        theme.set_theme(self._load_theme_pref())
        self.session = Session()
        self._load_session()
        self._current_path: str | None = None
        self._last_dir: str = self.session.last_dir
        self._folder_images: list[str] = []
        self._folder_index: int = -1
        # 状态栏「打开图片」这条消息的组成部分。翻页信息（第 x / n 张）以前会
        # 直接把「已打开 … 点击参考线」顶掉，导致刚打开就看不到下一步提示；
        # 现在两段拼成一句话显示。
        self._open_name = ''
        self._open_size = ''
        self._open_note = ''
        # 选中项变化后，等列表重建完再滚到对应行（信号早于行部件创建）
        self._scroll_to_seq: int | None = None
        # 测量数据自动保存：改一次线就延后写盘，避免逐帧写文件；关窗口时也会再存一次
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(700)
        self._save_timer.timeout.connect(self._save_session)

        # 标题栏作为菜单栏位（位于最顶），工具栏用 addToolBar 接管其后，
        # 二者形成「一体化」暗色条；下方为工作区；窗口自带状态栏在底部。
        self._title_bar = TitleBar()
        self._title_bar.on_theme_toggle = self._toggle_theme
        self.setMenuWidget(self._title_bar)

        self.canvas = Canvas()
        self.panel = ResultPanel()
        content = QWidget()
        self._content_lay = hbox = QHBoxLayout(content)
        hbox.setContentsMargins(16, 16, 16, 16)
        hbox.setSpacing(16)
        hbox.addWidget(self.canvas, 1)
        hbox.addWidget(self.panel)
        self.setCentralWidget(content)

        self._toolbar = self._build_toolbar()
        self._connect()
        self.statusBar().showMessage('未打开图片')

        # 右下角缩放手柄（无边框窗口下仍可调整大小）
        grip = QSizeGrip(self.statusBar())
        self.statusBar().addPermanentWidget(grip)

        # 初始应用主题（刷新图标 / 各组件样式）与响应式布局
        self._apply_theme()
        self._update_responsive(self.width(), force=True)
        # 记住上次打开图片所在的文件夹（「打开」对话框从这里起步）。
        # 注意：**不自动打开上次那张图** —— 启动就是一张干净的白板，
        # 要看上次的片子自己打开，历史测量仍然在会话里等着。
        self._restore_last_dir()

    # ---------- 会话 ----------

    def _load_session(self) -> None:
        if os.path.exists(_SESSION_PATH):
            try:
                self.session = Session.load(_SESSION_PATH)
            except Exception:
                # 文件损坏（手工改坏 / 写到一半断电）：按空会话启动，但要留痕，
                # 否则「上次的测量全没了」永远查不出原因
                _log.warning('会话文件读取失败：%s', _SESSION_PATH, exc_info=True)
                self.session = Session()

    # ---------- 窗口偏好（尺寸 / 位置 / 面板开关）----------

    def _restore_window_pref(self) -> None:
        """恢复上次的窗口几何与面板开关；越界/损坏一律忽略，回落到默认值。"""
        try:
            with open(_WIN_PREF_PATH, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return            # 首次运行，没有偏好文件是正常情况
        except Exception:
            _log.warning('窗口偏好读取失败，使用默认布局', exc_info=True)
            return
        if not isinstance(data, dict):
            return
        g = data.get('geometry')
        if isinstance(g, (list, tuple)) and len(g) == 4:
            try:
                x, y, w, h = (int(v) for v in g)
            except (TypeError, ValueError):
                x = y = w = h = 0
            if (w >= self.minimumWidth() and h >= self.minimumHeight()
                    and self._is_geometry_on_screen(x, y, w, h)):
                self.setGeometry(x, y, w, h)
        ov = data.get('panel_override')
        if isinstance(ov, bool):
            self._panel_user_override = ov
        self._pending_maximize = bool(data.get('maximized', False))
        self._pending_open = data.get('last_path') or ''

    @staticmethod
    def _is_geometry_on_screen(x: int, y: int, w: int, h: int) -> bool:
        """窗口至少要有一块可见区域落在某块屏幕上。

        显示器拔掉 / 分辨率变小 / 多屏改单屏后，上次记的坐标可能完全在屏幕外，
        直接照搬会出现「软件启动了但看不见窗口」。
        """
        try:
            from PySide6.QtGui import QGuiApplication
            screens = QGuiApplication.screens()
        except Exception:
            return False
        for s in screens:
            a = s.availableGeometry()
            ix = min(x + w, a.x() + a.width()) - max(x, a.x())
            iy = min(y + h, a.y() + a.height()) - max(y, a.y())
            if ix >= 120 and iy >= 80:   # 至少露出一条能抓住的边缘
                return True
        return False

    def _save_window_pref(self) -> None:
        try:
            if self.isMaximized() or self.isFullScreen():
                g = self.normalGeometry()
                data = {'maximized': self.isMaximized()}
            else:
                g = self.geometry()
                data = {'maximized': False}
            data['geometry'] = [g.x(), g.y(), g.width(), g.height()]
            ov = self._panel_user_override
            data['panel_override'] = ov if isinstance(ov, bool) else None
            data['last_path'] = self._current_path or ''
            with open(_WIN_PREF_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            # 窗口位置存不住不影响使用，但一定要能在日志里查到（比如目录不可写）
            _log.warning('窗口偏好保存失败：%s', _WIN_PREF_PATH, exc_info=True)

    def _restore_last_dir(self) -> None:
        """只取「上次打开图片的目录」，不自动打开图片。

        以前这里会把上次那张图连同测量一起重新打开，用户一启动就看到别人的
        片子，还以为是软件记住错了。现在启动恒为空，路径只用于让「打开」
        对话框落在上次的文件夹。
        """
        path = getattr(self, '_pending_open', '')
        self._pending_open = ''
        if path:
            d = os.path.dirname(path)
            if os.path.isdir(d):
                self._last_dir = d

    def _save_session(self) -> None:
        try:
            self.session.last_dir = self._last_dir
            # 只留「有内容」的图：每打开一张都会登记，但空白条目没必要写进文件，
            # 否则 session.json 里会堆一堆只有路径、没有任何线的图。
            for key in [k for k, v in self.session.images.items()
                        if not v.teeth and not v.reference]:
                del self.session.images[key]
            self.session.save(_SESSION_PATH)
        except Exception as exc:
            _log.warning('会话保存失败：%s', _SESSION_PATH, exc_info=True)
            self.statusBar().showMessage(f'会话保存失败: {exc}')

    def _schedule_save(self) -> None:
        """改动后延后写盘（防抖）。真正落盘发生在 _save_session。"""
        self._register_current()
        if self._save_timer is not None:
            self._save_timer.start()

    def _register_current(self) -> None:
        """把画布上正在编辑的数据登记进会话，这样保存时才写得到它。"""
        if self._current_path and self.canvas.image_data is not None:
            self.session.images[self._current_path] = self.canvas.image_data

    def closeEvent(self, e) -> None:
        # 先停掉防抖定时器：窗口关了还让它在稍后写盘，会把「关窗口那一刻之后
        # 才被别的窗口改过」的路径写成当前会话（测试里最容易踩）。
        if getattr(self, '_save_timer', None) is not None:
            self._save_timer.stop()
        self._register_current()
        self._save_session()
        self._save_window_pref()
        super().closeEvent(e)

    # ---------- 原生圆角（Windows 11 DWM）----------

    def _sync_window_rounding(self) -> None:
        """普通窗口用系统标准圆角；最大化 / 全屏时取消，避免屏幕边缘留缺口。

        走 DWM 而不是 setMask：无边框窗口自己裁圆角是硬锯齿，DWM 是合成器抗锯齿。
        Win10 及更早版本 DWM 不支持，调用会返回 False，窗口保持直角（静默降级）。
        """
        rounded = not (self.isMaximized() or self.isFullScreen())
        set_round_corners(self, enabled=rounded, border_color=theme.C_BORDER)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        # 原生句柄要等 show 之后才存在，圆角只能在这里（或之后）设置
        self._sync_window_rounding()
        # 上次是以最大化状态关掉的：等真正 show 出来再最大化，否则 showMaximized
        # 在 hide 状态下调用会被随后的 show() 覆盖回普通尺寸。
        if getattr(self, '_pending_maximize', False):
            self._pending_maximize = False
            self.showMaximized()

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if e.type() == QEvent.Type.WindowStateChange:
            self._sync_window_rounding()

    # ---------- 无边框四边拖拽缩放 ----------
    _EDGE = 7  # 边缘命中宽度(px)

    def nativeEvent(self, eventType, message):
        if eventType == b'windows_generic_MSG':
            try:
                msg = _MSG.from_address(int(message))
                if msg.message == _WM_NCHITTEST:
                    # ⚠ WM_NCHITTEST 的 lParam 是【物理像素】屏幕坐标，而
                    # frameGeometry() 给的是【逻辑像素】，必须乘 dpr 才能同尺度比较。
                    dpr = self.devicePixelRatio() or 1.0
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    fg = self.frameGeometry()
                    res = hit_test_edges(
                        x, y,
                        fg.x() * dpr, fg.y() * dpr,
                        fg.width() * dpr, fg.height() * dpr,
                        max(6.0, self._EDGE * dpr),
                    )
                    if res == -1:
                        return False, 0   # 顶部交给标题栏
                    if res:
                        return True, res
            except Exception:
                # 边缘命中判定失败不该影响窗口其他功能，但要能在日志里看到
                _log.debug('WM_NCHITTEST 处理异常', exc_info=True)
        return super().nativeEvent(eventType, message)
        return super().nativeEvent(eventType, message)

    # ---------- 工具栏 ----------

    def _build_toolbar(self) -> QToolBar:
        tb = QToolBar('工具栏')
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.setIconSize(QSize(18, 18))
        self.addToolBar(tb)

        # 结果面板显隐（抽屉开关），窄屏下自适应折叠，按钮始终可用
        self.act_panel = QAction('面板', self)
        self.act_panel.setIcon(get_icon('panel'))
        self.act_panel.setCheckable(True)
        self.act_panel.setChecked(True)
        self.act_panel.setToolTip('显示 / 隐藏右侧结果面板')
        self.act_panel.toggled.connect(self._toggle_panel)

        self.act_fit = QAction('适应窗口', self)
        self.act_fit.setShortcut(QKeySequence('Ctrl+0'))
        self.act_fit.setToolTip('适应窗口：放大 / 拖动后回到打开时的整图大小（Ctrl+0）')
        self.act_open = QAction('打开', self)
        self.act_open.setToolTip('打开图片…')
        self.act_folder = QAction('文件夹', self)
        self.act_folder.setToolTip('打开图片文件夹…')
        self.act_ref = QAction('参考线', self)
        self.act_ref.setShortcut(QKeySequence('R'))
        self.act_ref.setCheckable(True)
        self.act_ref.setToolTip('画参考线（R）')
        self.act_tooth = QAction('牙轴', self)
        self.act_tooth.setShortcut(QKeySequence('T'))
        self.act_tooth.setCheckable(True)
        self.act_tooth.setToolTip('画牙长轴（T）')
        self.act_undo = QAction('撤销', self)
        self.act_undo.setShortcut(QKeySequence('Ctrl+Z'))
        self.act_undo.setToolTip('撤销（Ctrl+Z）')
        self.act_del = QAction('删除', self)
        self.act_del.setShortcut(QKeySequence('Del'))
        self.act_del.setToolTip('删除选中记录（Del）')
        self.act_clear = QAction('清空', self)
        # 不用 Ctrl+Shift+Z：那是各家的「重做」，误按会把整张图清掉（虽然能撤销，
        # 但第一反应是「数据没了」）。改用 Ctrl+Shift+Del，并按 Del 家族的习惯加确认。
        self.act_clear.setShortcut(QKeySequence('Ctrl+Shift+Del'))
        self.act_clear.setToolTip('清空所有线（Ctrl+Shift+Del，需确认）')
        self.act_prev = QAction('上一张', self)
        self.act_prev.setToolTip('上一张')
        self.act_next = QAction('下一张', self)
        self.act_next.setToolTip('下一张')
        self.act_list = QAction('列表', self)
        self.act_list.setShortcut(QKeySequence('L'))
        self.act_list.setToolTip('图片列表（L）')
        self.act_export = QAction('导出CSV', self)
        self.act_export.setToolTip('导出 CSV…')
        # 使用说明放在工具栏最右端（F1）：操作要点、算法、打赏、仓库都在里面
        # （属性名保留 act_about，权限列表/优先级表里引用它，改名只会增加噪音）
        self.act_about = QAction('使用说明', self)
        self.act_about.setShortcut(QKeySequence('F1'))
        self.act_about.setToolTip('使用说明（F1）')

        # 统一配图标（DPI 感知、暗色可读）
        self.act_open.setIcon(get_icon('open'))
        self.act_folder.setIcon(get_icon('folder'))
        self.act_prev.setIcon(get_icon('prev'))
        self.act_list.setIcon(get_icon('list'))
        self.act_next.setIcon(get_icon('next'))
        self.act_fit.setIcon(get_icon('fit'))
        self.act_fit.setEnabled(False)   # 没有图片时不可用
        self.act_ref.setIcon(get_icon('ref'))
        self.act_tooth.setIcon(get_icon('tooth'))
        self.act_undo.setIcon(get_icon('undo'))
        self.act_del.setIcon(get_icon('delete'))
        self.act_clear.setIcon(get_icon('clear'))
        self.act_export.setIcon(get_icon('export'))
        self.act_about.setIcon(get_icon('about'))

        tb.addAction(self.act_open)
        tb.addAction(self.act_folder)
        tb.addSeparator()
        tb.addAction(self.act_prev)
        tb.addAction(self.act_list)
        tb.addAction(self.act_next)
        tb.addSeparator()
        tb.addAction(self.act_fit)
        tb.addAction(self.act_ref)
        tb.addAction(self.act_tooth)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_del)
        tb.addAction(self.act_clear)
        # 「面板」是视图开关，不属于左侧的测量/编辑动作组，放到最右侧、
        # 紧邻「导出CSV」（导出是这张图最后要做的事，视图开关在它左边不打断动线）
        tb.addSeparator()
        tb.addAction(self.act_panel)
        tb.addAction(self.act_export)
        # 「使用说明」永远在最末：不参与测量动线，位置固定反而好找
        tb.addSeparator()
        tb.addAction(self.act_about)

        # 主行动按钮（导出 CSV）视觉突出
        export_btn = tb.widgetForAction(self.act_export)
        if export_btn is not None:
            export_btn.setObjectName('exportBtn')

        # 图标名映射（主题切换时据此重渲染所有工具栏图标）
        self._icon_pairs = [
            (self.act_panel, 'panel'),
            (self.act_open, 'open'),
            (self.act_folder, 'folder'),
            (self.act_prev, 'prev'),
            (self.act_list, 'list'),
            (self.act_next, 'next'),
            (self.act_fit, 'fit'),
            (self.act_ref, 'ref'),
            (self.act_tooth, 'tooth'),
            (self.act_undo, 'undo'),
            (self.act_del, 'delete'),
            (self.act_clear, 'clear'),
            (self.act_export, 'export'),
            (self.act_about, 'about'),
        ]

        # 工具栏按钮「保文字」优先级：数字越小，在窗口变窄时越优先保留文字标签。
        # 0=最高（导出，永远尽量保文字）；1=核心操作；2=次要；3=导航/辅助。
        self._tool_priority = [
            (self.act_export, 0),
            (self.act_open, 1),
            (self.act_folder, 1),
            (self.act_fit, 1),
            (self.act_ref, 1),
            (self.act_tooth, 1),
            (self.act_undo, 2),
            (self.act_del, 2),
            (self.act_clear, 2),
            (self.act_prev, 3),
            (self.act_list, 3),
            (self.act_next, 3),
            # 「面板」挪到最右后若仍排在最低优先级，常见宽度下它会孤零零一个纯图标
            # 贴在绿色导出按钮左边（同组的前后翻页都是图标，单独升文字又会参差）。
            # 提到 2 档，和「撤销/删除/清空」一起整组升降，视觉上才成组。
            (self.act_panel, 2),
            # 「使用说明」最不常用，窗口变窄时最先丢文字只剩图标
            (self.act_about, 4),
        ]

        self._esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._esc.activated.connect(self.canvas.cancel_pending)
        # Ctrl+1 原本只在画布有焦点时生效；挂到窗口级后，先点过按钮再按也能用
        self._sc_actual = QShortcut(QKeySequence('Ctrl+1'), self)
        self._sc_actual.activated.connect(self._on_actual_pixels)
        return tb

    def _connect(self) -> None:
        self.act_open.triggered.connect(self._open_image_dialog)
        self.act_folder.triggered.connect(self._open_folder_dialog)
        self.act_prev.triggered.connect(lambda: self._goto(self._folder_index - 1))
        self.act_next.triggered.connect(lambda: self._goto(self._folder_index + 1))
        self.act_list.triggered.connect(self._show_image_list)
        self.act_ref.triggered.connect(self._on_ref_toggled)
        self.act_tooth.triggered.connect(self._on_tooth_toggled)
        self.act_fit.triggered.connect(self._on_fit)
        self.act_undo.triggered.connect(self._on_undo)
        self.act_del.triggered.connect(self._on_delete)
        self.act_clear.triggered.connect(self._on_clear)
        self.act_export.triggered.connect(self._on_export_csv)
        self.act_about.triggered.connect(lambda: show_help(self))
        self.canvas.modeChanged.connect(self._on_canvas_mode_changed)
        self.canvas.drawStepChanged.connect(self._on_draw_step)
        self.canvas.referenceChanged.connect(self._on_reference_changed)
        self.canvas.toothChanged.connect(self._on_tooth_changed)
        self.canvas.selectionChanged.connect(self._on_selection_changed)
        self.canvas.statusText.connect(self.statusBar().showMessage)
        self.canvas.fileDropped.connect(self._on_file_dropped)
        self.canvas.contextMenuRequested.connect(self._show_canvas_menu)
        self.canvas.imageCloseRequested.connect(self._close_image)
        self.panel.fdiChanged.connect(self._on_fdi_changed)
        self.panel.rowClicked.connect(self._on_row_clicked)
        self.panel.rowDeleteClicked.connect(self._on_row_delete)
        self.panel.rowFdiEdited.connect(self._on_row_fdi_edited)

    def _on_fit(self) -> None:
        """回到打开图片时的整图大小（缩放复位 + 居中），对应 Ctrl+0。"""
        if not self.canvas.has_image():
            self.statusBar().showMessage('请先打开图片')
            return
        self.canvas.zoom_fit()
        self.canvas.setFocus()
        self.statusBar().showMessage('已适应窗口：回到整图大小（Ctrl+0）')

    def _on_actual_pixels(self) -> None:
        """实际像素 100%（Ctrl+1）。以前只有画布有焦点时按快捷键才有效，界面上无入口。"""
        if not self.canvas.has_image():
            self.statusBar().showMessage('请先打开图片')
            return
        self.canvas.zoom_actual()
        self.canvas.setFocus()
        self.statusBar().showMessage('实际像素 100%（Ctrl+1）')

    def _show_canvas_menu(self, global_pos: QPoint) -> None:
        """画布右键菜单：把散落在工具栏 / 快捷键里的操作放到鼠标当前位置。"""
        data = self.canvas.image_data
        has_image = self.canvas.has_image()
        has_teeth = bool(data and data.teeth)
        seq = self.canvas._selected_seq

        menu = QMenu(self)
        act_fit = menu.addAction('适应窗口  (Ctrl+0)')
        act_fit.setEnabled(has_image)
        act_px = menu.addAction('实际像素 100%  (Ctrl+1)')
        act_px.setEnabled(has_image)
        menu.addSeparator()
        label = f'删除选中记录（序号 {seq}）' if seq is not None else '删除选中记录'
        act_del = menu.addAction(label)
        act_del.setEnabled(seq is not None)
        act_clear = menu.addAction('清空所有线')
        act_clear.setEnabled(has_image and (has_teeth or bool(data and data.reference)))
        menu.addSeparator()
        act_copy = menu.addAction('复制当前角度') if seq is not None else None
        act_export = menu.addAction('导出 CSV…')
        act_export.setEnabled(has_teeth)

        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen is act_fit:
            self._on_fit()
        elif chosen is act_px:
            self._on_actual_pixels()
        elif chosen is act_del:
            self._on_delete()
        elif chosen is act_clear:
            self._on_clear()
        elif chosen is act_export:
            self._on_export_csv()
        elif act_copy is not None and chosen is act_copy:
            self._copy_current_angle(seq)

    def _copy_current_angle(self, seq: int) -> None:
        data = self.canvas.image_data
        for t in (data.teeth if data else []):
            if t.seq != seq:
                continue
            if t.angle_deg is None:
                self.statusBar().showMessage('该记录没有角度（缺参考线），无可复制内容')
                return
            txt = f'{t.angle_deg:+.1f}° {t.direction or ""}'.strip()
            QApplication.clipboard().setText(txt)
            self.statusBar().showMessage(f'已复制序号 {seq} 的角度：{txt}')
            return

    def _on_ref_toggled(self, checked: bool) -> None:
        if not self.canvas.has_image():
            self.statusBar().showMessage('请先打开图片')
            self.canvas.set_mode(Canvas.MODE_NONE)
            return
        if not checked:
            self.canvas.set_mode(Canvas.MODE_NONE)
            self._refresh_panel()   # 退出画线：恢复当前测量，别停在「点击第一点」提示上
            return
        has_ref = self.canvas._has_ref()
        self.canvas.set_mode(Canvas.MODE_REF)
        if has_ref:
            self.canvas._hide_ref = True
            self.canvas.update()
        self.panel.show_measuring(1, kind='ref')
        self.statusBar().showMessage(
            '重画参考线：点击两点（将覆盖现有线）' if has_ref else '参考线：点击两点定义基准方向')

    def _on_tooth_toggled(self, checked: bool) -> None:
        if not self.canvas.has_image():
            self.statusBar().showMessage('请先打开图片')
            self.canvas.set_mode(Canvas.MODE_NONE)
            return
        if not checked:
            self.canvas.set_mode(Canvas.MODE_NONE)
            self._refresh_panel()
            return
        self.canvas.set_mode(Canvas.MODE_TOOTH)
        self.panel.show_measuring(1)
        self.statusBar().showMessage('牙轴：根 → 冠，点击两点')

    def _on_canvas_mode_changed(self, mode: int) -> None:
        for act, m in ((self.act_ref, Canvas.MODE_REF),
                       (self.act_tooth, Canvas.MODE_TOOTH)):
            act.blockSignals(True)
            act.setChecked(mode == m)
            act.blockSignals(False)
        # 用 Esc / 右键取消画线时按钮会被取消勾选，但面板还停在画线提示上；
        # 这里同步回当前测量（内容签名没变时不会真的重建，开销可忽略）。
        if mode == Canvas.MODE_NONE and self.canvas.has_image():
            self._refresh_panel()

    def _on_draw_step(self, step: int, kind: str) -> None:
        self.panel.show_measuring(step, kind=kind)

    # ---------- 动作 ----------

    def _open_image_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, '打开全景片', self._last_dir, _IMAGE_FILTER)
        if path:
            self._last_dir = os.path.dirname(path)
            self._folder_images = []
            self._folder_index = -1
            self._open_path(path)
            self._update_nav_buttons()

    def _on_file_dropped(self, path: str) -> None:
        """拖入图片：这张图不属于当前文件夹，必须清掉翻页列表。

        之前不清，拖入 A 文件夹的图后按「下一张」会跳到之前打开的 B 文件夹，
        用户完全没法预期这个跳转。
        """
        self._folder_images = []
        self._folder_index = -1
        self._update_nav_buttons()
        self._open_path(path)

    def _open_folder_dialog(self) -> None:
        d = QFileDialog.getExistingDirectory(self, '选择图片文件夹', self._last_dir)
        if not d:
            return
        self._last_dir = d
        exts = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp'}
        files = sorted(
            os.path.join(d, f) for f in os.listdir(d)
            if os.path.splitext(f)[1].lower() in exts
        )
        if not files:
            QMessageBox.information(self, '空文件夹', '该文件夹下没有支持格式的图片')
            return
        self._folder_images = files
        self._goto(0)

    def _goto(self, idx: int) -> None:
        if not self._folder_images:
            return
        idx = max(0, min(idx, len(self._folder_images) - 1))
        path = self._folder_images[idx]
        self._folder_index = idx
        self._open_path(path)
        self._update_nav_buttons()

    def _update_nav_buttons(self) -> None:
        n = len(self._folder_images)
        self.act_prev.setEnabled(n > 1 and self._folder_index > 0)
        self.act_next.setEnabled(n > 1 and self._folder_index < n - 1)
        self.act_list.setEnabled(n > 0)
        if n > 1:
            self._show_open_status()

    def _show_image_list(self) -> None:
        """当前文件夹的图片列表：双击 / 回车 / 「打开」按钮都能切换。

        之前只有双击这一条路：没有按钮、没有回车，选中行的底色还是硬编码的
        深蓝色，亮色主题下白字压深蓝与整体风格完全脱节。
        """
        if not self._folder_images:
            self.statusBar().showMessage('请先打开文件夹（工具栏「文件夹」）')
            return
        dlg = QDialog(self)
        dlg.setWindowTitle('图片列表')
        dlg.resize(380, 480)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        # 每张图已测多少条：多图复查时不用一张张点开看，直接就能找到漏测的图。
        # 会话里的键是 abspath，这里按 normcase 建索引，避免盘符/大小写差异漏匹配。
        measured = {
            os.path.normcase(os.path.abspath(k)): len(v.teeth)
            for k, v in self.session.images.items() if v.teeth
        }
        done = sum(1 for p in self._folder_images
                   if measured.get(os.path.normcase(os.path.abspath(p))))
        head = QLabel(f'共 {len(self._folder_images)} 张 · 已测 {done} 张 · '
                      f'双击或回车打开')
        head.setStyleSheet(f'color:{theme.C_TEXT2};font-size:12px;')
        lay.addWidget(head)

        lw = QListWidget()
        lw.setUniformItemSizes(True)
        for i, p in enumerate(self._folder_images):
            name = os.path.basename(p)
            if i == self._folder_index:
                name = f'{name}（当前）'
            n = measured.get(os.path.normcase(os.path.abspath(p)), 0)
            mark = f'已测 {n} 条' if n else '未测'
            item = QListWidgetItem(f'{name}    {mark}')
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setToolTip(f'{p}\n{mark}')
            lw.addItem(item)
        lw.setCurrentRow(self._folder_index)
        lay.addWidget(lw, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        btn_cancel = QPushButton('取消')
        btn_open = QPushButton('打开')
        btn_open.setDefault(True)
        btn_open.setStyleSheet(
            f'QPushButton{{background:{theme.C_ACCENT};color:{theme.C_ACCENT_FG};'
            f'border:1px solid {theme.C_ACCENT};border-radius:7px;'
            f'padding:6px 20px;font-size:13px;font-weight:600;}}'
            f'QPushButton:hover{{background:{theme.C_ACCENT_H};border-color:{theme.C_ACCENT_H};}}'
            f'QPushButton:pressed{{background:{theme.C_ACCENT_P};border-color:{theme.C_ACCENT_P};}}')
        row.addWidget(btn_cancel)
        row.addWidget(btn_open)
        lay.addLayout(row)

        picked = {'ok': False}

        def _accept() -> None:
            idx = lw.currentRow()
            if idx < 0:
                return
            picked['ok'] = True
            dlg.accept()

        btn_cancel.clicked.connect(dlg.reject)
        btn_open.clicked.connect(_accept)
        lw.itemDoubleClicked.connect(lambda *_: _accept())
        lw.itemActivated.connect(lambda *_: _accept())   # 回车
        if dlg.exec() == QDialog.DialogCode.Accepted and picked['ok']:
            self._goto(lw.currentRow())
            self.canvas.setFocus()

    def _open_path(self, path: str) -> None:
        try:
            img = load_image(path)
        except Exception as exc:
            QMessageBox.warning(self, '无法打开图片', str(exc))
            return
        w, h = image_size(img)
        qimg = convert_for_qt(img)
        abs_path = os.path.abspath(path)
        # 复用会话里已保存的测量结果：换图 / 翻页 / 关掉软件后重开，线都还在。
        # 之前的实现每次新建空 ImageData 且从不写回会话，等于每次打开都是白纸。
        image_data = self.session.images.get(abs_path)
        if image_data is None:
            image_data = ImageData(file=abs_path)
        image_data.file = abs_path
        if (image_data.width, image_data.height) != (w, h):
            if image_data.width or image_data.height:
                # 同一路径的图被替换 / 改过尺寸：旧像素坐标已不可信，避免错位标注
                image_data.teeth.clear()
                image_data.reference = None
            image_data.width, image_data.height = w, h
        self._current_path = abs_path
        self._last_dir = os.path.dirname(abs_path)
        self.centralWidget().layout().activate()
        self.canvas.set_image(qimg, image_data)
        # 历史记录里存的 angle_deg 是「打开时那个版本」算出来的。算法换过（v1.0
        # 的符号规则把上颌牙算反了），直接显示旧值会把错误一直留在界面上，
        # 所以每次打开都按当前算法重算一遍 —— 幂等，且顺带修正旧数据。
        self.canvas.recompute_all_teeth()
        # 文件名 + 尺寸放到画布左下角浮层（结果面板底部不再占一行）
        self.canvas.set_caption(f'{os.path.basename(path)} · {w} × {h}')
        n = len(image_data.teeth)
        self._open_name = os.path.basename(path)
        self._open_size = f'{w} × {h}'
        self._open_note = f'已载入 {n} 条历史记录' if n else '点击「参考线」定义基准方向'
        self._show_open_status()
        self._refresh_tool_buttons()
        self._refresh_panel()
        self._schedule_save()

    def _close_image(self) -> None:
        """关闭当前图片，回到空白工作区（左下角文件名右侧的 × ）。

        **只关不删**：测量结果仍留在会话里，重新打开同一张图就都回来了。
        所以这里不写盘、也不清 session.images —— 用户按 × 是想腾开画布看别的片子，
        不是想毁掉刚测的数据（真要删有「清空」）。
        """
        if not self.canvas.has_image():
            return
        # 画线途中直接点 × 时，先把工具退回「无」：否则 act_ref 还勾着，
        # 而画布模式已经空了，再点一次「参考线」只会把它取消勾选，看着像失灵。
        if self.canvas.mode != Canvas.MODE_NONE:
            self.canvas.set_mode(Canvas.MODE_NONE)
        self.canvas.clear_image()
        self._current_path = None
        self._open_name = ''
        self._open_size = ''
        self._open_note = ''
        self._scroll_to_seq = None
        # 画布已经清空，面板不会自己知道：列表得显式清空，否则右边还挂着
        # 上一张图的记录，点它就会作用到空画布上。
        self.panel.refresh_list([], None)
        self._refresh_panel()
        self._refresh_tool_buttons()
        self._update_nav_buttons()
        self.statusBar().showMessage('已关闭图片 · 可拖入图片或按 Ctrl+O 打开')

    def _show_open_status(self) -> None:
        """把「第 x/n 张」与「已打开 文件名 · 尺寸」拼成一条消息显示。"""
        if not self._open_name:
            return
        n = len(self._folder_images)
        nav = (f'第 {self._folder_index + 1} / {n} 张 · '
               if n > 1 and self._folder_index >= 0 else '')
        self.statusBar().showMessage(
            f'{nav}{self._open_name} · {self._open_size} · {self._open_note}')

    def _on_reference_changed(self) -> None:
        has = self.canvas._has_ref()
        self.act_ref.setText('重画参考线' if has else '参考线')
        self._refresh_panel()
        self._schedule_save()

    def _on_tooth_changed(self) -> None:
        self._refresh_panel()
        self._schedule_save()

    def _on_selection_changed(self, seq) -> None:
        if seq is None:
            self.statusBar().showMessage('已取消选中')
            self._scroll_to_seq = None
        else:
            self.statusBar().showMessage(f'已选中序号 {seq}')
            # 新画的牙 / 画布上点选的牙，让列表滚到对应行；否则记录一多就看不见
            self._scroll_to_seq = int(seq)
        # 列表高亮 + 当前测量块跟随选中项
        if self.canvas.image_data:
            self._refresh_panel()

    def _apply_fdi(self, tooth, text: str) -> None:
        """写入牙号：先校验格式与是否重复。

        以前这里不做任何校验，「ab」「00」「99」都能写进去，重复牙号也毫无提示，
        导出的 CSV 里就会出现根本不存在的牙位。
        """
        s = (text or '').strip()
        if not is_valid_fdi(s):
            self.statusBar().showMessage(
                f'牙号「{s}」不合法：应为两位 FDI 编号（如 16 / 31 / 48，乳牙 51-85）')
            # 输入框里是非法值，但模型没变 → 内容签名不变 → 面板不会重建，
            # 那个错字会一直留在输入框里。强制重建一次把它退回原值。
            self.panel.force_current_refresh()
            self._refresh_panel()
            return
        tooth.fdi = s
        self.canvas.recompute_all_teeth()
        self._schedule_save()
        others = [t for t in self.canvas.image_data.teeth
                  if t is not tooth and s and t.fdi == s]
        if others:
            self.statusBar().showMessage(
                f'序号 {tooth.seq} 的牙位「{s}」与序号 {others[0].seq} 重复，请复核')
        else:
            self.statusBar().showMessage(f'序号 {tooth.seq} 牙位已更新为「{s or "空"}」')

    def _on_fdi_changed(self, text: str) -> None:
        tooth = self.canvas.current_tooth()
        if tooth is None:
            return
        self._apply_fdi(tooth, text)

    # ---------- P2：撤销 / 删除 / 列表交互 ----------

    def _on_undo(self) -> None:
        if not self.canvas.undo():
            self.statusBar().showMessage('没有可撤销的操作')
        self._refresh_panel()

    def _on_delete(self) -> None:
        seq = self.canvas._selected_seq
        if seq is None:
            self.statusBar().showMessage('请先在画布或列表中选中一条记录')
            return
        self.canvas.removeTooth(seq)
        self._refresh_panel()

    def _on_clear(self) -> None:
        """清空当前图所有线（先确认）。

        以前点一下就清空、且快捷键是 `Ctrl+Shift+Z` —— 这个组合在几乎所有绘图
        软件里都是「重做」，用户按下去想恢复上一步，结果把整张图清空了。
        现在：快捷键改成 `Ctrl+Shift+Del`，并且有内容时先弹确认（默认按钮是取消）。
        """
        data = self.canvas.image_data
        n = len(data.teeth) if data is not None else 0
        has_ref = bool(data is not None and data.reference)
        if not n and not has_ref:
            return

        what: list[str] = []
        if has_ref:
            what.append('参考线')
        if n:
            what.append(f'{n} 条牙长轴记录')

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle('清空所有线')
        box.setText(f'将清空当前图片的{"和 ".join(what)}。')
        box.setInformativeText('清空后可按 Ctrl+Z 撤销。')
        btn_yes = box.addButton('清空', QMessageBox.ButtonRole.DestructiveRole)
        btn_no = box.addButton('取消', QMessageBox.ButtonRole.RejectRole)
        # 危险动作用红底，和旁边的中性「取消」区分开（QSS 里没有 destructive 角色样式）
        btn_yes.setStyleSheet(
            f'QPushButton{{background:{theme.C_DANGER};color:#ffffff;'
            f'border:1px solid {theme.C_DANGER};border-radius:7px;'
            f'padding:5px 16px;font-weight:600;}}'
            f'QPushButton:hover{{background:{theme.C_DANGER};border-color:{theme.C_TEXT};}}')
        box.setDefaultButton(btn_no)
        box.setEscapeButton(btn_no)
        box.exec()
        if box.clickedButton() is not btn_yes:
            return

        if self.canvas.clear_all():
            self._refresh_panel()
            _log.info('清空当前图所有线：%s', self._current_path)

    def _ask_patient_info(self) -> bool:
        """导出前填病例号 / 操作者（记住上次输入，直接写进 CSV 每行）。

        早先 CSV 里有 patient_id / operator_id 两列但界面上没有任何入口，
        恒为空 —— 表格里等于白占两列，事后也没法把记录对上病例。
        """
        dlg = QDialog(self)
        dlg.setWindowTitle('病例信息')
        dlg.setMinimumWidth(360)
        form = QFormLayout(dlg)
        form.setContentsMargins(18, 16, 18, 14)
        form.setSpacing(12)

        ed_patient = QLineEdit(self.session.patient_id)
        ed_patient.setPlaceholderText('可留空，如 P-20261029-001')
        ed_oper = QLineEdit(self.session.operator_id)
        ed_oper.setPlaceholderText('可留空，如 李医生')
        form.addRow('病例号', ed_patient)
        form.addRow('操作者', ed_oper)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText('下一步：选择保存位置')
        ok.setProperty('class', 'accent')
        ok.style().unpolish(ok)
        ok.style().polish(ok)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        self.session.patient_id = ed_patient.text().strip()
        self.session.operator_id = ed_oper.text().strip()
        self._schedule_save()
        return True

    def _on_export_csv(self) -> None:
        if self._current_path is None:
            self.statusBar().showMessage('请先打开图片')
            return
        data = self.canvas.image_data
        if data is None or not data.teeth:
            self.statusBar().showMessage('当前图片还没有测量记录')
            QMessageBox.information(self, '没有可导出的记录',
                                    '当前图片还没有任何测量记录。\n请先画参考线和牙长轴后再导出。')
            return
        if not self._ask_patient_info():
            self.statusBar().showMessage('已取消导出')
            return
        default_name = f'imageangle_{os.path.splitext(os.path.basename(self._current_path))[0]}.csv'
        default_path = os.path.join(self._last_dir or os.path.expanduser('~'), default_name)
        path, _ = QFileDialog.getSaveFileName(
            self, '导出 CSV', default_path, 'CSV 文件 (*.csv)')
        if not path:
            return
        try:
            # 直接导出画布上的当前数据：会话文件里存的是历史图，按路径反查会取到旧记录
            n = export_session_csv(self.session, path, images=[data])
            QMessageBox.information(self, '导出成功', f'已导出 {n} 条记录到\n{path}')
            self.statusBar().showMessage(f'已导出 {n} 条记录 → {path}')
        except Exception as exc:
            QMessageBox.warning(self, '导出失败', str(exc))

    def _on_row_clicked(self, seq: int) -> None:
        self.canvas.setSelected(seq)
        self.panel.scroll_to_seq(seq)

    def _on_row_delete(self, seq: int) -> None:
        self.canvas.removeTooth(seq)
        self._refresh_panel()

    def _on_row_fdi_edited(self, seq: int, text: str) -> None:
        if self.canvas.image_data is None:
            return
        for t in self.canvas.image_data.teeth:
            if t.seq == seq:
                self._apply_fdi(t, text)
                break

    def _refresh_panel(self) -> None:
        tooth = self.canvas.current_tooth()
        if tooth is None:
            # 没打开图片 vs 打开了还没画线，提示必须分开：启动恒为空之后，
            # 空白画布上却让用户「先画参考线」是没法照做的。
            self.panel.show_blank('' if self.canvas.has_image()
                                  else '先打开一张全景片（Ctrl+O 或直接拖入）')
        else:
            self.panel.show_result(tooth)
        # 拖动端点时画布每帧都会发 toothChanged：只更新「当前测量」的数值，
        # 不重建整张列表。14 条记录 = 每帧新建 80+ 个控件，实测掉帧明显；
        # 松手时画布会补发一次 toothChanged，那时再全量刷新。
        if self.canvas.image_data and not self.canvas.is_dragging():
            self.panel.refresh_list(self.canvas.image_data.teeth, self.canvas._selected_seq)
            if self._scroll_to_seq is not None:
                self.panel.scroll_to_seq(self._scroll_to_seq)
                self._scroll_to_seq = None
        self._refresh_tool_buttons()

    def _refresh_tool_buttons(self) -> None:
        """按当前状态决定工具栏按钮可用性。

        以前这里恒为 True，没打开图片时九个按钮全是可点的，点下去只在状态栏
        弹一句「请先打开图片」，看着像软件坏了。
        """
        has_image = self.canvas.has_image()
        data = self.canvas.image_data
        teeth = list(data.teeth) if data else []
        has_content = bool(teeth) or bool(data and data.reference)
        self.act_ref.setEnabled(has_image)
        self.act_tooth.setEnabled(has_image)
        self.act_fit.setEnabled(has_image)
        self.act_undo.setEnabled(has_image and bool(self.canvas._undo_stack))
        self.act_del.setEnabled(has_image and self.canvas._selected_seq is not None)
        self.act_clear.setEnabled(has_image and has_content)
        self.act_export.setEnabled(has_image and bool(teeth))

    # ---------- 主题切换 ----------
    def _toggle_theme(self) -> None:
        theme.set_theme('light' if theme.is_dark() else 'dark')
        self._apply_theme()
        self._save_theme_pref()

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.build_qss())
            app.processEvents()  # 让 QSS 触发的 toolbutton 重建完成，避免后续按钮 style 被覆盖
        self._refresh_tool_icons()
        self._title_bar.refresh_theme()
        self.canvas.refresh_theme()
        self.panel.refresh_theme()
        self._refresh_panel()  # 重建面板内容，跟随主题色
        # 圆角外缘的 1px 描边色跟随主题（暗色 #333 / 亮色 #d0d7de）
        self._sync_window_rounding()
        # QSS 重建 toolbuttons 后，重新按当前窗口宽度计算工具栏布局（混合式）
        self._update_responsive(self.width(), force=True)

    def _refresh_tool_icons(self) -> None:
        for act, name in getattr(self, '_icon_pairs', []):
            # 导出是唯一「填充式」按钮：图标必须用按钮前景色（暗色薄荷底配深墨，
            # 亮色蓝底配白），否则浅灰图标压在薄荷绿上几乎看不见。
            if name == 'export':
                act.setIcon(get_icon(name, theme.C_ACCENT_FG))
            else:
                act.setIcon(get_icon(name))

    def _load_theme_pref(self) -> str:
        try:
            p = paths.theme_pref_path()
            if os.path.exists(p):
                with open(p, encoding='utf-8') as f:
                    data = f.read().strip()
                if data in ('dark', 'light'):
                    return data
                _log.warning('主题偏好内容异常（%r），回落深色', data[:20])
        except Exception:
            _log.warning('主题偏好读取失败，回落深色', exc_info=True)
        return 'dark'

    def _save_theme_pref(self) -> None:
        try:
            p = paths.theme_pref_path()
            with open(p, 'w', encoding='utf-8') as f:
                f.write(theme.THEME_NAME)
        except Exception:
            _log.warning('主题偏好保存失败：%s', paths.theme_pref_path(), exc_info=True)

    # ---------- 结果面板折叠（抽屉） ----------
    def _toggle_panel(self, checked: bool) -> None:
        # 用户显式选择：True=强制显示，False=强制隐藏；None=恢复跟随自适应
        self._panel_user_override = bool(checked)
        self._update_panel_visibility()

    def _want_panel_visible(self) -> bool:
        if self._panel_user_override is not None:
            return self._panel_user_override
        return not self._panel_auto_collapsed

    def _update_panel_visibility(self) -> None:
        want = self._want_panel_visible()
        if want and self._panel_hidden:
            self.panel.show()
            self._content_lay.addWidget(self.panel)  # 加回右侧
            self._panel_hidden = False
        elif not want and not self._panel_hidden:
            self._content_lay.removeWidget(self.panel)
            self.panel.hide()
            self._panel_hidden = True
        # 同步工具按钮勾选态（静默，避免递归触发 toggled）
        self.act_panel.blockSignals(True)
        self.act_panel.setChecked(want)
        self.act_panel.blockSignals(False)

    # ---------- 响应式 ----------
    def _set_btn_style(self, action, style) -> None:
        w = self._toolbar.widgetForAction(action)
        if w is not None:
            w.setToolButtonStyle(style)

    def _update_responsive(self, width: int, force: bool = False) -> None:
        tb = self._toolbar
        TEXT = Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        ICON = Qt.ToolButtonStyle.ToolButtonIconOnly
        avail = width - 28
        # 混合式布局：先全部设为纯图标（最省空间），再按优先级「整组」升级为
        # 图文并排，直到放不下为止。整组升降而不是逐按钮，是为了避免出现
        #「上一张 列表 >」这种同组一半有字一半没字的参差感。
        groups: dict = {}
        for a, pri in self._tool_priority:
            groups.setdefault(pri, []).append(a)
        for a, _ in self._tool_priority:
            self._set_btn_style(a, ICON)
        for pri in sorted(groups):
            for a in groups[pri]:
                self._set_btn_style(a, TEXT)
            if tb.sizeHint().width() > avail:
                for a in groups[pri]:
                    self._set_btn_style(a, ICON)
        # 兜底：sizeHint 在连续改样式时可能滞后，若整体仍溢出，按优先级从低到高
        # 把文字收掉，直到放得下。否则 Qt 会把末尾的「导出CSV」丢进溢出菜单
        # （窄屏下那条 » 几乎看不见），用户会以为导出按钮消失了。
        for pri in sorted(groups, reverse=True):
            if tb.sizeHint().width() <= avail:
                break
            if pri == 0:
                continue
            for a in groups[pri]:
                self._set_btn_style(a, ICON)
        # 窄屏（<1060）：结果面板自动折叠（用户未强制显示时）
        auto = width < 1060
        if force or auto != self._panel_auto_collapsed:
            self._panel_auto_collapsed = auto
            self._update_panel_visibility()
        # QSS 刚重建过 toolbutton 时 sizeHint 会滞后（连续改 style 也有同样问题），
        # 按滞后值算出来的结论可能偏大或偏小：偏小会把「导出CSV」推进溢出菜单
        # （那条 » 在暗色下几乎看不见，用户以为按钮没了）。样式刚改完的场景
        # （force=True：启动 / 换主题）安排一次事件循环后的复算，那时值已刷新。
        if force and not self._resp_recheck_pending:
            self._resp_recheck_pending = True
            self._resp_timer.start()

    def _recheck_responsive(self) -> None:
        try:
            self._update_responsive(self.width())
        finally:
            self._resp_recheck_pending = False

    def resizeEvent(self, e) -> None:
        self._update_responsive(self.width())
        super().resizeEvent(e)

"""使用说明对话框（原「关于」）。

一屏只放三样东西：图标 + 名称 + 版本（后面跟「本软件免费，已开源」），
下面两个折叠栏 ——「打赏作者」展开两枚收款码，「使用说明」展开操作要点与算法。
折叠栏默认收起：想扫码的人点上一栏，想查用法的人点下一栏，谁都不必先滚过
一整屏与自己无关的内容。

入口在工具栏最右端（F1）。版本来自 ``app.__version__``，图标走
``resources.icon_path()``（打包后指向 _MEIPASS）。

样式刻意只用主题令牌里的颜色，不写死色值 —— 深浅两套主题下都要能读，
对话框每次打开时按当前主题重建，切主题后再打开就是新配色。
"""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel,
                               QVBoxLayout, QWidget)

from .. import __version__
from ..io.resources import icon_path, resource_dir
from . import theme

APP_NAME = 'ImageAngle'
AUTHOR = '基耶杰'
FREE_NOTE = '本软件免费，已开源'
GITHUB_URL = 'https://github.com/ASH-C776/ImageAngle'
GITEE_URL = 'https://gitee.com/kijeye/ImageAngle'
GITHUB_TEXT = 'github.com/ASH-C776/ImageAngle'
GITEE_TEXT = 'gitee.com/kijeye/ImageAngle'
DONATE_TITLE = '打赏作者'
HELP_TITLE = '使用说明'
# 打赏区：微信 / 支付宝收款码（已裁掉姓名文字的正方形 PNG，可点击看原图）
DONATE_QR = (
    ('donate_wechat.png', '微信收款码'),
    ('donate_alipay.png', '支付宝收款码'),
)


class QRLabel(QLabel):
    """可点击的收款码图：左键点击弹原图预览。"""

    clicked = Signal(str, str)          # (路径, 标题)

    def __init__(self, path: str, title: str):
        super().__init__()
        self._path = path
        self._title = title
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f'点击查看{title}原图')

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._path, self._title)
        super().mousePressEvent(e)


class _FoldHead(QWidget):
    """折叠栏的标题行：左侧箭头 + 标题，整行可点。

    自绘而不用 QPushButton：QPushButton 放不下「箭头 + 文字」的精确对齐
    （箭头要跟文字基线居中），而这里连 hover 底都是自己画的，一件控件到底，
    深浅主题下都不用担心 QSS 把箭头染成看不见的颜色。
    """

    clicked = Signal()

    H = 38

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._open = False
        self._hover = False
        self.setObjectName('foldHead')
        self.setFixedHeight(self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def title(self) -> str:
        return self._title

    def is_open(self) -> bool:
        return self._open

    def set_open(self, on: bool) -> None:
        if self._open != on:
            self._open = on
            self.update()

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect().adjusted(0, 1, 0, -1)
        if self._hover:
            # theme.C_HOVER 是给 QSS 用的 'rgba(...)' 字符串，QColor 解析不了
            # （会静默变成黑色）。这里改用主题文字色 + 低不透明度叠加，
            # 深浅两套主题各自成立：亮色下压深、暗色下提亮。
            p.setPen(Qt.PenStyle.NoPen)
            p.setOpacity(0.06)
            p.setBrush(QColor(theme.C_TEXT))
            p.drawRoundedRect(r, 7, 7)
            p.setOpacity(1.0)

        pen = QPen(QColor(theme.C_TEXT2 if self._hover else theme.C_TEXT3), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        cx, cy = 13, self.H // 2
        if self._open:                       # 展开：向下的 v
            p.drawLine(cx - 4, cy - 2, cx, cy + 2)
            p.drawLine(cx, cy + 2, cx + 4, cy - 2)
        else:                                # 收起：向右的 >
            p.drawLine(cx - 2, cy - 4, cx + 2, cy)
            p.drawLine(cx + 2, cy, cx - 2, cy + 4)

        f = self.font()
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.C_TEXT))
        p.drawText(r.adjusted(28, 0, -10, 0),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._title)


class FoldSection(QWidget):
    """折叠区块：标题行 + 展开后才出现的内容。"""

    INDENT = 28      # 内容相对标题行的左缩进（标题文字从 28px 起）

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName('foldSection')
        self.head = _FoldHead(title, self)
        self.head.clicked.connect(self.toggle)

        self.body = QWidget(self)
        self.body.setObjectName('foldBody')
        self.body.setVisible(False)
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(FoldSection.INDENT, 0, 0, 12)
        self.body_lay.setSpacing(10)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.head)
        lay.addWidget(self.body)

    def toggle(self) -> None:
        # 用标题自身的开合状态，不看 body.isVisible()：窗口还没 show 时
        # isVisible() 恒为 False，会把「再点一次收起」变成永远展开。
        self.set_open(not self.head.is_open())

    def set_open(self, on: bool) -> None:
        self.body.setVisible(on)
        self.head.set_open(on)


class HelpDialog(QDialog):
    """使用说明 / 打赏，两个折叠栏，440px 宽；Esc / 回车 / 标题栏 × 退出。"""

    W = 440          # 全对话框宽（_fit 会锁死它，见 _fit 的注释）
    PAD = 24         # 左右内边距
    INDENT = 28      # 折叠栏内容相对内边距的缩进

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(HELP_TITLE)
        self.setModal(True)
        self.setFixedWidth(self.W)
        path = icon_path()
        if path:
            self.setWindowIcon(QIcon(path))
        self._pal = theme.PALETTES[theme.THEME_NAME]
        self._build()
        self.setStyleSheet(self._qss())

    # ---- 构建 ----
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 24, 18)
        outer.setSpacing(0)

        # ① 头部：图标 + 名称 + 版本 + 免费开源
        head = QHBoxLayout()
        head.setSpacing(16)

        icon = QLabel()
        path = icon_path()
        if path:
            icon.setPixmap(QIcon(path).pixmap(QSize(56, 56)))
        icon.setFixedSize(56, 56)
        icon.setObjectName('helpIcon')
        head.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(8)
        name = QLabel(APP_NAME)
        name.setObjectName('helpName')
        ver = QLabel(f'版本 {__version__}')
        ver.setObjectName('helpVersion')
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setFixedHeight(22)
        free = QLabel(FREE_NOTE)
        free.setObjectName('helpFree')
        ver_row = QHBoxLayout()
        ver_row.setContentsMargins(0, 0, 0, 0)
        ver_row.setSpacing(8)
        ver_row.addWidget(ver, 0)
        ver_row.addWidget(free, 0)
        ver_row.addStretch(1)

        text_col.addStretch(1)
        text_col.addWidget(name)
        text_col.addLayout(ver_row)
        text_col.addStretch(1)
        head.addLayout(text_col, 1)
        outer.addLayout(head)

        outer.addSpacing(16)
        outer.addWidget(self._divider())
        outer.addSpacing(2)

        # ② 折叠栏一：打赏作者（展开才是二维码）
        self.fold_donate = FoldSection(DONATE_TITLE)
        self._fill_donate(self.fold_donate.body_lay)
        self.fold_donate.head.clicked.connect(self._fit)
        outer.addWidget(self.fold_donate)

        outer.addWidget(self._divider())

        # ③ 折叠栏二：使用说明
        self.fold_help = FoldSection(HELP_TITLE)
        help_lab = QLabel(self._help_html())
        help_lab.setObjectName('helpText')
        help_lab.setTextFormat(Qt.TextFormat.RichText)
        help_lab.setWordWrap(True)
        # 对话框宽 − 左右边距 − 折叠栏缩进
        help_lab.setFixedWidth(self.W - 2 * self.PAD - self.INDENT)
        help_lab.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.fold_help.body_lay.addWidget(help_lab)
        self.fold_help.head.clicked.connect(self._fit)
        outer.addWidget(self.fold_help)

        outer.addWidget(self._divider())
        outer.addSpacing(10)

        # ④ 作者 / 地址：固定在折叠栏下方（展开收起都不跟着跑）
        # 这里就是最后一行 —— 不再放「关闭」按钮：标题栏已有 ×，Esc / 回车
        # 也能退（见 keyPressEvent），底部再摆一个只占高度不添信息。
        author = QLabel(f'作者：{AUTHOR}')
        author.setObjectName('helpMeta')
        addr = QLabel('地址：' + self._link(GITHUB_URL, 'GitHub')
                      + '&nbsp;&nbsp;&nbsp;&nbsp;' + self._link(GITEE_URL, 'Gitee'))
        addr.setObjectName('helpMeta')
        addr.setOpenExternalLinks(True)
        addr.setToolTip(f'{GITHUB_URL}\n{GITEE_URL}')
        outer.addWidget(author)
        outer.addSpacing(4)
        outer.addWidget(addr)

    def _fill_donate(self, box: QVBoxLayout) -> None:
        """两枚码并排居中（展开这一栏只看得到码，作者与地址在折叠栏下方）。"""
        qr_row = QHBoxLayout()
        qr_row.setSpacing(24)
        qr_row.addStretch(1)
        for fname, caption in DONATE_QR:
            qr_row.addLayout(self._qr_tile(fname, caption))
        qr_row.addStretch(1)
        box.addLayout(qr_row)

    def _link(self, url: str, text: str) -> str:
        return (f'<a href="{url}" style="color:{self._pal["accent"]};'
                f' text-decoration:none;">{text}</a>')

    def _fit(self) -> None:
        """折叠栏开合后重算窗口尺寸（延后一拍执行，见 _fit_now）。"""
        # body 刚 setVisible 时布局里还留着它展开时的尺寸，同一调用栈里量到的
        # 仍是旧高度；排到事件循环下一拍，布局才真正把隐藏的内容剔出去。
        QTimer.singleShot(0, self._fit_now)

    def _fit_now(self) -> None:
        """宽度锁死 440，高度按布局实际内容重算。

        不能用 adjustSize()：它只在 sizeHint 小于「当前」尺寸时才收缩，
        展开一次后窗口会永久停在展开时的高度，顶部标题行被垂直居中拉开 ——
        看起来就像「标题被撑宽了」。每次 setFixedSize 宽高一起归位才干净。
        """
        lay = self.layout()
        lay.invalidate()
        lay.activate()
        self.setFixedSize(self.W, lay.sizeHint().height())

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._fit()

    def keyPressEvent(self, e) -> None:
        """回车 / 小键盘回车 = 关闭。

        去掉了底部「关闭」按钮，原本的 Enter 默认按钮也一并没了；
        Esc 是 QDialog 自带的（reject），这里补上回车，键盘习惯不断。
        """
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
            return
        super().keyPressEvent(e)

    # ---- 富文本正文 ----
    def _help_html(self) -> str:
        p = self._pal
        acc, danger, t2, t3 = p['accent'], p['danger'], p['text2'], p['text3']
        mono = 'font-family:Consolas,\'Courier New\',monospace;'

        def key(k: str) -> str:
            return (f'<span style="{mono}color:{acc};font-weight:bold;">{k}</span>')

        def row(label: str, body: str) -> str:
            return (f'<p style="margin:0 0 8px 0;font-size:12px;color:{t2};">'
                    f'<span style="color:{t3};">{label}</span>　{body}</p>')

        first = (
            f'<p style="margin:0 0 10px 0;font-size:13px;color:{p["text"]};">'
            f'<span style="color:{acc};font-weight:bold;">先点牙根尖，再点牙冠中点</span>'
            f'　<span style="color:{danger};">顺序点反，正负号会反。</span>'
            f'</p>')

        return ''.join((
            first,
            row('画线',
                f'打开片子（{key("←")} {key("→")} 翻片）· {key("R")} 沿腭中缝点两点 · '
                f'{key("T")} 先根后冠，画完即出读数，可连画'),
            row('读数',
                f'<span style="color:{acc};">近中为正、远中为负</span>；'
                f'<span style="color:{danger};">|角度| &gt; 30°</span> 标红待复核'),
            row('算法',
                f'取牙轴与参考线的夹角（折进 ±90° 后取绝对值）；'
                f'正负看牙根在参考线哪一侧，再看牙冠偏向中线'
                f'<span style="color:{acc};">(+)</span> 还是背离'
                f'<span style="color:{acc};">(−)</span>。'
                f'<span style="color:{t3};">参考线需大致竖直。</span>'),
        ))

    # ---- 小部件工厂 ----
    def _qr_tile(self, fname: str, caption: str) -> QVBoxLayout:
        """单枚收款码：白底边框图 + 居中说明；点击弹原图预览。"""
        tile = QVBoxLayout()
        tile.setSpacing(6)
        tile.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        path = os.path.join(resource_dir(), fname)
        qr = QRLabel(path, caption)
        qr.clicked.connect(self._show_qr_preview)
        qr.setFixedSize(108, 108)
        qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.isfile(path):
            pm = QPixmap(path).scaled(
                108, 108, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            qr.setPixmap(pm)
            qr.setObjectName('helpQR')
        else:
            qr.setText('收款码\n缺失')
            qr.setObjectName('helpQRPlaceholder')
        tile.addWidget(qr, 0, Qt.AlignmentFlag.AlignHCenter)

        cap = QLabel(caption)
        cap.setObjectName('helpQRCaption')
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.addWidget(cap, 0, Qt.AlignmentFlag.AlignHCenter)
        return tile

    def _show_qr_preview(self, path: str, title: str) -> None:
        """原图预览：全分辨率显示，点图或 Esc 关闭。"""
        if not os.path.isfile(path):
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setModal(True)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        limit = int(min(screen.width(), screen.height()) * 0.8)
        pm = QPixmap(path)
        if pm.width() > limit or pm.height() > limit:
            pm = pm.scaled(limit, limit, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        lab = QLabel()
        lab.setPixmap(pm)
        lab.setCursor(Qt.CursorShape.PointingHandCursor)
        lab.mousePressEvent = lambda _e: dlg.accept()   # 点图即关
        box = QVBoxLayout(dlg)
        box.setContentsMargins(12, 12, 12, 12)
        box.addWidget(lab, 0, Qt.AlignmentFlag.AlignCenter)
        hint = QLabel('点图关闭 · 此为原图分辨率')
        hint.setObjectName('helpNote')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(hint)
        dlg.exec()

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setObjectName('helpDivider')
        # 用 NoFrame + 背景色画 1px 线：HLine 自带描边会盖掉 QSS 的 background，
        # 结果在暗色下几乎看不见
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setFixedHeight(1)
        return line

    def _qss(self) -> str:
        p = self._pal
        return f"""
        QDialog {{ background: {p['surface']}; }}
        /* 全局 QSS 的 QWidget 规则会把所有子件刷成窗口底色（灰），
           折叠栏的标题行与内容区必须显式透明，否则会浮出两块灰方块。 */
        #foldHead, #foldBody, #foldSection {{ background: transparent; }}
        /* 全局 QSS 把 QWidget 底色刷成窗口色，QLabel 也是 QWidget，
           不显式透明的话亮色主题下每行文字都会顶一块白底 (#helpQR 除外)。 */
        QDialog QLabel {{ background: transparent; }}
        QLabel#helpName {{ color: {p['text']}; font-size: 20px; font-weight: 600; }}
        QLabel#helpVersion {{
            color: {p['accent']};
            background: {p['accent_soft']};
            border: 1px solid {p['accent_line']};
            border-radius: 9px;
            padding: 0 9px;
            font-size: 11px;
        }}
        QLabel#helpFree {{ color: {p['text2']}; font-size: 12px; }}
        QLabel#helpText {{ color: {p['text2']}; }}
        QLabel#helpMeta {{ color: {p['text2']}; font-size: 12px; }}
        QLabel#helpNote {{ color: {p['text3']}; font-size: 11px; }}
        QLabel#helpQR {{
            background: #ffffff;
            border: 1px solid {p['border']};
            border-radius: 8px;
        }}
        QLabel#helpQR:hover {{ border: 1px solid {p['accent']}; }}
        QLabel#helpQRCaption {{ color: {p['text']}; font-size: 12px; }}
        QLabel#helpQRPlaceholder {{
            color: {p['text3']};
            font-size: 11px;
            background: #ffffff;
            border: 1px dashed {p['border']};
            border-radius: 8px;
        }}
        QFrame#helpDivider {{ background: {p['border']}; border: none; }}
        """


def show_help(parent=None) -> None:
    """点工具栏「使用说明」或按 F1 时调用。"""
    HelpDialog(parent).exec()

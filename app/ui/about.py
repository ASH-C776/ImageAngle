"""关于对话框：软件名、版本、作者、开源地址。

放在工具栏最右端（F1）。内容取自单一来源，不在这里硬编码：
版本来自 ``app.__version__``，图标走 ``resources.icon_path()``（打包后指向 _MEIPASS）。

样式刻意只用主题令牌里的颜色，不写死色值 —— 深浅两套主题下都要能读，
对话框每次打开时按当前主题重建，切主题后再打开就是新配色。
"""
from __future__ import annotations

from PySide6.QtCore import QSize, QSysInfo, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)

from .. import __version__
from ..io.resources import icon_path
from . import theme

APP_NAME = 'ImageAngle'
TAGLINE = '口腔全景片牙齿近远中倾角测量'
AUTHOR = '基耶杰'
GITHUB_URL = 'https://github.com/ASH-C776/ImageAngle'
GITHUB_TEXT = 'github.com/ASH-C776/ImageAngle'
FOOTNOTE = '本地运行，不上传任何影像与测量数据。'


class AboutDialog(QDialog):
    """一个 440px 宽的信息卡，Esc 或「关闭」退出。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'关于 {APP_NAME}')
        self.setModal(True)
        self.setFixedWidth(440)
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

        # 头部：图标 + 名称 + 一句话定位 + 版本徽章
        head = QHBoxLayout()
        head.setSpacing(16)

        icon = QLabel()
        path = icon_path()
        if path:
            icon.setPixmap(QIcon(path).pixmap(QSize(64, 64)))
        icon.setFixedSize(64, 64)
        icon.setObjectName('aboutIcon')
        head.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)
        name = QLabel(APP_NAME)
        name.setObjectName('aboutName')
        tagline = QLabel(TAGLINE)
        tagline.setObjectName('aboutTagline')
        ver = QLabel(f'版本 {__version__}')
        ver.setObjectName('aboutVersion')
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setFixedHeight(22)
        ver_row = QHBoxLayout()
        ver_row.setContentsMargins(0, 4, 0, 0)
        ver_row.addWidget(ver, 0)
        ver_row.addStretch(1)

        text_col.addWidget(name)
        text_col.addWidget(tagline)
        text_col.addLayout(ver_row)
        head.addLayout(text_col, 1)
        outer.addLayout(head)

        outer.addSpacing(18)
        outer.addWidget(self._divider())
        outer.addSpacing(14)

        # 键值区：作者 / 开源地址
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)

        k_author = QLabel('作者')
        k_author.setObjectName('aboutKey')
        v_author = QLabel(AUTHOR)
        v_author.setObjectName('aboutValue')
        grid.addWidget(k_author, 0, 0)
        grid.addWidget(v_author, 0, 1)

        k_repo = QLabel('开源地址')
        k_repo.setObjectName('aboutKey')
        # 链接色只能写在 HTML 内联样式里：QLabel 富文本不吃 QSS 的 `a` 选择器，
        # 之前只写 QSS 的结果是暗色主题下链接一片深蓝、几乎看不清。
        v_repo = QLabel(
            f'<a href="{GITHUB_URL}" '
            f'style="color:{self._pal["accent"]}; text-decoration:none;">{GITHUB_TEXT}</a>')
        v_repo.setObjectName('aboutLink')
        v_repo.setOpenExternalLinks(True)      # 交给系统默认浏览器，不内嵌 WebEngine
        v_repo.setToolTip(GITHUB_URL)
        grid.addWidget(k_repo, 1, 0)
        grid.addWidget(v_repo, 1, 1)

        outer.addLayout(grid)
        outer.addSpacing(14)
        outer.addWidget(self._divider())
        outer.addSpacing(10)

        note = QLabel(FOOTNOTE)
        note.setObjectName('aboutNote')
        note.setWordWrap(True)
        outer.addWidget(note)

        outer.addSpacing(16)

        # 底部按钮：复制版本信息（报 issue 时省事）+ 关闭
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        self._btn_copy = QPushButton('复制版本信息')
        self._btn_copy.setProperty('class', 'ghost')
        self._btn_copy.clicked.connect(self._on_copy)
        btn_close = QPushButton('关闭')
        btn_close.setProperty('class', 'accent')
        btn_close.setDefault(True)
        btn_close.clicked.connect(self.accept)
        buttons.addWidget(self._btn_copy)
        buttons.addWidget(btn_close)
        outer.addLayout(buttons)

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setObjectName('aboutDivider')
        # 用 NoFrame + 背景色画 1px 线：HLine 自带描边会盖掉 QSS 的 background，
        # 结果在暗色下几乎看不见
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setFixedHeight(1)
        return line

    def _qss(self) -> str:
        p = self._pal
        return f"""
        QDialog {{ background: {p['surface']}; }}
        QLabel#aboutName {{ color: {p['text']}; font-size: 21px; font-weight: 600; }}
        QLabel#aboutTagline {{ color: {p['text2']}; font-size: 12px; }}
        QLabel#aboutVersion {{
            color: {p['accent']};
            background: {p['accent_soft']};
            border: 1px solid {p['accent_line']};
            border-radius: 9px;
            padding: 0 10px;
            font-size: 11px;
        }}
        QLabel#aboutKey {{ color: {p['text3']}; font-size: 12px; }}
        QLabel#aboutValue {{ color: {p['text']}; font-size: 13px; }}
        QLabel#aboutLink {{ font-size: 13px; }}
        QLabel#aboutNote {{ color: {p['text3']}; font-size: 11px; }}
        QFrame#aboutDivider {{ background: {p['border']}; border: none; }}
        """

    # ---- 交互 ----
    def _on_copy(self) -> None:
        win = QSysInfo.prettyProductName() or f'Windows {QSysInfo.productVersion()}'
        text = f'{APP_NAME} {__version__} · {win.strip()} · {GITHUB_URL}'
        QGuiApplication.clipboard().setText(text)
        self._btn_copy.setText('已复制')
        self._btn_copy.setEnabled(False)


def show_about(parent=None) -> None:
    """点工具栏「关于」或按 F1 时调用。"""
    AboutDialog(parent).exec()

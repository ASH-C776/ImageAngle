"""ImageAngle 设计系统：主题令牌 + 全局 QSS（暗色 / 亮色双主题）。

- 两套调色板 DARK / LIGHT，集中定义颜色、字号、字体层级。
- 模块级 C_* 变量默认跟随当前主题（set_theme 会更新它们），
  各组件在 refresh_theme() 里重新读取这些变量并重建样式，从而实时跟随。
- build_qss() 用当前调色板渲染出 QSS（一套模板，两套主题）。
- 风格对齐已定稿的「主题方案 v2」，并补齐亮色（GitHub Light 系）对应值。
"""
from __future__ import annotations

# ---------- 调色板（暗色 / 亮色）----------
# 键含义：bg 窗口底；surface 卡片；surface2 输入框/深底；border/border2 边框；
# text/text2/text3 文字三档；accent* 主色与状态；danger/warn/success 语义色；
# workspace 画布工作区底；hover/hover2 轻/重悬浮；btn* 按钮三态；grip 缩放角；
# icon/icon_active/icon_disabled 工具栏图标三态；accent_ink 激活态文字/图标色。
DARK = {
    # 配色对齐 WorkBuddy 暗色主题（IDE Night 系）：纯中性灰，无蓝色倾向。
    # 层级：窗口底 #141414 < 卡片/画布 #1f1f1f < 输入框内凹 #171717；
    # 品牌强调色用其薄荷绿 #22cba8（填充按钮上必须配深墨色文字，白字对比度不足）。
    'bg': '#141414', 'surface': '#1f1f1f', 'surface2': '#171717',
    'border': '#333333', 'border2': '#464646',
    'text': '#f2f2f2', 'text2': '#a6a6a6', 'text3': '#8a8a8a',
    'accent': '#22cba8', 'accent_h': '#4cf0ce', 'accent_p': '#1ba58a',
    'accent_soft': 'rgba(34,203,168,0.14)', 'accent_line': 'rgba(34,203,168,0.48)',
    'accent_ink': '#7cf0d8', 'accent_fg': '#062b23',
    'danger': '#f85149', 'warn': '#d29922', 'success': '#3fb950',
    'workspace': '#1f1f1f',
    'hover': 'rgba(255,255,255,0.07)', 'hover2': 'rgba(255,255,255,0.11)',
    'btn': '#262626', 'btn_hover': '#303030', 'btn_press': '#202020',
    'btn_disabled_bg': '#1a1a1a', 'btn_disabled_border': '#262626', 'btn_disabled_text': '#5c5c5c',
    'grip': 'transparent',
    # 工具栏文字单独一档：用 text2(#a6a6a6) 在 #141414 上发灰、笔画细时发虚，
    # 而直接用 text(#f2f2f2) 又和选中态的薄荷绿抢视线，取中间值。
    'tool_text': '#dcdcdc', 'tool_text_disabled': '#6f6f6f',
    'icon': '#c8c8c8', 'icon_active': '#7cf0d8', 'icon_disabled': '#6f6f6f',
}

LIGHT = {
    'bg': '#ffffff', 'surface': '#f6f8fa', 'surface2': '#eaeef2',
    'border': '#d0d7de', 'border2': '#afb8c1',
    'text': '#1f2328', 'text2': '#57606a', 'text3': '#8c959f',
    'accent': '#0969da', 'accent_h': '#218bff', 'accent_p': '#0860ca',
    'accent_soft': 'rgba(9,105,218,0.12)', 'accent_line': 'rgba(9,105,218,0.45)',
    'accent_ink': '#0969da', 'accent_fg': '#ffffff',
    'danger': '#cf222e', 'warn': '#9a6700', 'success': '#1a7f37',
    'workspace': '#eaeef2',
    'hover': 'rgba(31,35,40,0.04)', 'hover2': 'rgba(31,35,40,0.08)',
    'btn': '#f6f8fa', 'btn_hover': '#eaeef2', 'btn_press': '#d8dee4',
    'btn_disabled_bg': '#f6f8fa', 'btn_disabled_border': '#d0d7de', 'btn_disabled_text': '#8c959f',
    'grip': 'transparent',
    'tool_text': '#2f353b', 'tool_text_disabled': '#9aa3ad',
    'icon': '#424a53', 'icon_active': '#0969da', 'icon_disabled': '#b0b8c1',
}

PALETTES = {'dark': DARK, 'light': LIGHT}
THEME_NAME = 'dark'

# ---------- 模块级 C_* 变量（默认跟随 THEME_NAME）----------
C_BG = DARK['bg']
C_SURFACE = DARK['surface']
C_SURFACE2 = DARK['surface2']
C_BORDER = DARK['border']
C_BORDER2 = DARK['border2']
C_TEXT = DARK['text']
C_TEXT2 = DARK['text2']
C_TEXT3 = DARK['text3']
C_ACCENT = DARK['accent']
C_ACCENT_H = DARK['accent_h']
C_ACCENT_P = DARK['accent_p']
C_ACCENT_SOFT = DARK['accent_soft']
C_ACCENT_LINE = DARK['accent_line']
C_ACCENT_INK = DARK['accent_ink']
C_ACCENT_FG = DARK['accent_fg']   # 填充式主按钮上的前景色（暗色薄荷底用深墨，亮色蓝底用白）
C_DANGER = DARK['danger']
C_WARN = DARK['warn']
C_SUCCESS = DARK['success']
C_WORKSPACE = DARK['workspace']
C_HOVER = DARK['hover']
C_HOVER2 = DARK['hover2']
C_BTN = DARK['btn']
C_BTN_HOVER = DARK['btn_hover']
C_BTN_PRESS = DARK['btn_press']
C_BTN_DISABLED_BG = DARK['btn_disabled_bg']
C_BTN_DISABLED_BORDER = DARK['btn_disabled_border']
C_BTN_DISABLED_TEXT = DARK['btn_disabled_text']
C_TOOL_TEXT = DARK['tool_text']
C_TOOL_TEXT_DISABLED = DARK['tool_text_disabled']
C_GRIP = DARK['grip']

# ---------- 字号层级（px，相对可缩放）----------
F_CAP = 11      # caption / 标签
F_SM = 12       # 小字
F_BASE = 13     # 正文基准
F_MD = 14       # 中
F_LG = 16       # 大
F_XL = 24       # 卡片角度
F_XXL = 32      # 大数字

FONT_STACK = '"Segoe UI", "Microsoft YaHei UI", system-ui, -apple-system, sans-serif'

# ---------- QSS 模板（占位符 $xxx 由 build_qss 替换）----------
_QSS_TEMPLATE = """
/* ===== 全局 ===== */
QMainWindow, QDialog, QWidget {
  background-color: $bg;
  color: $text;
  font-family: "Segoe UI", "Microsoft YaHei UI", system-ui, -apple-system, sans-serif;
  font-size: 13px;
}

/* ===== 工具栏（无边框、透明，嵌入自定义标题栏下方） ===== */
QToolBar {
  background: transparent;
  border: none;   /* 底部分割线由 TitleBar 统一整行绘制，避免只画到工具栏宽度就断掉 */
  spacing: 2px;
  padding: 7px 12px;
}
QToolBar QToolButton {
  background: transparent;
  color: $tool_text;
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 5px 10px;
  font-size: 13px;
  spacing: 6px;
}
QToolBar QToolButton:hover {
  background: $hover;
  color: $text;
}
QToolBar QToolButton:pressed { background: $hover2; color: $text; }
QToolBar QToolButton:disabled { color: $tool_text_disabled; }
QToolBar QToolButton:checked {
  background: $accent_soft;
  color: $accent_ink;
  border: 1px solid $accent_line;
}
/* 主行动按钮（导出 CSV） */
QToolButton#exportBtn {
  background: $accent;
  color: $accent_fg;
  border: 1px solid $accent;
  /* 左侧留白：紧邻的「面板」开关在勾选态也是绿色底，两个绿块贴在一起会糊成一片 */
  margin-left: 10px;
}
QToolButton#exportBtn:hover { background: $accent_h; border-color: $accent_h; }
QToolButton#exportBtn:pressed { background: $accent_p; border-color: $accent_p; }
/* 没有可导出的记录时按钮会置灰：薄荷绿实心底若不跟随禁用态，看起来仍然可点 */
QToolButton#exportBtn:disabled {
  background: $surface2;
  color: $text3;
  border: 1px solid $border;
}
QToolBar::separator {
  background: $border;
  width: 1px;
  margin: 6px 8px;
}

/* ===== 状态栏 ===== */
QStatusBar {
  background: $bg;
  color: $text2;
  border-top: 1px solid $border;
  padding: 5px 14px;
  font-size: 12px;
}
QStatusBar::item { border: none; }
QSizeGrip { background: $grip; width: 14px; height: 14px; }

/* ===== 输入框 ===== */
QLineEdit {
  background: $surface2;
  border: 1px solid $border;
  border-radius: 6px;
  padding: 6px 10px;
  color: $text;
  font-size: 13px;
}
QLineEdit:focus {
  border-color: $accent;
  outline: none;
}
QLineEdit::placeholder { color: $text3; }

/* ===== 按钮 ===== */
QPushButton {
  background: $btn;
  color: $text;
  border: 1px solid $border;
  border-radius: 7px;
  padding: 6px 14px;
  font-size: 13px;
}
QPushButton:hover { background: $btn_hover; border-color: $border2; }
QPushButton:pressed { background: $btn_press; }
QPushButton:disabled { color: $btn_disabled_text; background: $btn_disabled_bg; border-color: $btn_disabled_border; }

/* 主行动按钮（如导出 CSV） */
QPushButton.accent {
  background: $accent;
  color: $accent_fg;
  border: 1px solid $accent;
}
QPushButton.accent:hover { background: $accent_h; border-color: $accent_h; }
QPushButton.accent:pressed { background: $accent_p; }

/* ===== 提示 ===== */
QToolTip {
  background: $surface;
  color: $text;
  border: 1px solid $border;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
}

/* ===== 滚动条 ===== */
QScrollBar:vertical {
  background: transparent;
  width: 10px;
  margin: 2px;
  border: none;
}
QScrollBar::handle:vertical {
  background: $border;
  border-radius: 5px;
  min-height: 40px;
}
QScrollBar::handle:vertical:hover { background: $border2; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; background: transparent; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal {
  background: transparent;
  height: 10px;
  margin: 2px;
  border: none;
}
QScrollBar::handle:horizontal {
  background: $border;
  border-radius: 5px;
  min-width: 40px;
}
QScrollBar::handle:horizontal:hover { background: $border2; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; background: transparent; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QScrollArea { background: transparent; border: none; }

/* ===== 通用卡片 ===== */
QFrame.card {
  background: $surface;
  border: 1px solid $border;
  border-radius: 10px;
}

/* ===== 右键菜单 ===== */
QMenu {
  background: $surface;
  border: 1px solid $border;
  border-radius: 8px;
  padding: 6px;
  color: $text;
  font-size: 13px;
}
QMenu::item {
  padding: 7px 24px 7px 12px;
  border-radius: 6px;
}
QMenu::item:selected { background: $hover2; }
QMenu::item:disabled { color: $text3; }
QMenu::separator {
  height: 1px;
  background: $border;
  margin: 5px 8px;
}

/* ===== 列表（图片列表弹窗）===== */
QListWidget {
  background: $surface2;
  border: 1px solid $border;
  border-radius: 8px;
  padding: 4px;
  outline: none;
  color: $text;
  font-size: 13px;
}
QListWidget::item {
  padding: 7px 9px;
  border-radius: 6px;
}
QListWidget::item:hover { background: $hover; }
QListWidget::item:selected { background: $accent_soft; color: $accent_ink; }
"""


def build_qss() -> str:
    """按当前主题渲染 QSS。

    ⚠ 必须按 key 长度倒序替换：`$accent` 是 `$accent_soft` / `$accent_fg` 的**前缀**，
    若先替换 `$accent`，后者会变成 `#22cba8_soft` 这种非法值，Qt 静默丢弃该声明
    （表现是按钮文字仍是默认白色、勾选态底色失效）。
    """
    p = PALETTES[THEME_NAME]
    qss = _QSS_TEMPLATE
    for key in sorted(p, key=len, reverse=True):
        qss = qss.replace('$' + key, p[key])
    return qss


def set_theme(name: str) -> None:
    """切换主题，更新所有模块级令牌 + 图标颜色常量。

    name: 'dark' | 'light'。
    调用后各组件需调用自身的 refresh_theme() 重建样式（或直接重建内容）。
    """
    global THEME_NAME
    global C_BG, C_SURFACE, C_SURFACE2, C_BORDER, C_BORDER2
    global C_TEXT, C_TEXT2, C_TEXT3
    global C_ACCENT, C_ACCENT_H, C_ACCENT_P, C_ACCENT_SOFT, C_ACCENT_LINE, C_ACCENT_INK, C_ACCENT_FG
    global C_DANGER, C_WARN, C_SUCCESS, C_WORKSPACE
    global C_HOVER, C_HOVER2
    global C_BTN, C_BTN_HOVER, C_BTN_PRESS, C_BTN_DISABLED_BG, C_BTN_DISABLED_BORDER, C_BTN_DISABLED_TEXT
    global C_TOOL_TEXT, C_TOOL_TEXT_DISABLED
    global C_GRIP
    p = PALETTES[name]
    THEME_NAME = name
    C_BG = p['bg']; C_SURFACE = p['surface']; C_SURFACE2 = p['surface2']
    C_BORDER = p['border']; C_BORDER2 = p['border2']
    C_TEXT = p['text']; C_TEXT2 = p['text2']; C_TEXT3 = p['text3']
    C_ACCENT = p['accent']; C_ACCENT_H = p['accent_h']; C_ACCENT_P = p['accent_p']
    C_ACCENT_SOFT = p['accent_soft']; C_ACCENT_LINE = p['accent_line']
    C_ACCENT_INK = p['accent_ink']; C_ACCENT_FG = p['accent_fg']
    C_DANGER = p['danger']; C_WARN = p['warn']; C_SUCCESS = p['success']
    C_WORKSPACE = p['workspace']
    C_HOVER = p['hover']; C_HOVER2 = p['hover2']
    C_BTN = p['btn']; C_BTN_HOVER = p['btn_hover']; C_BTN_PRESS = p['btn_press']
    C_BTN_DISABLED_BG = p['btn_disabled_bg']; C_BTN_DISABLED_BORDER = p['btn_disabled_border']
    C_BTN_DISABLED_TEXT = p['btn_disabled_text']
    C_TOOL_TEXT = p['tool_text']; C_TOOL_TEXT_DISABLED = p['tool_text_disabled']
    C_GRIP = p['grip']

    # 同步图标颜色到 icons 模块（get_icon 使用模块级常量）
    try:
        from . import icons
        icons.ICON_COLOR = p['icon']
        icons.ICON_COLOR_ACTIVE = p['icon_active']
        icons.ICON_COLOR_DISABLED = p['icon_disabled']
    except Exception:
        pass


def is_dark() -> bool:
    return THEME_NAME == 'dark'

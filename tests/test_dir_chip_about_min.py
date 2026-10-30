"""回归：方向胶囊（近中 / 远中）与「使用说明」页（原关于页）。

两件事各有历史：
1) 方向列原本是 11px 纯灰文字，扫视时几乎分不出近中还是远中。
   改为色块胶囊后，靠「形状 + 底色 + 文字色」三重差异区分，
   这里锁住两点：两者颜色不同、控件尺寸固定（保证列表和当前测量对齐）。
2) 关于页一度堆了定位语、开源声明、下载区说明、复制版本按钮，
   后来精简成一屏六项，现在再改为「名称 + 版本（本软件免费，已开源）+ 两个折叠栏」。
   这里锁住：该有的在、多余的没了、折叠栏默认收起、正文要点与重点色还在。
"""
from PySide6.QtWidgets import QLabel

from app import __version__
from app.model.session import Tooth
from app.ui import about, theme
from app.ui.about import HelpDialog
from app.ui.result_panel import DIR_CHIP_H, DIR_CHIP_W, ResultPanel, make_dir_chip


def test_dir_chips_use_different_colors():
    prev = theme.THEME_NAME
    theme.set_theme('dark')
    try:
        mesial = make_dir_chip('近中')
        distal = make_dir_chip('远中')
        assert mesial.text() == '近中' and distal.text() == '远中'
        assert theme.C_DIR_MESIAL != theme.C_DIR_DISTAL
        # 胶囊必须有底色，否则和原来的纯文字没区别
        assert theme.C_DIR_MESIAL_BG in mesial.styleSheet()
        assert theme.C_DIR_DISTAL_BG in distal.styleSheet()
        assert theme.C_DIR_MESIAL in mesial.styleSheet()
        assert theme.C_DIR_DISTAL in distal.styleSheet()
    finally:
        theme.set_theme(prev)


def test_dir_chip_fixed_size_and_blank_state():
    chip = make_dir_chip('')
    assert chip.text() == '—'
    assert chip.width() == DIR_CHIP_W and chip.height() == DIR_CHIP_H
    # 空方向走中性灰，不能借用近中/远中的语义色
    assert theme.C_DIR_MESIAL not in chip.styleSheet()
    assert theme.C_DIR_DISTAL not in chip.styleSheet()


def test_rows_show_dir_chips(qapp):
    panel = ResultPanel()
    panel.refresh_list([Tooth(seq=1, fdi='16', angle_deg=4.0, direction='近中'),
                        Tooth(seq=2, fdi='17', angle_deg=-6.0, direction='远中')],
                       None)
    qapp.processEvents()
    texts = []
    for seq in (1, 2):
        row = panel._row_widgets[seq]
        chips = [w for w in row.findChildren(QLabel)
                 if w.text() in ('近中', '远中')
                 and w.width() == DIR_CHIP_W and w.height() == DIR_CHIP_H]
        assert len(chips) == 1, f'第 {seq} 行应恰好有一个方向胶囊'
        texts.append(chips[0].text())
    assert texts == ['近中', '远中']


def test_help_header_shows_name_version_and_free_note(qapp):
    """头部只留三样：名称、版本、版本后面那句「本软件免费，已开源」。"""
    dlg = HelpDialog()
    try:
        joined = '\n'.join(w.text() for w in dlg.findChildren(QLabel))
        assert about.APP_NAME in joined
        assert f'版本 {__version__}' in joined
        assert about.FREE_NOTE in joined
        # 早先被删掉的定位语 / 简介不能又跑回来
        for gone in ('全景片角度测量小工具', '口腔全景片牙齿近远中倾角测量'):
            assert gone not in joined, f'「{gone}」已按要求移除'
    finally:
        dlg.close()


def test_help_folds_collapsed_until_clicked(qapp):
    """两个折叠栏默认收起，点标题才展开（用 isVisibleTo，不受窗口是否显示影响）。"""
    dlg = HelpDialog()
    try:
        assert not dlg.fold_donate.body.isVisibleTo(dlg)
        assert not dlg.fold_help.body.isVisibleTo(dlg)
        dlg.fold_donate.head.clicked.emit()          # 走真实的「点标题」路径
        assert dlg.fold_donate.body.isVisibleTo(dlg)
        assert not dlg.fold_help.body.isVisibleTo(dlg)
        dlg.fold_help.toggle()
        assert dlg.fold_help.body.isVisibleTo(dlg)
        dlg.fold_help.toggle()                        # 再点一次收起
        assert not dlg.fold_help.body.isVisibleTo(dlg)
    finally:
        dlg.close()


def test_help_text_keeps_key_points_with_colors(qapp):
    """正文只留要点：点的顺序、正负号、阈值、参考线前提；重点靠颜色区分。"""
    dlg = HelpDialog()
    try:
        lab = [w for w in dlg.findChildren(QLabel)
               if w.objectName() == 'helpText'][0]
        html = lab.text()
        for must in ('先点牙根尖', '再点牙冠中点', '顺序点反', '近中为正', '30°'):
            assert must in html, f'说明里应保留「{must}」'
        # 重点色：顺序用 accent、点反会反号用 danger
        assert dlg._pal['accent'] in html and dlg._pal['danger'] in html
    finally:
        dlg.close()


def test_dialog_size_restores_after_collapse(qapp):
    """展开再折叠，窗口必须缩回原高度。

    adjustSize() 只在 sizeHint 小于「当前」尺寸时收缩 —— 展开一次后窗口
    会永久停在展开时的高度，顶部标题行被垂直居中拉开。这里锁住回弹。
    """
    dlg = HelpDialog()
    try:
        dlg.show()
        qapp.processEvents()
        dlg._fit_now()
        collapsed = dlg.height()

        dlg.fold_donate.head.clicked.emit()      # 走真实的点击信号
        qapp.processEvents(); qapp.processEvents()
        assert dlg.height() > collapsed, '展开后应长高'
        assert dlg.width() == HelpDialog.W

        dlg.fold_donate.head.clicked.emit()
        qapp.processEvents(); qapp.processEvents()
        assert dlg.height() == collapsed, '折叠后应缩回原高度'
        assert dlg.width() == HelpDialog.W
    finally:
        dlg.close()


def test_no_close_button_and_keyboard_exit_works(qapp):
    """页内不放「关闭」按钮，但 Esc / 回车都必须还能退。

    标题栏自带 ×，底部再摆一个「关闭」只是白占高度；不过按钮同时也是 Qt 的
    「默认按钮」，删掉后回车就没人接了 —— 所以 keyPressEvent 里补一手。
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QPushButton

    dlg = HelpDialog()
    try:
        assert dlg.findChildren(QPushButton) == [], '使用说明页不应再有任何按钮'

        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            dlg.show()
            qapp.processEvents()
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
            dlg.keyPressEvent(ev)
            assert not dlg.isVisible(), f'{key} 应能关闭对话框'
    finally:
        dlg.close()


def test_donate_fold_holds_qr_and_repos(qapp):
    """打赏折叠栏里才是二维码、作者和两个仓库。"""
    dlg = HelpDialog()
    try:
        joined = '\n'.join(w.text() for w in dlg.findChildren(QLabel))
        # 折叠栏标题是自绘文字（不是 QLabel），单独取
        assert dlg.fold_donate.head.title() == about.DONATE_TITLE
        assert dlg.fold_help.head.title() == about.HELP_TITLE
        assert about.AUTHOR in joined
        assert about.GITHUB_URL in joined and about.GITEE_URL in joined
        for _, caption in about.DONATE_QR:
            assert caption in joined, f'收款码说明「{caption}」应在打赏栏'
    finally:
        dlg.close()

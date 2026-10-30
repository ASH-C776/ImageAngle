"""回归：测量记录的四列按权重均分，行尾删除按钮是自绘控件。

历史问题：
1) 四列各自写死宽度（26/40/66/54），面板拉宽时宽度全被右侧空白吃掉 ——
   编号和牙号挤在左边一小块。现在按 COL_WEIGHTS 分权重，四列一起变宽，
   表头与数据行必须用同一组权重，否则列头错位。
2) 删除按钮原来是 `QPushButton('×')`，字符 × 的重心与笔画随字体变，
   和 0.5px 描边的 UI 不是一套质感。改成自绘 DeleteButton。
"""
from PySide6.QtWidgets import QLabel

from app.model.session import Tooth
from app.ui.result_panel import (COL_WEIGHTS, DeleteButton, ResultPanel,
                                 make_dir_chip)


def _panel(qapp, width: int) -> ResultPanel:
    panel = ResultPanel()
    panel.resize(width, 420)
    panel.refresh_list([Tooth(seq=1, fdi='16', angle_deg=12.4, direction='近中')],
                       None)
    panel.show()
    qapp.processEvents()
    return panel


def test_columns_stretch_with_panel_width(qapp):
    """列宽必须跟着面板变 —— 固定宽度就是这次要修的病根。"""
    narrow = _panel(qapp, 340)
    wide = _panel(qapp, 440)
    try:
        for i in range(4):
            w_narrow = narrow._head_cells[i][0].width()
            w_wide = wide._head_cells[i][0].width()
            assert w_wide > w_narrow, f'第 {i} 列没有随面板变宽（{w_narrow} → {w_wide}）'
    finally:
        narrow.close()
        wide.close()


def test_head_and_row_columns_align(qapp):
    panel = _panel(qapp, 380)
    try:
        lay = panel._row_widgets[1].layout()
        row_widgets = [lay.itemAt(i).widget() for i in range(4)]
        for i, (head_lbl, _align) in enumerate(panel._head_cells):
            assert abs(head_lbl.geometry().x() - row_widgets[i].geometry().x()) <= 1, (
                f'第 {i} 列表头 x={head_lbl.geometry().x()} '
                f'与数据行 x={row_widgets[i].geometry().x()} 错位')
    finally:
        panel.close()


def test_column_weights_are_ordered_and_positive():
    assert len(COL_WEIGHTS) == 4
    assert all(w > 0 for w in COL_WEIGHTS)
    # 角度列最宽（带 ± 号与小数点），方向列次之（放得下 42px 胶囊）
    assert COL_WEIGHTS[2] > COL_WEIGHTS[3] > COL_WEIGHTS[0]


def test_row_delete_button_is_painted_widget(qapp):
    panel = _panel(qapp, 380)
    try:
        lay = panel._row_widgets[1].layout()
        btn = lay.itemAt(lay.count() - 1).widget()
        assert isinstance(btn, DeleteButton)
        assert isinstance(btn, QLabel) is False
        assert btn.text() == '', 'delete 按钮不应用字符 × 绘制'
        assert btn.toolTip() == '删除该条'
    finally:
        panel.close()


def test_delete_button_emits_row_delete(qapp):
    panel = _panel(qapp, 380)
    seen = []
    panel.rowDeleteClicked.connect(seen.append)
    try:
        lay = panel._row_widgets[1].layout()
        lay.itemAt(lay.count() - 1).widget().click()
        qapp.processEvents()
        assert seen == [1]
    finally:
        panel.close()


def test_dir_chip_fits_in_its_column(qapp):
    """方向列再窄也要放得下 42px 胶囊，否则会被裁掉一截。"""
    panel = _panel(qapp, 340)
    try:
        chip = make_dir_chip('近中')
        assert chip.width() <= panel._head_cells[3][0].width()
    finally:
        panel.close()

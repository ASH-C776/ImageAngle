"""回归：面板刷新时不得产生「无父的顶层小窗口」。

历史 bug：result_panel 删旧行/旧字段时用了 `setParent(None)`，这会把手里的
QFrame/QLabel 变成**无父顶层窗口**。它们在 `deleteLater` 真正执行前会以无边框
小方块的形式真的上屏 —— 表现就是点「清空」时画布前闪出几个框。
"""
from PySide6.QtWidgets import QApplication

from app.model.session import Tooth
from app.ui.result_panel import ResultPanel


def _baseline() -> set:
    """测试开始时已存在的顶层窗口（上一个用例可能留下未销毁的面板）。"""
    app = QApplication.instance()
    return {id(w) for w in app.topLevelWidgets()}


def _stray_toplevels(panel, base: set) -> list:
    app = QApplication.instance()
    out = []
    for w in app.topLevelWidgets():
        if w is None or not w.isWidgetType() or not w.isVisible():
            continue
        if w is panel or id(w) in base:
            continue
        out.append((type(w).__name__, w.geometry().getRect()))
    return out


def _teeth(n: int):
    return [Tooth(seq=i + 1, fdi=str(11 + i), angle_deg=1.5 * (i + 1),
                  direction='近中', confidence='高') for i in range(n)]


def test_refresh_list_leaves_no_orphan_toplevel(qapp):
    panel = ResultPanel()
    panel.show()
    qapp.processEvents()
    base = _baseline()

    panel.refresh_list(_teeth(4), 2)
    qapp.processEvents()
    assert _stray_toplevels(panel, base) == [], '列表重建后出现了游离顶层窗口'

    # 再刷一次（内容变化，会走「删除旧行」分支）
    panel.refresh_list(_teeth(2), None)
    qapp.processEvents()
    assert _stray_toplevels(panel, base) == [], '删除旧行时产生了游离顶层窗口'

    # 清空到 0 行
    panel.refresh_list([], None)
    qapp.processEvents()
    assert _stray_toplevels(panel, base) == [], '清空列表时产生了游离顶层窗口'


def test_render_current_leaves_no_orphan_toplevel(qapp):
    panel = ResultPanel()
    panel.show()
    qapp.processEvents()
    base = _baseline()

    for tooth in _teeth(3):
        panel.show_result(tooth)
        qapp.processEvents()
        assert _stray_toplevels(panel, base) == [], '重建当前测量块时出现了游离顶层窗口'

    panel.show_blank('')
    qapp.processEvents()
    assert _stray_toplevels(panel, base) == [], '切回空态时出现了游离顶层窗口'


def test_refresh_skips_when_content_unchanged(qapp):
    panel = ResultPanel()
    panel.show()
    teeth = _teeth(3)
    panel.refresh_list(teeth, 1)
    qapp.processEvents()
    first_row = panel._row_widgets[1]

    # 内容完全一致 → 不应重建（行对象还是同一个）
    panel.refresh_list(teeth, 1)
    qapp.processEvents()
    assert panel._row_widgets[1] is first_row

    # 选中项变化 → 必须重建
    panel.refresh_list(teeth, 2)
    qapp.processEvents()
    assert panel._row_widgets[1] is not first_row

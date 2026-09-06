"""SortableTable：支持表头点击三态排序（升序 → 降序 → 默认）的 QTableWidget。

为什么不用 Qt 内置排序：
    QTableWidget.sortItems() 只交换 QTableWidgetItem，**不会移动 setCellWidget
    放置的自定义控件**（tag/双行/操作按钮等），会造成行错位。因此本项目采用
    "页面层对数据重排 + 重建行" 方案：本组件只负责表头点击状态机、箭头指示与
    sort_changed 信号，页面收到信号后对数据排序并重建表格行。

排序循环（点击同一列表头）：
    第一次：升序 → 第二次：降序 → 第三次：恢复默认（无箭头）→ 再点：升序…
点击新列：直接升序。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHeaderView, QTableWidget

from app.ui.widgets.base_table import fill_first_column

_ORDER_CYCLE = {"asc": "desc", "desc": None, None: "asc"}


def sort_rows(rows: list[dict], key_fn, order: str | None) -> list[dict]:
    """对行数据按 key_fn 排序；order=None 恢复原始顺序。

    健壮性（防止 Qt 槽内异常导致进程崩溃）：
        - key_fn 对任意行抛异常 → 该行视为空值，排到最后；
        - 空值（None/空串/NaN）无论升序降序都排到最后；
        - 数值列统一转 float、文本列统一转 str 后比较，避免同列
          int/str 混合或"非数字字符串"（如历史脏数据 balance='abc'）触发 TypeError。
    """
    if order is None or not rows:
        return list(rows)

    def extract(r):
        try:
            v = key_fn(r)
        except Exception:
            return None
        if v is None or (isinstance(v, str) and v == "") or (isinstance(v, float) and v != v):
            return None
        return v

    prepared = [(r, extract(r)) for r in rows]
    nonempty = [(r, k) for r, k in prepared if k is not None]
    empty = [r for r, k in prepared if k is None]

    # 数值列识别：非空键都能转 float 时按数值排序（数字字符串一并转）
    numeric = True
    for _, k in nonempty:
        if isinstance(k, bool):
            continue
        if not isinstance(k, (int, float)):
            try:
                float(k)
            except (TypeError, ValueError):
                numeric = False
                break

    if numeric:
        nonempty.sort(key=lambda item: float(item[1]), reverse=(order == "desc"))
    else:
        nonempty.sort(key=lambda item: str(item[1]), reverse=(order == "desc"))
    return [r for r, _ in nonempty] + empty


class SortableTable(QTableWidget):
    """可点击表头三态排序的表格。"""

    sort_changed = Signal(int, object)  # (col, order): order ∈ "asc"/"desc"/None

    def __init__(self, rows: int = 0, cols: int = 0, parent=None):
        super().__init__(rows, cols, parent)
        self.setSortingEnabled(False)  # 关闭内置排序（不移动 cellWidget）
        self._sort_col: int | None = None
        self._sort_order: str | None = None
        self._sortable_cols: set[int] = set()
        self._rebuild_fn = None        # 由 set_rebuild_fn() 注册
        self._sort_pending = False     # 合批标志：高频连点只重建一次
        self._col0_user_resized = False  # 用户手动拖过第 0 列后，停止自动补宽
        self.horizontalHeader().sectionClicked.connect(self._on_section_clicked)
        self.horizontalHeader().sectionResized.connect(self._on_section_resized)

    def _on_section_resized(self, col: int, _old: int, _new: int) -> None:
        """列宽变化：区分"用户拖动"与"程序化补宽"（fill_first_column 置标志）。

        用户拖第 0 列 → 记录并停止后续自动补宽；拖其他列 → 第 0 列重新吃掉
        剩余宽度（等价于原 Stretch 模式的联动）。
        """
        if col == 0:
            if not getattr(self, "_filling_col0", False):
                self._col0_user_resized = True
        elif not self._col0_user_resized:
            QTimer.singleShot(0, lambda: fill_first_column(self))

    def resizeEvent(self, event) -> None:
        """表格尺寸变化（窗口缩放/滚动条出现）后让第 0 列继续吃掉剩余宽度。"""
        super().resizeEvent(event)
        if not self._col0_user_resized:
            QTimer.singleShot(0, lambda: fill_first_column(self))

    # ------------------------------------------------------------------
    def set_rebuild_fn(self, fn) -> None:
        """注册「重建表格行」的回调（通常是页面的 _populate_table）。

        表头点击后由本组件统一延迟到事件循环执行，页面无需各自实现
        _on_sort / _flush_sort（这四个方法原本在 4 个页面里一字不差地各复制一份）。
        """
        self._rebuild_fn = fn

    def set_sortable_cols(self, cols) -> None:
        """设置允许排序的列号集合（操作列等不放进来）。"""
        self._sortable_cols = set(cols)

    def current_sort_col(self) -> int | None:
        return self._sort_col

    def current_sort_order(self) -> str | None:
        return self._sort_order

    def _on_section_clicked(self, col: int) -> None:
        """表头点击：三态循环。

        信号栈内只做纯 Python 状态更新（绝不在 sectionClicked/mousePressEvent
        处理栈内调用 setSortIndicatorShown/setSortIndicator 等 Qt 表头操作——
        第三次点击恢复默认时 setSortIndicatorShown(False) 会触发 header 重布局，
        在鼠标事件栈内执行可导致 Qt 内部状态冲突而 C++ 崩溃）。
        表头指示更新与表格重建都延迟到事件循环执行。
        """
        try:
            if col not in self._sortable_cols:
                return
            if self._sort_col != col:
                self._sort_col = col
                self._sort_order = "asc"
            else:
                self._sort_order = _ORDER_CYCLE[self._sort_order]
            QTimer.singleShot(0, self._apply_indicator)
            self.sort_changed.emit(self._sort_col, self._sort_order)
            self._schedule_rebuild()
        except Exception:
            # 任何异常（脏数据/未知列等）都回退默认排序，保证不崩溃
            self._sort_col = None
            self._sort_order = None
            QTimer.singleShot(0, self._apply_indicator)
            self.sort_changed.emit(None, None)
            self._schedule_rebuild()

    def _apply_indicator(self) -> None:
        """事件循环中更新表头排序箭头（不在信号栈内调用）。"""
        try:
            self._update_indicator()
        except Exception:
            pass

    def _update_indicator(self) -> None:
        """箭头指示：升序 ▲ / 降序 ▼ / 默认无箭头。"""
        header = self.horizontalHeader()
        if self._sort_order is None:
            header.setSortIndicatorShown(False)
        else:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(
                self._sort_col,
                Qt.AscendingOrder if self._sort_order == "asc" else Qt.DescendingOrder,
            )

    def _schedule_rebuild(self) -> None:
        """排一次延迟重建（合批：连续点击表头时只执行最后一次）。"""
        self._sort_pending = True
        QTimer.singleShot(0, self._flush_rebuild)

    def _flush_rebuild(self) -> None:
        """在事件循环中执行表格重建。

        绝不在 sectionClicked 信号栈内同步重建表格——Qt 此时正遍历 header/selection
        内部状态，同步重建会造成内部状态冲突而 C++ 崩溃。
        """
        if not self._sort_pending:
            return
        self._sort_pending = False
        if self._rebuild_fn is None:
            return
        try:
            self._rebuild_fn()
        except Exception:
            # 脏数据等异常时回退默认排序，保证点击表头不崩溃
            self.clear_sort()

    def clear_sort(self) -> None:
        """恢复默认（无排序）状态。"""
        self._sort_col = None
        self._sort_order = None
        self._update_indicator()

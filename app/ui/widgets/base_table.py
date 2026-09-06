"""BaseTable：全局表格布局规范 + 单元格辅助（UI 设计规范 3.5 / v1.3 强约束）。

列策略（自适应版）：
    1. 第 0 列（名称/债权人）Stretch 吸收剩余宽度，消除表格内部右侧空白；
    2. 其余数据列由 autofit_columns() 在填充数据后按内容适配（Interactive 仍可手调），
       比例余量对抗 fractional-DPI 字形 hinting 偏差，任何字体/DPI 下不截断；
    3. 过窄出水平滚动条（ScrollBarAsNeeded + ScrollPerPixel）而非裁剪。

视觉（v2.0 规范 3.5）：
    表头 13px 灰 Medium、行高默认 52（双行）或 44（单行）、金额右对齐、空值 "—"。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.ui import styles, theme


def setup_table(table: QTableWidget, row_height: int = 52) -> None:
    """按全局规范初始化一个表格。

    row_height: 行高（双行单元格 52 / 单行 44）。
    列宽策略（内容自适应）：
        - 第 0 列 Interactive（用户可拖动调宽），数据填充后由 fill_first_column()
          吃掉剩余宽度，模拟 Stretch 的观感——Stretch 模式下用户无法拖动，
          长名称/备注显示不全时没办法手动调宽；
        - 其余数据列 Interactive，数据填充后由 autofit_columns() 按内容适配；
        - 过窄出水平滚动条（ScrollBarAsNeeded + ScrollPerPixel）而非裁剪。
    """
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)

    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Interactive)
    header.setSectionResizeMode(0, QHeaderView.Interactive)
    header.setStretchLastSection(False)

    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    header.setMinimumSectionSize(60)

    table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.verticalHeader().setDefaultSectionSize(row_height)


def fill_first_column(table: QTableWidget) -> None:
    """把第 0 列加宽到吃掉表格剩余宽度（Interactive 模式下的手动 Stretch）。

    用户手动拖动过第 0 列后（SortableTable 记录状态）不再自动调整，尊重用户
    设定的宽度；_filling_col0 标志用于让 sectionResized 回调区分"程序化加宽"
    与"用户拖动"，避免自动补宽被误判成用户操作。
    """
    if getattr(table, "_col0_user_resized", False):
        return
    header = table.horizontalHeader()
    if table.columnCount() == 0:
        return
    others = sum(header.sectionSize(c) for c in range(1, table.columnCount()))
    leftover = table.viewport().width() - others - 2  # 余量防抖，避免恰好触发横向滚动条
    if leftover >= header.minimumSectionSize():
        table._filling_col0 = True
        try:
            header.resizeSection(0, leftover)
        finally:
            table._filling_col0 = False


def autofit_columns(table: QTableWidget) -> None:
    """按内容自适应全部数据列宽度（第 0 列 Stretch 跳过）。

        列宽 = max(表头文字,
                  文字项按 QSS 字号(14px)实测 ×1.12 + 6,
                  单元格控件 sizeHint ×1.08 + 2)
             + QSS ::item 左右内边距

    比例余量对抗 fractional-DPI 下字形 hinting 使实际渲染略宽于 metrics 的偏差
    （每个字形最多 ±1 物理像素，CJK 长文本累计可达 8%~10%）；
    内边距补偿是因为布局会把这笔从单元格内容可用宽度中扣掉。
    须在数据填充完成后调用；排序重建走同一 populate，无需额外处理。
    """
    header = table.horizontalHeader()
    pad = styles.TABLE_ITEM_PAD_X * 2 + 4
    f_base = QFont(table.font())
    f_base.setPixelSize(theme.FS_BODY)
    for col in range(1, table.columnCount()):
        if header.sectionResizeMode(col) == QHeaderView.Stretch:
            continue
        w = 0
        hdr = table.horizontalHeaderItem(col)
        if hdr:
            w = header.fontMetrics().horizontalAdvance(hdr.text())
        for r in range(table.rowCount()):
            item = table.item(r, col)
            if item is not None and item.text():
                f = QFont(f_base)
                if item.font().bold():
                    f.setBold(True)
                tw = QFontMetrics(f).horizontalAdvance(item.text())
                w = max(w, int(tw * 1.12) + 6)
            widget = table.cellWidget(r, col)
            if widget is not None:
                w = max(w, int(widget.sizeHint().width() * 1.08) + 2)
        if w:
            table.setColumnWidth(col, w + pad)
    # 第 0 列（名称列）吃掉剩余宽度，保持原 Stretch 模式的观感
    fill_first_column(table)
    # 滚动条按需出现/消失会再改一次视口宽，下一轮事件循环再校准一次
    QTimer.singleShot(0, lambda: fill_first_column(table))


# ---------------------------------------------------------------------------
# 单元格辅助
# ---------------------------------------------------------------------------
def cell_item(text: str, align: Qt.AlignmentFlag = Qt.AlignLeft | Qt.AlignVCenter,
              color: str | None = None, bold: bool = False) -> QTableWidgetItem:
    """生成 QTableWidgetItem：金额列右对齐、空值 —、可着色。"""
    item = QTableWidgetItem(text)
    item.setTextAlignment(align)
    if color:
        item.setForeground(QColor(color))
    if bold:
        f = item.font()
        f.setWeight(f.Weight.Bold)  # type: ignore[attr-defined]
        item.setFont(f)
    return item


def money_item(text: str, color: str | None = None, bold: bool = True) -> QTableWidgetItem:
    """金额单元格：右对齐、SemiBold。"""
    return cell_item(text, Qt.AlignRight | Qt.AlignVCenter, color, bold)


def double_line_widget(main_text: str, sub_text: str | None = None,
                       main_bold: bool = True) -> QWidget:
    """双行单元格：主行 14px（可加粗）+ 副行 12px 灰（cell-sub）。"""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 10, 0, 10)
    lay.setSpacing(2)
    main = QLabel(main_text)
    if main_bold:
        main.setStyleSheet(f"font-weight:600; color:{theme.TEXT}; font-size:14px;")
    else:
        main.setStyleSheet(f"color:{theme.TEXT}; font-size:14px;")
    lay.addWidget(main)
    if sub_text:
        sub = QLabel(sub_text)
        sub.setStyleSheet(f"color:{theme.TEXT_3}; font-size:12px;")
        lay.addWidget(sub)
    return w


def cell_hbox(widget: QWidget, top_margin: int = 12) -> QWidget:
    """把任意组件放进水平容器（表格单元格垂直居中）。"""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, top_margin, 0, top_margin)
    lay.addWidget(widget)
    lay.addStretch()
    return w

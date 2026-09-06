"""负债管理页（v2.0，UI 设计规范 4.6）。

topbar：标题 + 「+ 新增负债」；顶部总负债汇总（红色 18px Bold）；
表格：名称+备注副行 / 类型 tag / 剩余·总额 / 年利率 / 月还款额右对齐 / 还款进度（进度条+已还%）/ 操作
（主按钮=本月已还款 act-primary，⋯=还款历史/编辑/删除）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app import constants
from app.constants import type_label
from app.dao import liability_dao
from app.utils import today_str
from app.ui import theme
from app.ui.page_base import PageBase
from app.ui.widgets.action_cell import ActionCell
from app.ui.widgets.base_table import autofit_columns, cell_item, double_line_widget, money_item, setup_table
from app.ui.widgets.button import make_button
from app.ui.widgets.modal import Modal
from app.ui.widgets.sortable_table import SortableTable, sort_rows
from app.ui.widgets.tag import tag_in_cell


class LiabilityDialog(Modal):
    """负债新增/编辑弹窗。"""

    def __init__(self, liability: dict | None = None, parent=None):
        super().__init__("编辑负债" if liability else "新增负债", width=440, parent=parent)
        self.liability = liability
        self.result_data: dict = {}
        form = QFormLayout()
        form.setSpacing(12)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如：XX路房贷")
        form.addRow(self._labeled("名称 *"), self.name_edit)

        self.type_combo = QComboBox()
        for key, label in constants.LIABILITY_TYPES:
            self.type_combo.addItem(label, key)
        form.addRow(self._labeled("类型 *"), self.type_combo)

        two1 = QHBoxLayout()
        two1.setSpacing(12)
        self.total_spin = QDoubleSpinBox()
        self.total_spin.setRange(0, 1e15)
        self.total_spin.setDecimals(2)
        self.total_spin.setSingleStep(10000)
        self.remaining_spin = QDoubleSpinBox()
        self.remaining_spin.setRange(0, 1e15)
        self.remaining_spin.setDecimals(2)
        self.remaining_spin.setSingleStep(10000)
        two1.addWidget(self.total_spin)
        two1.addWidget(self.remaining_spin)
        form.addRow(self._labeled("总金额 · 当前余额"), two1)

        two2 = QHBoxLayout()
        two2.setSpacing(12)
        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0, 100)
        self.rate_spin.setDecimals(2)
        self.rate_spin.setSuffix(" %")
        self.payment_spin = QDoubleSpinBox()
        self.payment_spin.setRange(0, 1e15)
        self.payment_spin.setDecimals(2)
        self.payment_spin.setSingleStep(1000)
        two2.addWidget(self.rate_spin)
        two2.addWidget(self.payment_spin)
        form.addRow(self._labeled("年利率 · 月还款额"), two2)

        self.note_edit = QLineEdit()
        form.addRow(self._labeled("备注"), self.note_edit)

        self.body_layout.addLayout(form)
        self.set_foot("取消", "保存", self._on_save)
        if liability:
            self._load(liability)

    def _load(self, liab: dict):
        self.name_edit.setText(liab["name"])
        idx = self.type_combo.findData(liab["type"])
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.total_spin.setValue(liab["total_amount"] or 0)
        self.remaining_spin.setValue(liab["remaining"] or 0)
        self.rate_spin.setValue(liab["interest_rate"] or 0)
        self.payment_spin.setValue(liab["monthly_payment"] or 0)
        self.note_edit.setText(liab["note"] or "")

    def _on_save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "负债名称不能为空")
            return
        self.result_data = {
            "name": name,
            "type": self.type_combo.currentData(),
            "total_amount": self.total_spin.value(),
            "remaining": self.remaining_spin.value(),
            "interest_rate": self.rate_spin.value(),
            "monthly_payment": self.payment_spin.value(),
            "note": self.note_edit.text().strip() or None,
        }
        self.accept()


class RepayHistoryDialog(Modal):
    """还款历史弹窗（表格：日期/金额）。"""

    def __init__(self, liability: dict, parent=None):
        super().__init__(f"还款历史 — {liability['name']}", width=420, parent=parent)
        self.liability = liability
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["日期", "金额"])
        setup_table(self.table, row_height=40)
        self.body_layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        undo_btn = make_button("撤销最近一次还款", "danger")
        undo_btn.clicked.connect(self._undo)
        btn_row.addWidget(undo_btn)
        self.body_layout.addLayout(btn_row)

        self.set_foot(ok_text="关闭", on_ok=self.accept, ok_only=True)
        self._load()

    def _load(self):
        self.table.setRowCount(0)
        history = liability_dao.list_repayments(self.liability["id"])
        for h in history:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, cell_item(h["repay_date"]))
            self.table.setItem(row, 1, money_item(f"¥{h['amount']:,.2f}"))

    def _undo(self):
        ret = QMessageBox.question(
            self, "撤销还款", "确定撤销最近一次还款吗？将删除该记录并加回余额。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            if liability_dao.undo_last_repayment(self.liability["id"]):
                self._load()


class LiabilitiesPage(PageBase):
    """负债管理页。"""

    def __init__(self, parent=None):
        super().__init__("负债管理", "房贷、车贷、消费贷与信用卡欠款")
        self._build_content()
        self.refresh()

    def _build_content(self):
        add_btn = make_button("+ 新增负债", "primary")
        add_btn.clicked.connect(self._add_liability)
        self.add_action(add_btn)

        body = self.body()
        self.total_label = QLabel("总负债：¥0.00")
        self.total_label.setStyleSheet(f"font-size:18px; font-weight:700; color:{theme.RED};")
        body.addWidget(self.total_label)

        self.table = SortableTable(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["名称", "类型", "剩余 / 总额", "年利率", "月还款额", "还款进度", "操作"]
        )
        setup_table(self.table, row_height=56)
        self.table.set_sortable_cols({0, 1, 2, 3, 4, 5})  # 操作列(6)不可排序
        # 表头点击后由组件统一「延迟 + 合批」重建，无需页面自己接 sort_changed
        self.table.set_rebuild_fn(self._populate_table)
        body.addWidget(self.table, 1)

    # ------------------------------------------------------------------
    def refresh(self):
        self._liabilities = liability_dao.list_liabilities()
        self._populate_table()

    # ------------------------------------------------------------------
    # 表头排序
    # ------------------------------------------------------------------
    # 表头点击后的「延迟 + 合批重建」已下沉到 SortableTable
    # （见 __init__ 里的 set_rebuild_fn），页面只需提供排序键。

    def _liability_sort_key(self, col: int):
        """各列排序键（列范围：0名称/1类型/2剩余金额/3年利率/4月还款额/5还款进度）。"""
        if col == 0:
            return lambda l: l["name"]
        if col == 1:
            return lambda l: type_label(constants.LIABILITY_TYPES, l["type"])
        if col == 2:
            return lambda l: l["remaining"] or 0.0
        if col == 3:
            return lambda l: l["interest_rate"] or 0.0
        if col == 4:
            return lambda l: l["monthly_payment"] or 0.0
        if col == 5:
            def repaid_pct(l):
                total = l["total_amount"] or 0
                remaining = l["remaining"] or 0
                return max(0.0, min(100.0, (total - remaining) / total * 100)) if total else 0.0
            return repaid_pct
        return lambda l: ""

    def _populate_table(self):
        self.table.setUpdatesEnabled(False)
        try:
            rows = sort_rows(self._liabilities, self._liability_sort_key(self.table.current_sort_col()),
                             self.table.current_sort_order())
            self.table.setRowCount(0)
            total = 0.0
            for liab in rows:
                total += liab["remaining"] or 0
                row = self.table.rowCount()
                self.table.insertRow(row)

                self.table.setCellWidget(row, 0, double_line_widget(liab["name"], liab["note"] or None))
                self.table.setCellWidget(row, 1, tag_in_cell(
                    type_label(constants.LIABILITY_TYPES, liab["type"]),
                    {"mortgage": "blue", "credit_card": "red"}.get(liab["type"], "gray"), 14))

                # 剩余（加粗主行） / 总额（灰色副行）——双行布局比单行并排省约一半宽度
                self.table.setCellWidget(row, 2, double_line_widget(
                    f"¥{liab['remaining']:,.2f}", f"总额 ¥{liab['total_amount']:,.2f}"))

                rate = liab["interest_rate"]
                self.table.setItem(row, 3, cell_item(f"{rate:.2f}%" if rate else "—"))
                pay = liab["monthly_payment"]
                self.table.setItem(row, 4, money_item(f"¥{pay:,.2f}" if pay else "—"))

                # 还款进度（细进度条 + 百分比文字，避免 QProgressBar 自带文字撑大行高）
                total_amt = liab["total_amount"] or 0
                remaining = liab["remaining"] or 0
                repaid_pct = max(0.0, min(100.0, (total_amt - remaining) / total_amt * 100)) if total_amt else 0.0
                cell = QWidget()
                cell_lay = QHBoxLayout(cell)
                cell_lay.setContentsMargins(0, 0, 0, 0)
                cell_lay.setSpacing(8)
                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(int(repaid_pct))
                bar.setTextVisible(False)
                bar.setFixedSize(48, 6)  # 紧凑固定宽：避免 QProgressBar 默认 sizeHint 撑宽整列
                cell_lay.addWidget(bar)
                pct_label = QLabel(f"{repaid_pct:.0f}% 已还")
                pct_label.setStyleSheet(f"color:{theme.TEXT_2}; font-size:12px;")
                pct_label.setFixedWidth(52)
                cell_lay.addWidget(pct_label)
                self.table.setCellWidget(row, 5, cell)

                cell = ActionCell(
                    "本月已还款",
                    lambda _=False, x=liab: self._repay(x),
                    primary_kind="primary",
                    more_items=[
                        ("还款历史", lambda _=False, x=liab: self._show_history(x)),
                        ("编辑", lambda _=False, x=liab: self._edit_liability(x)),
                        ("删除", lambda _=False, x=liab: self._delete_liability(x), "danger"),
                    ],
                )
                self.table.setCellWidget(row, 6, cell)

            self.total_label.setText(f"总负债：¥{total:,.2f}")
            autofit_columns(self.table)
        finally:
            self.table.setUpdatesEnabled(True)

        if not self._liabilities:
            self.show_empty("还没有负债", "记录房贷、车贷等负债，跟踪还款进度", "+ 新增负债", self._add_liability)
        else:
            self.hide_empty()

    # ------------------------------------------------------------------
    def _add_liability(self):
        dlg = LiabilityDialog(parent=self)
        if dlg.exec():
            d = dlg.result_data
            liability_dao.create_liability(
                d["name"], d["type"], d["total_amount"], d["remaining"],
                d["interest_rate"], d["monthly_payment"], d["note"],
            )
            self.refresh()
            self.data_changed.emit()

    def _edit_liability(self, liab):
        dlg = LiabilityDialog(liab, parent=self)
        if dlg.exec():
            d = dlg.result_data
            liability_dao.update_liability(
                liab["id"], d["name"], d["type"], d["total_amount"], d["remaining"],
                d["interest_rate"], d["monthly_payment"], d["note"],
            )
            self.refresh()
            self.data_changed.emit()

    def _delete_liability(self, liab):
        ret = QMessageBox.question(
            self, "确认删除", f"确定删除负债「{liab['name']}」吗？还款历史也将一并删除。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            liability_dao.delete_liability(liab["id"])
            self.refresh()
            self.data_changed.emit()

    def _repay(self, liab):
        default = liab["monthly_payment"] or 0
        amount, ok = QInputDialog.getDouble(
            self, "本月已还款", f"输入还款金额（{liab['name']}）：",
            default, 0, 1e15, 2,
        )
        if not ok:
            return
        ret = QMessageBox.question(
            self, "确认还款",
            f"确认还款 ¥{amount:,.2f} 吗？\n还款后余额将扣减（最低扣到 0）。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            liability_dao.repay(liab["id"], amount, today_str())
            self.refresh()
            self.data_changed.emit()
            QMessageBox.information(self, "完成", "还款已记录。")

    def _show_history(self, liab):
        dlg = RepayHistoryDialog(liab, parent=self)
        dlg.exec()
        self.refresh()
        self.data_changed.emit()

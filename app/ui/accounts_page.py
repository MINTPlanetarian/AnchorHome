"""账户管理页（v2.0，UI 设计规范 4.4）。

topbar：标题 + 持有人筛选 + 「+ 新增账户」「⟳ 刷新行情」。
内容：类型筛选 Chip 行 → 账户表格（名称+机构副行 / 类型 tag / 余额右对齐 / 流动性 tag / 状态 tag）
    → 持仓明细卡（默认收起，列含盈亏涨红跌绿）。
"""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from app import constants
from app.constants import type_label
from app.dao import account_dao, holding_dao, member_dao
from app.services import report_service
from app.services.market_service import detect_market, lookup_name
from app.utils import today_str
from app.ui import theme
from app.ui.page_base import PageBase
from app.ui.market_refresh import start_market_refresh
from app.ui.widgets.action_cell import ActionCell
from app.ui.widgets.base_table import (
    autofit_columns, cell_item, double_line_widget, money_item, setup_table,
)
from app.ui.widgets.button import make_button
from app.ui.widgets.chip import ChipGroup
from app.ui.thread_helper import stop_thread
from app.ui.widgets.modal import Modal
from app.ui.widgets.sortable_table import SortableTable, sort_rows
from app.ui.widgets.tag import make_tag, tag_in_cell


# ---------------------------------------------------------------------------
# 账户对话框（v1.2 字段 + 理财可用日期 Radio Pills）
# ---------------------------------------------------------------------------
class AccountDialog(Modal):
    """账户新增/编辑弹窗。"""

    def __init__(self, account: dict | None = None, parent=None):
        super().__init__("编辑账户" if account else "新增账户", width=440, parent=parent)
        self.account = account
        self.result_data: dict = {}
        self.form = QFormLayout()
        self.form.setSpacing(12)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如 招行-活期 / 支付宝-余额宝")
        self.form.addRow(self._labeled("账户名称 *"), self.name_edit)

        self.type_combo = QComboBox()
        for key, label in constants.ACCOUNT_TYPES:
            self.type_combo.addItem(label, key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.form.addRow(self._labeled("账户类型 *"), self.type_combo)

        self.member_combo = QComboBox()
        for m in member_dao.list_members():
            self.member_combo.addItem(m["name"], m["id"])
        self.form.addRow(self._labeled("持有人 *"), self.member_combo)

        self.institution_combo = QComboBox()
        self.institution_combo.setEditable(True)
        self.institution_combo.addItems(constants.INSTITUTIONS)
        self.institution_combo.setCurrentText("")
        self.form.addRow(self._labeled("开户机构"), self.institution_combo)

        self.currency_combo = QComboBox()
        self.currency_combo.addItems(constants.CURRENCIES)
        self.form.addRow(self._labeled("币种"), self.currency_combo)

        self.balance_spin = QDoubleSpinBox()
        self.balance_spin.setRange(-1e12, 1e12)
        self.balance_spin.setDecimals(2)
        self.balance_spin.setSingleStep(1000)
        self.form.addRow(self._labeled("余额"), self.balance_spin)

        # 可用日期（仅理财）：Radio Pills 随时可用 / 指定日期
        self.avail_field = QWidget()
        avail_lay = QVBoxLayout(self.avail_field)
        avail_lay.setContentsMargins(0, 0, 0, 0)
        avail_lay.setSpacing(8)
        pill_row = QHBoxLayout()
        pill_row.setSpacing(8)
        self.pill_anytime = QPushButton("随时可用")
        self.pill_anytime.setProperty("pill", "true")
        self.pill_anytime.setCheckable(True)
        self.pill_specific = QPushButton("指定日期")
        self.pill_specific.setProperty("pill", "true")
        self.pill_specific.setCheckable(True)
        for b in (self.pill_anytime, self.pill_specific):
            b.setCursor(Qt.PointingHandCursor)
            pill_row.addWidget(b, 1)
        from PySide6.QtWidgets import QButtonGroup
        self._avail_group = QButtonGroup(self)
        self._avail_group.setExclusive(True)
        self._avail_group.addButton(self.pill_anytime)
        self._avail_group.addButton(self.pill_specific)
        self.pill_anytime.setChecked(True)
        self.pill_anytime.toggled.connect(lambda c: self._on_avail_toggled())
        avail_lay.addLayout(pill_row)

        self.avail_date_edit = QDateEdit()
        self.avail_date_edit.setCalendarPopup(True)
        self.avail_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.avail_date_edit.setDate(QDate.currentDate())
        self.avail_date_edit.setMinimumDate(QDate.currentDate())
        self.avail_date_edit.setEnabled(False)
        avail_lay.addWidget(self.avail_date_edit)
        self.form.addRow(self._labeled("可用日期"), self.avail_field)

        self.note_edit = QLineEdit()
        self.form.addRow(self._labeled("备注"), self.note_edit)

        self.body_layout.addLayout(self.form)
        self.set_foot("取消", "保存", self._on_save)

        if account:
            self._load(account)
        else:
            self._on_type_changed()

    def _on_type_changed(self):
        is_wealth = self.type_combo.currentData() == "wealth"
        self.form.setRowVisible(self.avail_field, is_wealth)

    def _on_avail_toggled(self):
        self.avail_date_edit.setEnabled(self.pill_specific.isChecked())

    def _get_available_date(self) -> str | None:
        if self.pill_anytime.isChecked():
            return None
        text = self.avail_date_edit.text().strip()
        if len(text) == 8 and text.isdigit():
            d = QDate.fromString(text, "yyyyMMdd")
            if d.isValid():
                return d.toString("yyyy-MM-dd")
        return self.avail_date_edit.date().toString("yyyy-MM-dd")

    def _load(self, account: dict):
        self.name_edit.setText(account["name"])
        idx = self.type_combo.findData(account["type"])
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        midx = self.member_combo.findData(account.get("member_id"))
        if midx >= 0:
            self.member_combo.setCurrentIndex(midx)
        self.institution_combo.setCurrentText(account["institution"] or "")
        cidx = self.currency_combo.findText(account["currency"])
        if cidx >= 0:
            self.currency_combo.setCurrentIndex(cidx)
        self.balance_spin.setValue(account["balance"] or 0)
        avail = account.get("available_date")
        if avail:
            self.pill_specific.setChecked(True)
            d = QDate.fromString(avail, "yyyy-MM-dd")
            if d.isValid():
                self.avail_date_edit.setDate(d)
        else:
            self.pill_anytime.setChecked(True)
        self.note_edit.setText(account["note"] or "")
        self._on_type_changed()
        self._on_avail_toggled()

    def _on_save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "账户名称不能为空")
            return
        self.result_data = {
            "name": name,
            "type": self.type_combo.currentData(),
            "currency": self.currency_combo.currentText(),
            "balance": self.balance_spin.value(),
            "institution": self.institution_combo.currentText().strip() or None,
            "note": self.note_edit.text().strip() or None,
            "member_id": self.member_combo.currentData(),
            "available_date": self._get_available_date() if self.type_combo.currentData() == "wealth" else None,
        }
        self.accept()


# ---------------------------------------------------------------------------
# 持仓对话框
# ---------------------------------------------------------------------------
class NameLookupWorker(QThread):
    """后台线程：按代码联网查询证券名称。"""

    found = Signal(str)

    def __init__(self, code: str, parent=None):
        super().__init__(parent)
        self._code = code

    def run(self):
        name = lookup_name(self._code)
        if name:
            self.found.emit(name)


class HoldingDialog(Modal):
    """持仓新增/编辑弹窗（代码自动补全名称，异步）。"""

    def __init__(self, holding: dict | None = None, parent=None):
        super().__init__("编辑持仓" if holding else "新增持仓", width=400, parent=parent)
        self.holding = holding
        self._lookup_worker = None
        self.result_data: dict = {}
        form = QFormLayout()
        form.setSpacing(12)

        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("如 600519 / 110022")
        self.code_edit.editingFinished.connect(self._auto_fill_name)
        form.addRow(self._labeled("证券代码 *"), self.code_edit)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("联网自动补全，失败请手填")
        form.addRow(self._labeled("名称 *"), self.name_edit)

        self.quantity_spin = QDoubleSpinBox()
        self.quantity_spin.setRange(0, 1e12)
        self.quantity_spin.setDecimals(2)
        self.quantity_spin.setValue(100)
        form.addRow(self._labeled("数量"), self.quantity_spin)

        self.cost_spin = QDoubleSpinBox()
        self.cost_spin.setRange(0, 1e12)
        self.cost_spin.setDecimals(4)
        self.cost_spin.setValue(1.0)
        form.addRow(self._labeled("成本价"), self.cost_spin)

        self.body_layout.addLayout(form)
        self.set_foot("取消", "保存", self._on_save)
        if holding:
            self._load(holding)

    def _load(self, holding: dict):
        self.code_edit.setText(holding["code"])
        self.name_edit.setText(holding["name"])
        self.quantity_spin.setValue(holding["quantity"])
        self.cost_spin.setValue(holding["cost_price"])

    def _auto_fill_name(self):
        code = self.code_edit.text().strip()
        if len(code) != 6 or not code.isdigit():
            return
        if self.name_edit.text().strip():
            return
        worker = NameLookupWorker(code, self)
        worker.found.connect(self._on_name_found)
        # editingFinished 每次触发都可能开一个线程，交给托管避免引用被覆盖
        start_thread(self, "_lookup_worker", worker)

    def _on_name_found(self, name: str):
        if not self.name_edit.text().strip():
            self.name_edit.setText(name)

    def closeEvent(self, event):
        """关闭前回收查询线程。

        弹窗关闭时线程若仍在运行，Python 侧引用归零会让运行中的 QThread 被销毁，
        触发 "QThread: Destroyed while thread is still running" 崩溃。
        """
        stop_thread(self, "_lookup_worker")
        super().closeEvent(event)

    def _on_save(self):
        code = self.code_edit.text().strip()
        name = self.name_edit.text().strip()
        if not code or not name:
            QMessageBox.warning(self, "提示", "代码和名称不能为空")
            return
        try:
            market = detect_market(code)
        except ValueError as e:
            QMessageBox.warning(self, "提示", str(e))
            return
        self.result_data = {
            "code": code, "name": name, "market": market,
            "quantity": self.quantity_spin.value(),
            "cost_price": self.cost_spin.value(),
        }
        self.accept()


# ---------------------------------------------------------------------------
# 账户页
# ---------------------------------------------------------------------------
# 由 constants.ACCOUNT_TYPES 派生：新增账户类型时筛选器自动跟上，不必同步改这里
TYPE_FILTERS = [("all", "全部")] + list(constants.ACCOUNT_TYPES)


class AccountsPage(PageBase):
    """账户管理页。"""

    data_changed = Signal()
    status_msg = Signal(str)

    def __init__(self, parent=None):
        super().__init__("账户管理", "现金、理财、股票基金与信用卡账户")
        self._type_filter = "all"
        self._member_id = None
        self._holding_account = None
        self._holding_mv: dict = {}  # 持仓账户市值映射（批量取回，避免逐账户 N+1）
        self._build_content()
        self.refresh()

    def _build_content(self):
        # ---- topbar ----
        self.member_filter = QComboBox()
        self.member_filter.addItem("全部持有人", None)
        self.member_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.add_action(self.member_filter)

        refresh_btn = make_button("⟳ 刷新行情", "ghost")
        refresh_btn.clicked.connect(self._refresh_market)
        self.add_action(refresh_btn)

        add_btn = make_button("+ 新增账户", "primary")
        add_btn.clicked.connect(self._add_account)
        self.add_action(add_btn)

        body = self.body()

        # ---- 类型筛选 Chip ----
        self.type_chips = ChipGroup(TYPE_FILTERS, default="all")
        self.type_chips.changed.connect(self._on_type_changed)
        body.addWidget(self.type_chips)

        # ---- 账户表格（表头点击三态排序，操作列除外）----
        self.table = SortableTable(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["名称", "持有人", "类型", "余额/市值", "可用性", "币种", "状态", "操作"]
        )
        setup_table(self.table, row_height=56)
        self.table.set_sortable_cols({0, 1, 2, 3, 4, 5, 6})  # 操作列(7)不可排序
        # 表头点击后由组件统一「延迟 + 合批」重建，无需页面自己接 sort_changed
        self.table.set_rebuild_fn(self._populate_table)
        body.addWidget(self.table, 1)

        # ---- 持仓明细卡（默认收起）----
        self.holding_card = QFrame()
        self.holding_card.setObjectName("card")
        h_lay = QVBoxLayout(self.holding_card)
        h_lay.setContentsMargins(theme.CARD_PADDING, 16, theme.CARD_PADDING, 16)
        h_lay.setSpacing(10)

        h_head = QHBoxLayout()
        self.holding_title = QLabel("持仓明细")
        self.holding_title.setObjectName("panelTitle")
        h_head.addWidget(self.holding_title)
        h_head.addStretch()
        h_lay.addLayout(h_head)

        self.holding_table = QTableWidget(0, 8)
        self.holding_table.setHorizontalHeaderLabels(
            ["代码", "名称", "数量", "成本价", "现价", "市值", "盈亏金额", "盈亏%"]
        )
        # 持仓表无操作列：全部数据列由 RTC/autofit 按内容自适应
        setup_table(self.holding_table, row_height=44)
        h_lay.addWidget(self.holding_table, 1)

        h_btns = QHBoxLayout()
        h_btns.addStretch()
        self.add_holding_btn = make_button("+ 新增持仓", "primary")
        self.add_holding_btn.clicked.connect(self._add_holding)
        self.edit_holding_btn = make_button("编辑持仓", "ghost")
        self.edit_holding_btn.clicked.connect(self._edit_holding)
        self.del_holding_btn = make_button("删除持仓", "danger")
        self.del_holding_btn.clicked.connect(self._delete_holding)
        h_btns.addWidget(self.add_holding_btn)
        h_btns.addWidget(self.edit_holding_btn)
        h_btns.addWidget(self.del_holding_btn)
        h_lay.addLayout(h_btns)
        self.holding_card.setVisible(False)
        body.addWidget(self.holding_card)
        self._set_holding_buttons_enabled(False)

    # ------------------------------------------------------------------
    def refresh(self):
        """重载数据并重建表格（保留当前排序状态）。"""
        self._sync_member_filter()
        filter_id = self.member_filter.currentData()
        accounts = account_dao.list_accounts(member_id=filter_id)
        if self._type_filter != "all":
            accounts = [a for a in accounts if a["type"] == self._type_filter]
        self._accounts = accounts
        self._populate_table()

    # ------------------------------------------------------------------
    # 表头排序
    # ------------------------------------------------------------------
    # 表头点击后的「延迟 + 合批重建」已下沉到 SortableTable
    # （见 __init__ 里的 set_rebuild_fn），页面只需提供排序键。

    def _account_sort_key(self, col: int):
        """各列排序键（列范围：0名称/1持有人/2类型/3余额·市值/4可用性/5币种/6状态）。"""
        if col == 0:
            return lambda a: a["name"]
        if col == 1:
            return lambda a: a.get("member_name") or "未归属"
        if col == 2:
            return lambda a: type_label(constants.ACCOUNT_TYPES, a["type"])
        if col == 3:
            def value(a):
                v = a["balance"] or 0.0
                if a["type"] in ("stock", "fund"):
                    v += self._holding_mv.get(a["id"], 0.0)
                return v
            return value
        if col == 4:
            # 可用性按流动性优先级：随时可用(0) → 已到期可用(1) → 日期可用(2) → 非理财(3)
            def liquidity(a):
                if a["type"] != "wealth":
                    return (3, "")
                avail = a.get("available_date")
                today = today_str()
                if not avail:
                    return (0, "")
                if avail <= today:
                    return (1, "")
                return (2, avail)
            return liquidity
        if col == 5:
            return lambda a: a["currency"]
        if col == 6:
            return lambda a: 1 if a["is_active"] else 0
        return lambda a: ""

    def _populate_table(self):
        """按当前排序状态重建表格行（批量更新，减少重绘压力）。"""
        self.table.setUpdatesEnabled(False)
        try:
            # 持仓市值一次性批量取回（消除排序键与渲染各查一遍的 N+1）
            self._holding_mv = report_service.holdings_market_values()
            rows = sort_rows(self._accounts, self._account_sort_key(self.table.current_sort_col()),
                             self.table.current_sort_order())
            self.table.setRowCount(0)
            for acc in rows:
                row = self.table.rowCount()
                self.table.insertRow(row)

                # 名称（主行 + 机构副行）
                self.table.setCellWidget(
                    row, 0,
                    double_line_widget(acc["name"], acc["institution"] or None),
                )
                self.table.setItem(row, 1, cell_item(acc.get("member_name") or "未归属"))
                self.table.setCellWidget(row, 2, tag_in_cell(
                    type_label(constants.ACCOUNT_TYPES, acc["type"]), self._type_tag(acc["type"]), 14))

                display_value = acc["balance"] or 0.0
                if acc["type"] in ("stock", "fund"):
                    display_value += self._holding_mv.get(acc["id"], 0.0)
                self.table.setItem(row, 3, money_item(f"¥{display_value:,.2f}"))

                self.table.setCellWidget(row, 4, self._liquidity_tag(acc))
                self.table.setItem(row, 5, cell_item(acc["currency"], Qt.AlignCenter))
                self.table.setCellWidget(row, 6, tag_in_cell(
                    "启用" if acc["is_active"] else "停用",
                    "green" if acc["is_active"] else "gray", 14))

                self._make_action_cell(row, acc)
            autofit_columns(self.table)
        finally:
            self.table.setUpdatesEnabled(True)

        if not account_dao.list_accounts():
            self.show_empty("还没有账户", "记录现金、理财、股票与基金账户", "+ 新增账户", self._add_account)
        elif not self._accounts:
            # 有账户但当前筛选条件下无匹配：给出明确空状态，而非一张空表
            self.show_empty("没有匹配的账户", "换个筛选条件试试", None, None)
        else:
            self.hide_empty()

        # 刷新持仓区
        if self._holding_account is not None:
            self._load_holdings(self._holding_account["id"])

    @staticmethod
    def _type_tag(t: str) -> str:
        return {"cash": "green", "credit_card": "red", "provident_fund": "blue"}.get(t, "gray")

    def _liquidity_tag(self, acc) -> QWidget:
        """可用性列流动性 tag：随时可用 green / 已到期 orange / 日期可用 gray / 非理财 —。"""
        if acc["type"] != "wealth":
            return tag_in_cell("—", "gray", 14)
        avail = acc.get("available_date")
        today = today_str()
        if not avail:
            return tag_in_cell("随时可用", "green", 14)
        if avail <= today:
            return tag_in_cell("已到期可用", "orange", 14)
        return tag_in_cell(f"{avail} 可用", "gray", 14)

    def _sync_member_filter(self):
        current = self.member_filter.currentData()
        self.member_filter.blockSignals(True)
        self.member_filter.clear()
        self.member_filter.addItem("全部持有人", None)
        for m in member_dao.list_members():
            self.member_filter.addItem(m["name"], m["id"])
        idx = self.member_filter.findData(current)
        self.member_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.member_filter.blockSignals(False)

    def _on_filter_changed(self):
        self.refresh()

    def _on_type_changed(self, key):
        self._type_filter = key
        self.refresh()

    def _make_action_cell(self, row, acc):
        toggle_text = "停用" if acc["is_active"] else "启用"
        if acc["type"] in ("stock", "fund"):
            cell = ActionCell(
                "持仓", lambda _=False, a=acc: self._show_holdings(a),
                more_items=[
                    ("编辑", lambda _=False, a=acc: self._edit_account(a)),
                    (toggle_text, lambda _=False, a=acc: self._toggle_account(a)),
                    ("删除", lambda _=False, a=acc: self._delete_account(a), "danger"),
                ],
            )
        else:
            cell = ActionCell(
                "编辑", lambda _=False, a=acc: self._edit_account(a),
                more_items=[
                    (toggle_text, lambda _=False, a=acc: self._toggle_account(a)),
                    ("删除", lambda _=False, a=acc: self._delete_account(a), "danger"),
                ],
            )
        self.table.setCellWidget(row, 7, cell)

    # ------------------------------------------------------------------
    # 账户操作
    # ------------------------------------------------------------------
    def _add_account(self):
        dlg = AccountDialog(parent=self)
        if dlg.exec():
            d = dlg.result_data
            account_dao.create_account(
                d["name"], d["type"], d["currency"], d["balance"],
                d["institution"], d["note"], d["member_id"], d["available_date"],
            )
            self.refresh()
            self.data_changed.emit()

    def _edit_account(self, acc):
        dlg = AccountDialog(acc, parent=self)
        if dlg.exec():
            d = dlg.result_data
            account_dao.update_account(
                acc["id"], d["name"], d["type"], d["currency"], d["balance"],
                d["institution"], d["note"], d["member_id"], d["available_date"],
            )
            self.refresh()
            self.data_changed.emit()

    def _toggle_account(self, acc):
        account_dao.set_active(acc["id"], not acc["is_active"])
        self.refresh()
        self.data_changed.emit()

    def _delete_account(self, acc):
        if account_dao.has_holdings(acc["id"]):
            QMessageBox.warning(self, "无法删除", "该账户下仍有持仓，请先清空持仓。")
            return
        ret = QMessageBox.question(
            self, "确认删除", f"确定删除账户「{acc['name']}」吗？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            account_dao.delete_account(acc["id"])
            self.refresh()
            self.data_changed.emit()

    # ------------------------------------------------------------------
    # 持仓操作
    # ------------------------------------------------------------------
    def _show_holdings(self, acc):
        if self._holding_account is not None and self._holding_account["id"] == acc["id"]:
            # 再次点击：收起
            self.holding_card.setVisible(not self.holding_card.isVisible())
            return
        self._holding_account = acc
        self.holding_title.setText(f"持仓明细 — {acc['name']}")
        self.holding_card.setVisible(True)
        self._load_holdings(acc["id"])
        self._set_holding_buttons_enabled(True)

    def _load_holdings(self, account_id):
        self.holding_table.setRowCount(0)
        for h in holding_dao.list_holdings_by_account(account_id):
            row = self.holding_table.rowCount()
            self.holding_table.insertRow(row)
            qty = h["quantity"] or 0
            cost = h["cost_price"] or 0
            price = h["current_price"] if h["current_price"] is not None else None

            code_item = cell_item(h["code"])
            code_item.setData(Qt.UserRole, h["id"])
            self.holding_table.setItem(row, 0, code_item)
            self.holding_table.setItem(row, 1, cell_item(h["name"]))
            self.holding_table.setItem(row, 2, cell_item(f"{qty:,.2f}"))
            self.holding_table.setItem(row, 3, cell_item(f"{cost:,.4f}"))

            if price is None:
                for col in range(4, 8):
                    self.holding_table.setItem(row, col, cell_item("—", Qt.AlignRight))
                continue
            market_value = qty * price
            pnl = (price - cost) * qty
            pnl_pct = (price - cost) / cost * 100 if cost else 0.0
            self.holding_table.setItem(row, 4, cell_item(f"{price:,.4f}"))
            self.holding_table.setItem(row, 5, money_item(f"¥{market_value:,.2f}"))
            color = theme.RED if pnl >= 0 else theme.GREEN  # 涨红跌绿
            self.holding_table.setItem(row, 6, money_item(f"{pnl:+,.2f}", color))
            self.holding_table.setItem(row, 7, money_item(f"{pnl_pct:+.2f}%", color))
        autofit_columns(self.holding_table)

    def _set_holding_buttons_enabled(self, enabled):
        for b in (self.add_holding_btn, self.edit_holding_btn, self.del_holding_btn):
            b.setEnabled(enabled)

    def _selected_holding(self):
        row = self.holding_table.currentRow()
        if row < 0 or self._holding_account is None:
            return None
        item = self.holding_table.item(row, 0)
        if item is None:
            return None
        holding_id = item.data(Qt.UserRole)
        for h in holding_dao.list_holdings_by_account(self._holding_account["id"]):
            if h["id"] == holding_id:
                return h
        return None

    def _add_holding(self):
        dlg = HoldingDialog(parent=self)
        if dlg.exec():
            d = dlg.result_data
            holding_dao.create_holding(
                self._holding_account["id"], d["code"], d["name"], d["market"],
                d["quantity"], d["cost_price"],
            )
            self._load_holdings(self._holding_account["id"])
            self.refresh()
            self.data_changed.emit()

    def _edit_holding(self):
        h = self._selected_holding()
        if h is None:
            QMessageBox.information(self, "提示", "请先选择一条持仓")
            return
        dlg = HoldingDialog(h, parent=self)
        if dlg.exec():
            d = dlg.result_data
            holding_dao.update_holding(h["id"], d["quantity"], d["cost_price"])
            self._load_holdings(self._holding_account["id"])
            self.refresh()
            self.data_changed.emit()

    def _delete_holding(self):
        h = self._selected_holding()
        if h is None:
            QMessageBox.information(self, "提示", "请先选择一条持仓")
            return
        ret = QMessageBox.question(
            self, "确认删除", f"确定删除持仓「{h['name']}」吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            holding_dao.delete_holding(h["id"])
            self._load_holdings(self._holding_account["id"])
            self.refresh()
            self.data_changed.emit()

    # ------------------------------------------------------------------
    # 行情刷新
    # ------------------------------------------------------------------
    def _refresh_market(self):
        if start_market_refresh(self, "_fetcher", self._on_prices_ready, self._on_fetch_failed):
            return
        # 未启动有两种原因：没有任何持仓，或上一次刷新仍在进行（防重入）
        if not holding_dao.list_all_holdings():
            QMessageBox.information(self, "提示", "暂无持仓可刷新")
        else:
            self.status_msg.emit("行情正在刷新中，请稍候")

    def _on_prices_ready(self, prices: dict):
        try:
            if not prices:
                QMessageBox.warning(self, "行情更新失败", "未能获取到任何行情，显示为缓存价格。")
                return
            holding_dao.update_prices(prices)
            self.refresh()
            self.data_changed.emit()
            self.status_msg.emit(f"行情已更新，共 {len(prices)} 只")
        except Exception as e:
            QMessageBox.warning(self, "行情更新失败", f"{e}\n显示为缓存价格。")

    def _on_fetch_failed(self, err: str):
        QMessageBox.warning(self, "行情更新失败", f"{err}\n显示为缓存价格。")

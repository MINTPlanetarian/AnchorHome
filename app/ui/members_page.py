"""家庭成员（账户持有人）管理页（v2.0，UI 设计规范 4.3）。

topbar：标题 + 描述 + 「+ 新增成员」；表格列：姓名(默认 tag) / 关系 tag / 名下账户数 / 备注 / 操作。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.dao import member_dao
from app.ui import theme
from app.ui.page_base import PageBase
from app.ui.widgets.action_cell import ActionCell
from app.ui.widgets.base_table import autofit_columns, cell_item, double_line_widget, setup_table
from app.ui.widgets.button import make_button
from app.ui.widgets.modal import Modal
from app.ui.widgets.sortable_table import SortableTable, sort_rows
from app.ui.widgets.tag import make_tag, tag_in_cell


class MemberDialog(Modal):
    """成员新增/编辑弹窗（规范 3.8 结构）。"""

    def __init__(self, member: dict | None = None, parent=None):
        super().__init__("编辑成员" if member else "新增成员", width=420, parent=parent)
        self.member = member
        self.result_data: dict = {}

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如：本人 / 配偶 / 孩子")
        form.addRow(self._labeled("姓名 *"), self.name_edit)

        self.relation_combo = QComboBox()
        self.relation_combo.addItems(member_dao.RELATIONS)
        form.addRow(self._labeled("与户主关系"), self.relation_combo)

        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("选填")
        form.addRow(self._labeled("备注"), self.note_edit)

        self.body_layout.addLayout(form)
        self.set_foot("取消", "保存", self._on_save)
        if member:
            self._load(member)

    def _load(self, member: dict):
        self.name_edit.setText(member["name"])
        idx = self.relation_combo.findText(member["relation"])
        if idx >= 0:
            self.relation_combo.setCurrentIndex(idx)
        self.note_edit.setText(member["note"] or "")

    def _on_save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "成员姓名不能为空")
            return
        self.result_data = {
            "name": name,
            "relation": self.relation_combo.currentText(),
            "note": self.note_edit.text().strip() or None,
        }
        self.accept()


class MembersPage(PageBase):
    """家庭成员管理页。"""

    def __init__(self, parent=None):
        super().__init__("家庭成员", "成员用于区分账户持有人；删除成员前请先转移或删除其名下账户。")
        # 各成员名下账户数：每次刷新一次性取回，渲染列与排序键共用（避免逐行查 SQL）
        self._acc_counts: dict[int, int] = {}
        self._build_content()
        self.refresh()

    def _build_content(self):
        add_btn = make_button("+ 新增成员", "primary")
        add_btn.clicked.connect(self._add_member)
        self.add_action(add_btn)

        self.table = SortableTable(0, 5)
        self.table.setHorizontalHeaderLabels(["姓名", "关系", "名下账户数", "备注", "操作"])
        setup_table(self.table, row_height=52)
        self.table.set_sortable_cols({0, 1, 2, 3})  # 操作列(4)不可排序
        # 表头点击后由组件统一「延迟 + 合批」重建，无需页面自己接 sort_changed
        self.table.set_rebuild_fn(self._populate_table)
        self.body().addWidget(self.table, 1)

    # ------------------------------------------------------------------
    def refresh(self):
        self._members = member_dao.list_members()
        self._populate_table()

    # ------------------------------------------------------------------
    # 表头排序
    # ------------------------------------------------------------------
    # 表头点击后的「延迟 + 合批重建」已下沉到 SortableTable
    # （见 __init__ 里的 set_rebuild_fn），页面只需提供排序键。

    def _member_sort_key(self, col: int):
        """各列排序键（列范围：0姓名/1关系/2名下账户数/3备注）。"""
        if col == 0:
            return lambda m: m["name"]
        if col == 1:
            return lambda m: m["relation"]
        if col == 2:
            # 用刷新时一次性取回的映射，避免排序时每行各查一次
            return lambda m: self._acc_counts.get(m["id"], 0)
        if col == 3:
            return lambda m: m["note"] or ""
        return lambda m: ""

    def _populate_table(self):
        self.table.setUpdatesEnabled(False)
        try:
            # 一次性取回各成员账户数：渲染列与排序键共用，避免每行一次 SQL（N+1）
            self._acc_counts = member_dao.count_accounts_by_member()
            rows = sort_rows(self._members, self._member_sort_key(self.table.current_sort_col()),
                             self.table.current_sort_order())
            self.table.setRowCount(0)
            default_id = member_dao.default_member_id()
            for m in rows:
                row = self.table.rowCount()
                self.table.insertRow(row)

                # 姓名（默认成员加"默认"蓝色 tag）
                if m["id"] == default_id:
                    main = QLabel(m["name"])
                    main.setStyleSheet(f"font-weight:600; color:{theme.TEXT}; font-size:14px;")
                    w = QVBoxLayout()
                    w.setContentsMargins(0, 8, 0, 8)
                    w.setSpacing(4)
                    w.addWidget(main)
                    row_line = QHBoxLayout()
                    row_line.setSpacing(6)
                    row_line.addWidget(make_tag("默认", "blue"))
                    row_line.addStretch()
                    w.addLayout(row_line)
                    cell = QWidget()
                    cell.setLayout(w)
                    self.table.setCellWidget(row, 0, cell)
                else:
                    self.table.setCellWidget(row, 0, double_line_widget(m["name"]))

                self.table.setCellWidget(row, 1, tag_in_cell(m["relation"], "gray"))
                count = self._acc_counts.get(m["id"], 0)
                self.table.setItem(row, 2, cell_item(str(count), Qt.AlignRight | Qt.AlignVCenter))
                self.table.setItem(row, 3, cell_item(m["note"] or "—"))

                if m["id"] == default_id:
                    cell = ActionCell("编辑", lambda _=False, x=m: self._edit_member(x))
                else:
                    cell = ActionCell(
                        "编辑", lambda _=False, x=m: self._edit_member(x),
                        more_items=[("删除", lambda _=False, x=m: self._delete_member(x), "danger")],
                    )
                self.table.setCellWidget(row, 4, cell)
            autofit_columns(self.table)
        finally:
            self.table.setUpdatesEnabled(True)

        if not self._members:
            self.show_empty("还没有家庭成员", "新增成员以区分账户持有人", "+ 新增成员", self._add_member)
        else:
            self.hide_empty()

    # ------------------------------------------------------------------
    def _add_member(self):
        dlg = MemberDialog(parent=self)
        if dlg.exec():
            d = dlg.result_data
            member_dao.create_member(d["name"], d["relation"], d["note"])
            self.refresh()
            self.data_changed.emit()

    def _edit_member(self, m):
        dlg = MemberDialog(m, parent=self)
        if dlg.exec():
            d = dlg.result_data
            member_dao.update_member(m["id"], d["name"], d["relation"], d["note"])
            self.refresh()
            self.data_changed.emit()

    def _delete_member(self, m):
        count = member_dao.count_accounts(m["id"])
        if count > 0:
            QMessageBox.warning(
                self, "无法删除",
                f"成员「{m['name']}」名下仍有 {count} 个账户，请先转移或删除其名下账户。",
            )
            return
        ret = QMessageBox.question(
            self, "确认删除", f"确定删除成员「{m['name']}」吗？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            member_dao.delete_member(m["id"])
            self.refresh()
            self.data_changed.emit()

"""资产台账页（v2.0，UI 设计规范 4.5，以 HTML demo assets.html 为 1:1 视觉基准）。

topbar：标题 + 描述 + 「更新估值」ghost + 「+ 新增资产」primary。
内容：保险口径 Banner → 5 统计卡（资产总估值 hero）→ 类型筛选 Chip + 计数
    → 表格（保险子类型 tag / "不计入资产" tag / 附件数 / 操作列）。
弹窗：v1.4 动态表单（选保险 → 子类型 Radio Pills + 保额 + 年保费；保障型现金价值禁用置 0 + orange 提示）。
附件：⋯菜单"查看附件"弹出管理弹窗。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app import constants
from app.constants import type_label
from app.dao import asset_dao, member_dao
from app.database import get_data_dir
from app.services import report_service
from app.ui import theme
from app.ui.page_base import PageBase
from app.ui.widgets.action_cell import ActionCell
from app.ui.widgets.banner import Banner
from app.ui.widgets.base_table import autofit_columns, cell_item, double_line_widget, money_item, setup_table
from app.ui.widgets.button import make_button
from app.ui.widgets.chip import ChipGroup
from app.ui.widgets.icon import svg_to_icon
from app.ui.widgets.modal import Modal
from app.ui.widgets.stat_card import StatCard
from app.ui.widgets.sortable_table import SortableTable, sort_rows
from app.ui.widgets.tag import make_tag, tag_in_cell

MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".pdf"}

ASSET_FILTERS = [("all", "全部"), ("real_estate", "房产"), ("vehicle", "车辆"),
                 ("insurance", "保险"), ("precious_metal", "贵金属"), ("other", "其他")]


# ---------------------------------------------------------------------------
# 资产对话框（v1.4 保险动态表单）
# ---------------------------------------------------------------------------
class AssetDialog(Modal):
    """资产新增/编辑弹窗。类型=保险时展开子类型 Radio Pills + 保额 + 年保费。"""

    def __init__(self, asset: dict | None = None, parent=None):
        super().__init__("编辑资产" if asset else "新增资产", width=480, parent=parent)
        self.asset = asset
        self.result_data: dict = {}
        form = QFormLayout()
        form.setSpacing(12)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如：滨江花园住房 / 重大疾病险")
        self.name_edit.setMinimumHeight(40)
        form.addRow(self._labeled("名称 *"), self.name_edit)

        type_row = QHBoxLayout()
        type_row.setSpacing(12)
        self.type_combo = QComboBox()
        self.type_combo.setMinimumHeight(40)
        for key, label in constants.ASSET_TYPES:
            self.type_combo.addItem(label, key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_row.addWidget(self.type_combo, 1)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setMinimumHeight(40)
        from PySide6.QtCore import QDate
        self.date_edit.setDate(QDate.currentDate())
        type_row.addWidget(self.date_edit, 1)
        form.addRow(self._labeled("类型 *"), type_row)

        # 保险专属区块
        self.ins_field = QWidget()
        ins_lay = QVBoxLayout(self.ins_field)
        ins_lay.setContentsMargins(0, 0, 0, 0)
        ins_lay.setSpacing(8)

        sub_row = QHBoxLayout()
        sub_row.setSpacing(8)
        self.pill_protection = QPushButton("保障型")
        self.pill_protection.setProperty("pill", "true")
        self.pill_protection.setCheckable(True)
        self.pill_savings = QPushButton("储蓄型")
        self.pill_savings.setProperty("pill", "true")
        self.pill_savings.setCheckable(True)
        for b in (self.pill_protection, self.pill_savings):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(40)
            sub_row.addWidget(b, 1)
        # 手动互斥（不用 QButtonGroup：exclusive 不允许全部取消，而"未分类"旧数据需要全不选）
        self.pill_protection.clicked.connect(lambda: self._select_subtype("protection"))
        self.pill_savings.clicked.connect(lambda: self._select_subtype("savings"))
        self._select_subtype("savings")
        ins_lay.addLayout(sub_row)
        self.subtype_hint = QLabel("储蓄型保险按现金价值计入总资产")
        self.subtype_hint.setObjectName("formHint")
        ins_lay.addWidget(self.subtype_hint)

        # 被保险人（仅保险）：直接列出全部家庭成员，默认选中默认成员（=资产所有者，快速填写）
        self.insured_label = QLabel("被保险人")
        self.insured_label.setObjectName("formLabel")
        ins_lay.addWidget(self.insured_label)
        self.insured_combo = QComboBox()
        self.insured_combo.setMinimumHeight(40)
        default_id = member_dao.default_member_id()
        default_name = "本人"
        for m in member_dao.list_members():
            if m["id"] == default_id:
                default_name = m["name"]
                break
        # 默认成员排第一并默认选中（相当于"与资产所有者相同"）
        self.insured_combo.addItem(default_name, default_id)
        for m in member_dao.list_members():
            if m["id"] != default_id:
                self.insured_combo.addItem(m["name"], m["id"])
        ins_lay.addWidget(self.insured_combo)

        two_col = QHBoxLayout()
        two_col.setSpacing(12)
        self.coverage_spin = QDoubleSpinBox()
        self.coverage_spin.setRange(0, 1e15)
        self.coverage_spin.setDecimals(2)
        self.coverage_spin.setSingleStep(10000)
        self.coverage_spin.setSuffix(" ¥")
        self.coverage_spin.setMinimumHeight(40)
        self.premium_spin = QDoubleSpinBox()
        self.premium_spin.setRange(0, 1e15)
        self.premium_spin.setDecimals(2)
        self.premium_spin.setSingleStep(1000)
        self.premium_spin.setSuffix(" ¥")
        self.premium_spin.setMinimumHeight(40)
        cov_box = QVBoxLayout()
        cov_box.setSpacing(6)
        cov_lbl = QLabel("保额")
        cov_lbl.setObjectName("formLabel")
        cov_box.addWidget(cov_lbl)
        cov_box.addWidget(self.coverage_spin)
        prem_box = QVBoxLayout()
        prem_box.setSpacing(6)
        prem_lbl = QLabel("年保费")
        prem_lbl.setObjectName("formLabel")
        prem_box.addWidget(prem_lbl)
        prem_box.addWidget(self.premium_spin)
        two_col.addLayout(cov_box)
        two_col.addLayout(prem_box)
        ins_lay.addLayout(two_col)
        form.addRow("", self.ins_field)

        # 估值（标签动态切换 当前估值 / 现金价值）
        self.value_label = QLabel("当前估值")
        self.value_label.setObjectName("formLabel")
        self.value_spin = QDoubleSpinBox()
        self.value_spin.setRange(0, 1e15)
        self.value_spin.setDecimals(2)
        self.value_spin.setSingleStep(10000)
        self.value_spin.setMinimumHeight(40)
        form.addRow(self.value_label, self.value_spin)
        self.value_hint = QLabel("保障型保险是风险保障，无市场估值，现金价值固定为 0，不计入总资产")
        self.value_hint.setObjectName("formHint")
        self.value_hint.setProperty("warn", "true")
        self.value_hint.setWordWrap(True)
        self.value_hint.setMinimumHeight(40)
        self.value_hint.setVisible(False)
        form.addRow("", self.value_hint)

        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("选填")
        self.note_edit.setMinimumHeight(40)
        form.addRow(self._labeled("备注"), self.note_edit)

        self.body_layout.addLayout(form)
        self.set_foot("取消", "保存", self._on_save)
        if asset:
            self._load(asset)
        else:
            self._on_type_changed()
        # 按 body 内容自适应高度（保险区块完整显示）
        self.resize_to_content()

    def _is_ins(self) -> bool:
        return self.type_combo.currentData() == "insurance"

    def _on_type_changed(self):
        is_ins = self._is_ins()
        self.ins_field.setVisible(is_ins)
        if is_ins:
            self.value_label.setText("现金价值")
        else:
            self.value_label.setText("当前估值")
            self.value_spin.setEnabled(True)
        self._on_subtype_changed()
        # 保险区块显隐切换后强制重新计算 sizeHint 并按内容自适应
        self.layout().invalidate()
        self.layout().activate()
        self.resize_to_content()

    def _select_subtype(self, sub: str):
        """手动互斥选中子类型；sub='' 表示都取消（未分类历史数据）。"""
        self.pill_protection.setChecked(sub == "protection")
        self.pill_savings.setChecked(sub == "savings")
        self._on_subtype_changed()

    def _on_subtype_changed(self):
        if not self._is_ins():
            return
        if self.pill_protection.isChecked():
            self.value_spin.setValue(0)
            self.value_spin.setEnabled(False)
            self.value_hint.setVisible(True)
            self.subtype_hint.setText("保障型保险不计入总资产，仅记录保额与年保费")
        else:
            self.value_spin.setEnabled(True)
            self.value_hint.setVisible(False)
            self.subtype_hint.setText("储蓄型保险按现金价值计入总资产")
        # value_hint 显隐切换后重新按内容自适应高度
        QTimer.singleShot(0, self.resize_to_content)

    def _load(self, asset: dict):
        self.name_edit.setText(asset["name"])
        idx = self.type_combo.findData(asset["type"])
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.value_spin.setValue(asset["value"] or 0)
        self.coverage_spin.setValue(asset.get("coverage") or 0)
        self.premium_spin.setValue(asset.get("annual_premium") or 0)
        if asset["purchase_date"]:
            from PySide6.QtCore import QDate
            d = QDate.fromString(asset["purchase_date"], "yyyy-MM-dd")
            if d.isValid():
                self.date_edit.setDate(d)
        self.note_edit.setText(asset["note"] or "")
        # 被保险人回填：未指定（None）→ 默认"与资产所有者相同"
        if asset.get("insured_member_id"):
            iidx = self.insured_combo.findData(asset["insured_member_id"])
            if iidx >= 0:
                self.insured_combo.setCurrentIndex(iidx)
        # 旧保险（无子类型）：pills 都不选中，提示用户选择；不清零原估值
        sub = asset.get("insurance_subtype")
        if sub == "protection":
            self._select_subtype("protection")
        elif sub == "savings":
            self._select_subtype("savings")
        else:
            self._select_subtype("")
            self.subtype_hint.setText("请选择保险子类型（历史数据未指定）")

    def _on_save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "资产名称不能为空")
            return
        is_ins = self._is_ins()
        subtype = None
        if is_ins:
            if self.pill_protection.isChecked():
                subtype = "protection"
            elif self.pill_savings.isChecked():
                subtype = "savings"
        self.result_data = {
            "name": name,
            "type": self.type_combo.currentData(),
            "value": self.value_spin.value(),
            "purchase_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "note": self.note_edit.text().strip() or None,
            "insurance_subtype": subtype,
            "coverage": (self.coverage_spin.value() or None) if is_ins else None,
            "annual_premium": (self.premium_spin.value() or None) if is_ins else None,
            "insured_member_id": self.insured_combo.currentData() if is_ins else None,
        }
        self.accept()


# ---------------------------------------------------------------------------
# 附件管理弹窗
# ---------------------------------------------------------------------------
class AttachmentsDialog(Modal):
    """资产附件管理弹窗：列表 + 上传/查看/删除。"""

    def __init__(self, asset: dict, parent=None):
        super().__init__(f"附件管理 — {asset['name']}", width=520, parent=parent)
        self.asset = asset

        self.list_widget = QListWidget()
        self.body_layout.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        self.upload_btn = make_button("上传附件", "primary")
        self.upload_btn.clicked.connect(self._upload)
        self.view_btn = make_button("查看附件", "ghost")
        self.view_btn.clicked.connect(self._view)
        self.del_btn = make_button("删除附件", "danger")
        self.del_btn.clicked.connect(self._delete)
        btn_row.addWidget(self.upload_btn)
        btn_row.addWidget(self.view_btn)
        btn_row.addWidget(self.del_btn)
        btn_row.addStretch()
        self.body_layout.addLayout(btn_row)

        self.set_foot(ok_text="关闭", on_ok=self.accept, ok_only=True)
        self._load()

    def _load(self):
        self.list_widget.clear()
        for att in asset_dao.list_attachments(self.asset["id"]):
            item = QListWidgetItem(f"{att['file_name']}  （{att['created_at']}）")
            item.setData(Qt.UserRole, att["id"])
            self.list_widget.addItem(item)

    def _selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "提示", "请先选择附件")
            return None
        return asset_dao.get_attachment(item.data(Qt.UserRole))

    def _upload(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择附件", "", "图片/PDF (*.jpg *.jpeg *.png *.pdf)"
        )
        if not paths:
            return
        att_dir = get_data_dir() / "attachments"
        att_dir.mkdir(parents=True, exist_ok=True)
        for src in paths:
            src_path = Path(src)
            ext = src_path.suffix.lower()
            if ext not in ALLOWED_EXT:
                QMessageBox.warning(self, "不支持", f"不支持的文件类型：{ext}")
                continue
            if src_path.stat().st_size > MAX_ATTACHMENT_SIZE:
                QMessageBox.warning(self, "文件过大", f"{src_path.name} 超过 20MB 限制")
                continue
            # 用 uuid 命名，避免同秒上传同名文件互相覆盖
            dest_name = f"{self.asset['id']}_{uuid4().hex}_{src_path.name}"
            try:
                shutil.copy2(src_path, att_dir / dest_name)
            except OSError as e:
                QMessageBox.warning(self, "复制失败", f"附件 {src_path.name} 保存失败：{e}")
                continue
            asset_dao.add_attachment(self.asset["id"], src_path.name, f"attachments/{dest_name}")
        self._load()

    def _view(self):
        att = self._selected()
        if att is None:
            return
        full = get_data_dir() / att["file_path"]
        if not full.exists():
            QMessageBox.warning(self, "提示", "附件文件不存在")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(full))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(full)])
            else:
                subprocess.Popen(["xdg-open", str(full)])
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _delete(self):
        att = self._selected()
        if att is None:
            return
        ret = QMessageBox.question(
            self, "确认删除", f"确定删除附件「{att['file_name']}」吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            full = get_data_dir() / att["file_path"]
            if full.exists():
                full.unlink()
            asset_dao.delete_attachment(att["id"])
            self._load()


# ---------------------------------------------------------------------------
# 资产页
# ---------------------------------------------------------------------------
class AssetsPage(PageBase):
    """资产台账页。"""

    def __init__(self, parent=None):
        super().__init__("资产台账", "管理房产、车辆、保险等非流动资产")
        self._type_filter = "all"
        # 各资产项附件数：每次刷新一次性取回，附件列渲染与排序键共用（避免逐行查 SQL）
        self._att_counts: dict[int, int] = {}
        self._build_content()
        self.refresh()

    def _build_content(self):
        update_btn = make_button("⟳ 更新估值", "ghost")
        update_btn.clicked.connect(self.refresh)
        self.add_action(update_btn)
        add_btn = make_button("+ 新增资产", "primary")
        add_btn.clicked.connect(self._add_asset)
        self.add_action(add_btn)

        body = self.body()

        # 保险口径说明 Banner（常驻，blue 变体）
        self.banner = Banner(
            "<b>保险估值口径说明：</b>保障型保险（医疗/意外/重疾等）是风险保障，<b>不计入总资产</b>，"
            "仅记录保额与年保费；储蓄型保险（年金/分红/万能险）按<b>现金价值</b>计入总资产。",
            "blue",
        )
        body.addWidget(self.banner)

        # 统计卡 4 张（与 HTML demo assets.html 1:1：hero + 房产/车辆/保险现金价值）
        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.card_total = StatCard("资产总估值", hero=True)
        self.card_real_estate = StatCard("房产")
        self.card_vehicle = StatCard("车辆")
        self.card_insurance = StatCard("保险现金价值")
        for c in (self.card_total, self.card_real_estate, self.card_vehicle, self.card_insurance):
            cards.addWidget(c, 1)
        body.addLayout(cards)

        # 筛选工具条（Chip + 计数）
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.type_chips = ChipGroup(ASSET_FILTERS, default="all")
        self.type_chips.changed.connect(self._on_type_changed)
        filter_row.addWidget(self.type_chips)
        filter_row.addStretch()
        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color:{theme.TEXT_3}; font-size:13px;")
        filter_row.addWidget(self.count_label)
        body.addLayout(filter_row)

        # 表格
        self.table = SortableTable(0, 10)
        self.table.setHorizontalHeaderLabels(
            ["名称", "类型", "保险子类型", "被保险人", "估值 / 现金价值", "保额", "年保费", "购置日期", "附件", "操作"]
        )
        setup_table(self.table, row_height=56)
        self.table.set_sortable_cols({0, 1, 2, 3, 4, 5, 6, 7, 8})  # 操作列(9)不可排序
        # 表头点击后由组件统一「延迟 + 合批」重建，无需页面自己接 sort_changed
        self.table.set_rebuild_fn(self._populate_table)
        body.addWidget(self.table, 1)

    # ------------------------------------------------------------------
    def refresh(self):
        assets = asset_dao.list_assets()
        self._update_stats(assets)
        self._update_count(assets)
        self._assets = assets
        self._populate_table()

    # ------------------------------------------------------------------
    # 表头排序
    # ------------------------------------------------------------------
    # 表头点击后的「延迟 + 合批重建」已下沉到 SortableTable
    # （见 __init__ 里的 set_rebuild_fn），页面只需提供排序键。

    def _asset_sort_key(self, col: int):
        """各列排序键（列范围：0名称/1类型/2子类型/3被保险人/4估值/5保额/6年保费/7日期/8附件数）。"""
        if col == 0:
            return lambda a: a["name"]
        if col == 1:
            return lambda a: type_label(constants.ASSET_TYPES, a["type"])
        if col == 2:
            return lambda a: (
                {"savings": "储蓄型", "protection": "保障型"}.get(a.get("insurance_subtype"), "未分类")
                if a["type"] == "insurance" else ""
            )
        if col == 3:
            return lambda a: a.get("insured_name") or ""
        if col == 4:
            return lambda a: a["value"] or 0.0
        if col == 5:
            return lambda a: a.get("coverage") or 0.0
        if col == 6:
            return lambda a: a.get("annual_premium") or 0.0
        if col == 7:
            return lambda a: a["purchase_date"] or ""  # ISO 日期字符串可直接比较
        if col == 8:
            # 用刷新时一次性取回的映射，避免排序时每行各查一次
            return lambda a: self._att_counts.get(a["id"], 0)
        return lambda a: ""

    def _populate_table(self):
        """按当前排序状态重建资产表格行（批量更新，减少重绘压力）。"""
        self.table.setUpdatesEnabled(False)
        try:
            # 一次性取回各资产附件数：附件列渲染与排序键共用，避免每行一次 SQL（N+1）
            self._att_counts = asset_dao.count_attachments_by_asset()
            filtered = self._assets if self._type_filter == "all" else [
                a for a in self._assets if a["type"] == self._type_filter]
            rows = sort_rows(filtered, self._asset_sort_key(self.table.current_sort_col()),
                             self.table.current_sort_order())
            self.table.setRowCount(0)
            for a in rows:
                row = self.table.rowCount()
                self.table.insertRow(row)

                self.table.setCellWidget(row, 0, double_line_widget(a["name"], a["note"] or None))
                self.table.setCellWidget(row, 1, tag_in_cell(
                    type_label(constants.ASSET_TYPES, a["type"]),
                    {"insurance": "gold", "precious_metal": "orange"}.get(a["type"], "blue"), 14))
                self.table.setCellWidget(row, 2, self._subtype_cell(a))
                self.table.setCellWidget(row, 3, self._insured_cell(a))

                # 估值 / 现金价值。保障型保险只放"¥0 + 不计入资产"控件，不能再
                # setItem——控件背景透明，底下 QTableWidgetItem 的 ¥0.00 会透出来
                # 造成重复显示
                if a["type"] == "insurance" and a.get("insurance_subtype") == "protection":
                    self.table.setCellWidget(row, 4, self._zero_with_note())
                else:
                    self.table.setItem(row, 4, money_item(f"¥{a['value']:,.2f}"))

                self.table.setItem(row, 5, money_item(f"¥{a['coverage']:,.0f}" if a.get("coverage") else "—", bold=False))
                self.table.setItem(row, 6, money_item(f"¥{a['annual_premium']:,.0f}" if a.get("annual_premium") else "—", bold=False))
                self.table.setItem(row, 7, cell_item(a["purchase_date"] or "—"))
                self.table.setCellWidget(row, 8, self._attach_cell(a))

                cell = ActionCell(
                    "编辑", lambda _=False, x=a: self._edit_asset(x),
                    more_items=[
                        ("查看附件", lambda _=False, x=a: self._show_attachments(x)),
                        ("删除", lambda _=False, x=a: self._delete_asset(x), "danger"),
                    ],
                )
                self.table.setCellWidget(row, 9, cell)
            autofit_columns(self.table)
        finally:
            self.table.setUpdatesEnabled(True)

        if not self._assets:
            self.show_empty("还没有资产", "记录房产、车辆、保险等非流动资产", "+ 新增资产", self._add_asset)
        else:
            self.hide_empty()

    def _subtype_cell(self, a) -> QWidget:
        if a["type"] != "insurance":
            return tag_in_cell("—", "gray", 14)
        sub = a.get("insurance_subtype")
        if sub == "savings":
            return tag_in_cell("储蓄型", "blue", 14)
        if sub == "protection":
            return tag_in_cell("保障型", "gray", 14)
        return tag_in_cell("未分类", "orange", 14)

    def _insured_cell(self, a) -> QWidget:
        """被保险人列：保险类直接显示成员名，非保险/未指定显示 —。"""
        if a["type"] != "insurance" or not a.get("insured_name"):
            return tag_in_cell("—", "gray", 14)
        return tag_in_cell(a["insured_name"], "blue", 14)

    def _zero_with_note(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(6)
        val = QLabel("¥0")
        val.setStyleSheet(f"color:{theme.TEXT}; font-size:14px; font-weight:600;")
        lay.addWidget(val)
        lay.addWidget(make_tag("不计入资产", "orange"))
        lay.addStretch()
        return w

    def _attach_cell(self, a) -> QWidget:
        count = self._att_counts.get(a["id"], 0)
        if count == 0:
            return tag_in_cell("—", "gray", 14)
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(6)
        ico = QLabel()
        ico.setPixmap(svg_to_icon(theme.icon("paperclip", theme.TEXT_2, 14), 14).pixmap(14, 14))
        lay.addWidget(ico)
        num = QLabel(str(count))
        num.setStyleSheet(f"color:{theme.TEXT_2}; font-size:12.5px;")
        lay.addWidget(num)
        lay.addStretch()
        return w

    def _update_stats(self, assets: list[dict]):
        total = report_service._asset_ledger_value(assets)
        buckets = {"real_estate": 0.0, "vehicle": 0.0, "insurance": 0.0, "precious_metal": 0.0, "other": 0.0}
        counts: dict[str, int] = {}
        for a in assets:
            if report_service._is_protection_insurance(a):
                continue
            key = a["type"] if a["type"] in buckets else "other"
            buckets[key] += a["value"] or 0
            counts[key] = counts.get(key, 0) + 1
        self.card_total.set_value(total)
        self.card_total.set_sub("不含保障型保险（保额仅作保障记录）")

        def pct(v): return f"{(v / total * 100) if total else 0:.1f}%"

        self.card_real_estate.set_value(buckets.get("real_estate", 0.0))
        self.card_real_estate.set_sub(f"{counts.get('real_estate', 0)} 项 · 占比 {pct(buckets.get('real_estate', 0.0))}")
        self.card_vehicle.set_value(buckets.get("vehicle", 0.0))
        self.card_vehicle.set_sub(f"{counts.get('vehicle', 0)} 项 · 占比 {pct(buckets.get('vehicle', 0.0))}")
        # 保险：储蓄型份数 / 保障型份数
        savings = sum(1 for a in assets if a["type"] == "insurance" and a.get("insurance_subtype") == "savings")
        protection = sum(1 for a in assets if a["type"] == "insurance" and a.get("insurance_subtype") == "protection")
        self.card_insurance.set_value(buckets.get("insurance", 0.0))
        self.card_insurance.set_sub(f"储蓄型 {savings} 份 · 保障型 {protection} 份")

    def _update_count(self, assets: list[dict]):
        policies = sum(1 for a in assets if a["type"] == "insurance")
        self.count_label.setText(f"共 {len(assets)} 项资产 · {policies} 份保单")

    def _on_type_changed(self, key):
        self._type_filter = key
        self.refresh()

    # ------------------------------------------------------------------
    def _add_asset(self):
        dlg = AssetDialog(parent=self)
        if dlg.exec():
            d = dlg.result_data
            asset_dao.create_asset(
                d["name"], d["type"], d["value"], d["purchase_date"], d["note"],
                d["insurance_subtype"], d["coverage"], d["annual_premium"],
                d["insured_member_id"],
            )
            self.refresh()
            self.data_changed.emit()

    def _edit_asset(self, a):
        dlg = AssetDialog(a, parent=self)
        if dlg.exec():
            d = dlg.result_data
            asset_dao.update_asset(
                a["id"], d["name"], d["type"], d["value"], d["purchase_date"], d["note"],
                d["insurance_subtype"], d["coverage"], d["annual_premium"],
                d["insured_member_id"],
            )
            self.refresh()
            self.data_changed.emit()

    def _delete_asset(self, a):
        ret = QMessageBox.question(
            self, "确认删除", f"确定删除资产「{a['name']}」吗？其附件也将一并删除。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            for att in asset_dao.list_attachments(a["id"]):
                p = get_data_dir() / att["file_path"]
                if p.exists():
                    p.unlink()
            asset_dao.delete_asset(a["id"])
            self.refresh()
            self.data_changed.emit()

    def _show_attachments(self, a):
        dlg = AttachmentsDialog(a, parent=self)
        dlg.exec()
        self.refresh()

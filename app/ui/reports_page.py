"""报表页（v2.0，UI 设计规范 4.7）。

topbar：标题 + 时间范围 Chip（整个页面共用）。
内容：4 统计卡（期末净资产 / 期间净资产变动+幅度 / 期末总资产 / 期末总负债）
    → 净资产趋势卡 → 左右两列：资产构成卡（当前口径）+ 负债构成条形图卡（含期间还款汇总）
    → 快照明细表卡（日期/总资产/总负债/净资产/环比，可导出 CSV）。
语义色：净资产变动 增加=绿 / 减少=红（与资产负债语义一致）。

与总览页的分工（v2.2 差异化）：总览="现在怎么样"（当下状态 + 关注提醒），
本页="一段时间以来怎么样"（期间对比 + 趋势 + 数字明细）。
"""
from __future__ import annotations

import csv
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QTableWidget, QVBoxLayout, QWidget,
)

from app.dao import liability_dao, snapshot_dao
from app.services import report_service
from app.ui import theme
from app.ui.page_base import PageBase
from app.ui.widgets.base_table import autofit_columns, cell_item, money_item, setup_table
from app.ui.widgets.button import make_button
from app.ui.widgets.charts import DonutChart, TrendChart
from app.ui.widgets.chip import ChipGroup
from app.ui.widgets.layout_util import clear_layout
from app.ui.widgets.stat_card import StatCard

RANGES = [("1m", "近1月"), ("3m", "近3月"), ("6m", "近6月"), ("1y", "近1年"), ("all", "全部")]


class ReportsPage(PageBase):
    """报表页。"""

    def __init__(self, parent=None):
        super().__init__("报表", "家庭资产统计与分布")
        self._range = "6m"
        self._dimension = "account"
        self._build_content()
        self.refresh()

    def _build_content(self):
        # ---- topbar：时间范围 Chip ----
        self.range_chips = ChipGroup(RANGES, default="6m")
        self.range_chips.changed.connect(self._on_range_changed)
        self.add_action(self.range_chips)

        body = self.body()

        # ---- 4 统计卡 ----
        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.card_net_end = StatCard("期末净资产")
        self.card_net_change = StatCard("期间净资产变动")
        self.card_assets_end = StatCard("期末总资产")
        self.card_liab_end = StatCard("期末总负债")
        for c in (self.card_net_end, self.card_net_change, self.card_assets_end, self.card_liab_end):
            cards.addWidget(c, 1)
        body.addLayout(cards)

        # ---- 趋势卡 ----
        trend_card = QFrame()
        trend_card.setObjectName("card")
        t_lay = QVBoxLayout(trend_card)
        t_lay.setContentsMargins(theme.CARD_PADDING, 16, theme.CARD_PADDING, 16)
        t_lay.setSpacing(10)
        t_head = QHBoxLayout()
        title = QLabel("净资产趋势")
        title.setObjectName("panelTitle")
        t_head.addWidget(title)
        t_head.addStretch()
        t_lay.addLayout(t_head)
        self.trend = TrendChart()
        t_lay.addWidget(self.trend)
        body.addWidget(trend_card, 1)

        # ---- 底部两列 ----
        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        # 资产构成（当前口径——快照表无分类结构历史，本卡不随时间范围联动，标题明示）
        dist_card = QFrame()
        dist_card.setObjectName("card")
        d_lay = QVBoxLayout(dist_card)
        d_lay.setContentsMargins(theme.CARD_PADDING, 16, theme.CARD_PADDING, 16)
        d_lay.setSpacing(10)
        d_head = QHBoxLayout()
        d_title = QLabel("资产构成（当前）")
        d_title.setObjectName("panelTitle")
        d_head.addWidget(d_title)
        d_head.addStretch()
        self.dim_chips = ChipGroup(
            [("account", "按账户类型"), ("class", "按资产大类"),
             ("member", "按持有人"), ("liquidity", "按流动性")],
            default="account",
        )
        self.dim_chips.changed.connect(self._on_dim_changed)
        d_head.addWidget(self.dim_chips)
        d_lay.addLayout(d_head)
        self.donut = DonutChart()
        d_lay.addWidget(self.donut)
        bottom.addWidget(dist_card, 1)

        # 负债构成（横向条形 + 期间还款汇总）
        liab_card = QFrame()
        liab_card.setObjectName("card")
        l_lay = QVBoxLayout(liab_card)
        l_lay.setContentsMargins(theme.CARD_PADDING, 16, theme.CARD_PADDING, 16)
        l_lay.setSpacing(12)
        l_head = QHBoxLayout()
        l_title = QLabel("负债构成")
        l_title.setObjectName("panelTitle")
        l_head.addWidget(l_title)
        l_head.addStretch()
        self.repay_summary_label = QLabel("")
        self.repay_summary_label.setStyleSheet(f"color:{theme.TEXT_3}; font-size:12px;")
        l_head.addWidget(self.repay_summary_label)
        l_lay.addLayout(l_head)
        self.liab_box = QVBoxLayout()
        self.liab_box.setSpacing(10)
        l_lay.addLayout(self.liab_box)
        l_lay.addStretch()
        bottom.addWidget(liab_card, 1)

        body.addLayout(bottom)

        # ---- 快照明细卡（数字明细 + CSV 导出）----
        detail_card = QFrame()
        detail_card.setObjectName("card")
        dt_lay = QVBoxLayout(detail_card)
        dt_lay.setContentsMargins(theme.CARD_PADDING, 16, theme.CARD_PADDING, 16)
        dt_lay.setSpacing(10)
        dt_head = QHBoxLayout()
        dt_title = QLabel("快照明细")
        dt_title.setObjectName("panelTitle")
        dt_head.addWidget(dt_title)
        dt_head.addStretch()
        export_btn = make_button("导出 CSV", "ghost")
        export_btn.clicked.connect(self._export_csv)
        dt_head.addWidget(export_btn)
        dt_lay.addLayout(dt_head)
        self.snap_table = QTableWidget(0, 5)
        self.snap_table.setHorizontalHeaderLabels(
            ["日期", "总资产", "总负债", "净资产", "净资产环比"])
        setup_table(self.snap_table, row_height=40)
        dt_lay.addWidget(self.snap_table, 1)
        body.addWidget(detail_card, 1)

    # ------------------------------------------------------------------
    def refresh(self):
        snaps = self._snapshots()
        self._update_cards(snaps)
        self._update_trend(snaps)
        self._update_donut()
        self._update_liab()
        self._update_snapshots(snaps)

    def _on_range_changed(self, key):
        self._range = key
        self.refresh()

    def _on_dim_changed(self, key):
        self._dimension = key
        self._update_donut()

    # ------------------------------------------------------------------
    def _snapshots(self):
        return report_service.get_trend(self._range)

    def _update_cards(self, snaps: list[dict]):
        if len(snaps) >= 2:
            first, last = snaps[0], snaps[-1]
            self.card_net_end.set_value(last["net_worth"])
            change = last["net_worth"] - first["net_worth"]
            self.card_net_change.set_value(change)
            if change >= 0:
                self.card_net_change.value_widget.setStyleSheet(
                    f"font-size:24px; font-weight:700; color:{theme.GREEN};")
            else:
                self.card_net_change.value_widget.setStyleSheet(
                    f"font-size:24px; font-weight:700; color:{theme.RED};")
            self.card_net_change.set_sub(
                f"{self._range_label()} 变动{self._change_pct_text(first['net_worth'], change)}")
            self.card_assets_end.set_value(last["total_assets"])
            self.card_liab_end.set_value(last["total_liabilities"])
        else:
            t = report_service.calc_totals()
            self.card_net_end.set_value(t["net_worth"])
            self.card_net_change.value_widget.setText("—")
            self.card_net_change.set_sub("数据不足")
            self.card_assets_end.set_value(t["total_assets"])
            self.card_liab_end.set_value(t["total_liabilities"])

    @staticmethod
    def _change_pct_text(base: float, change: float) -> str:
        """期间变动幅度；基期为 0 时百分比无意义，不显示。"""
        if not base:
            return ""
        return f" · {change / abs(base) * 100:+.1f}%"

    def _range_label(self) -> str:
        return dict(RANGES).get(self._range, "期间")

    def _update_trend(self, snaps: list[dict]):
        self.trend.set_data(snaps)

    def _update_donut(self):
        if self._dimension == "account":
            data = report_service.distribution_by_account_type()
        elif self._dimension == "class":
            data = report_service.distribution_by_asset_class()
        elif self._dimension == "member":
            data = report_service.distribution_by_member()
        else:
            data = report_service.distribution_by_liquidity()
        self.donut.set_data(data)

    def _update_liab(self):
        """负债构成横向条形（各负债 remaining + 已还比例）+ 期间还款汇总。"""
        cnt, repaid = liability_dao.repay_summary_since(report_service.range_start(self._range))
        self.repay_summary_label.setText(f"期间已还款 ¥{repaid:,.0f} · {cnt} 笔" if cnt else "")

        clear_layout(self.liab_box)
        liabilities = [l for l in liability_dao.list_liabilities() if (l["remaining"] or 0) > 0]
        if not liabilities:
            tip = QLabel("暂无负债")
            tip.setStyleSheet(f"color:{theme.TEXT_3}; font-size:13px;")
            self.liab_box.addWidget(tip)
            return
        max_amt = max(l["remaining"] for l in liabilities) or 1
        for i, liab in enumerate(liabilities):
            total_amt = liab["total_amount"] or 0
            remaining = liab["remaining"] or 0
            repaid_pct = max(0.0, min(100.0, (total_amt - remaining) / total_amt * 100)) if total_amt else 0.0
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(10)
            name = QLabel(liab["name"])
            name.setFixedWidth(110)
            name.setStyleSheet(f"color:{theme.TEXT_2}; font-size:13px;")
            lay.addWidget(name)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(liab["remaining"] / max_amt * 100))
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            # 蓝色系深浅区分
            alpha = 0.55 + 0.45 * (i % 4) / 3
            bar.setStyleSheet(
                f"QProgressBar{{ background:#EEF1F5; border:none; border-radius:4px; }}"
                f"QProgressBar::chunk{{ background:rgba(0,100,230,{alpha}); border-radius:4px; }}"
            )
            lay.addWidget(bar, 1)
            # 右列两行：剩余金额 + 已还比例
            amt_box = QVBoxLayout()
            amt_box.setSpacing(0)
            amt = QLabel(f"¥{liab['remaining']:,.0f}")
            amt.setFixedWidth(100)
            amt.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amt.setStyleSheet(f"color:{theme.TEXT_2}; font-size:12px;")
            sub = QLabel(f"已还 {repaid_pct:.0f}%")
            sub.setFixedWidth(100)
            sub.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sub.setStyleSheet(f"color:{theme.TEXT_3}; font-size:11px;")
            amt_box.addWidget(amt)
            amt_box.addWidget(sub)
            lay.addLayout(amt_box)
            self.liab_box.addWidget(row)

    # ------------------------------------------------------------------
    def _update_snapshots(self, snaps: list[dict]):
        """快照明细表：日期/总资产/总负债/净资产/环比（基期为范围内首条的前一条快照）。"""
        self.snap_table.setUpdatesEnabled(False)
        try:
            self.snap_table.setRowCount(0)
            prev = None
            if snaps:
                prev = snapshot_dao.get_snapshot_before(
                    snaps[0]["snapshot_date"], inclusive=False)
            for s in snaps:
                row = self.snap_table.rowCount()
                self.snap_table.insertRow(row)
                self.snap_table.setItem(row, 0, cell_item(s["snapshot_date"]))
                self.snap_table.setItem(row, 1, money_item(f"{s['total_assets']:,.2f}", bold=False))
                self.snap_table.setItem(row, 2, money_item(f"{s['total_liabilities']:,.2f}", bold=False))
                self.snap_table.setItem(row, 3, money_item(f"{s['net_worth']:,.2f}"))
                self.snap_table.setItem(row, 4, self._delta_item(prev, s))
                prev = s
            autofit_columns(self.snap_table)
        finally:
            self.snap_table.setUpdatesEnabled(True)

    @staticmethod
    def _delta_text(prev: dict | None, snap: dict) -> str:
        """净资产环比文案；无基期或基期为 0 时显示 —。"""
        if prev is None:
            return "—"
        base = prev["net_worth"] or 0
        if not base:
            return "—"
        return f"{(snap['net_worth'] - base) / abs(base) * 100:+.2f}%"

    def _delta_item(self, prev: dict | None, snap: dict):
        text = self._delta_text(prev, snap)
        if prev is None or text == "—":
            return cell_item("—", Qt.AlignRight | Qt.AlignVCenter)
        delta = snap["net_worth"] - (prev["net_worth"] or 0)
        color = theme.GREEN if delta >= 0 else theme.RED
        return money_item(text, color, bold=False)

    def _export_csv(self):
        """导出当前时间范围的快照明细为 CSV（UTF-8 BOM，Excel 直接打开不乱码）。"""
        snaps = self._snapshots()
        if not snaps:
            QMessageBox.information(self, "提示", "当前时间范围内没有快照数据")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出快照明细",
            f"anhang_snapshots_{datetime.now():%Y%m%d}.csv", "CSV (*.csv)",
        )
        if not path:
            return
        try:
            self._write_snapshots_csv(path, snaps)
        except OSError as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        QMessageBox.information(self, "完成", f"快照明细已导出到：\n{path}")

    def _write_snapshots_csv(self, path: str, snaps: list[dict]) -> None:
        prev = snapshot_dao.get_snapshot_before(snaps[0]["snapshot_date"], inclusive=False)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["日期", "总资产", "总负债", "净资产", "净资产环比"])
            for s in snaps:
                w.writerow([
                    s["snapshot_date"],
                    f"{s['total_assets']:.2f}",
                    f"{s['total_liabilities']:.2f}",
                    f"{s['net_worth']:.2f}",
                    self._delta_text(prev, s),
                ])
                prev = s

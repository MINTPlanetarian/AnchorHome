"""总览页（v2.0，UI 设计规范 4.2）。

topbar：标题"总览" + 成员切换 Chip + 记录今日快照 / 刷新行情。
内容：到期提醒 Banner → 4 统计卡（总资产 hero）→ 净资产趋势卡（时间 Chip + 三线图）
    → 底部两列：资产分布环形图卡（4 维度）+ 快捷信息卡。
空状态：无任何账户时整页 EmptyState。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app import config
from app.dao import account_dao, asset_dao, member_dao, snapshot_dao
from app.services import report_service
from app.utils import today_str
from app.ui import theme
from app.ui.page_base import PageBase
from app.ui.widgets.banner import Banner
from app.ui.widgets.button import make_button
from app.ui.widgets.charts import DonutChart, TrendChart
from app.ui.widgets.chip import ChipGroup
from app.ui.widgets.icon import nav_icon, svg_to_icon
from app.ui.widgets.layout_util import clear_layout
from app.ui.widgets.stat_card import StatCard


class OverviewPage(PageBase):
    """家庭资产总览。"""

    # 请求主窗口切换页面 / 刷新行情（替代直接摸主窗口私有成员 _pages/_stack/_refresh_market）
    navigate_request = Signal(str)
    market_refresh_request = Signal()

    def __init__(self, parent=None):
        super().__init__("总览", "家庭资产全景")
        self._member_id = None
        self._dimension = "account"
        self._build_content()
        self.refresh()

    # ------------------------------------------------------------------
    def _build_content(self):
        # ---- topbar 操作 ----
        self.member_chips = ChipGroup([("all", "全部")], default="all")
        self.member_chips.changed.connect(self._on_member_changed)
        self.add_action(self.member_chips)

        snap_btn = make_button("记录今日快照", "ghost")
        snap_btn.clicked.connect(self._take_snapshot)
        self.add_action(snap_btn)

        refresh_btn = make_button("⟳ 刷新行情", "ghost")
        refresh_btn.clicked.connect(self._refresh_market)
        self.add_action(refresh_btn)

        body = self.body()

        # ---- 到期提醒 Banner ----
        self.notice = Banner("", "orange", closable=True)
        self.notice.close_btn.clicked.connect(self._dismiss_notice)
        self.notice.setVisible(False)
        body.addWidget(self.notice)

        # ---- 统计卡 ----
        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self.card_assets = StatCard("总资产", hero=True)
        self.card_liab = StatCard("总负债")
        self.card_net = StatCard("净资产")
        self.card_liquid = StatCard("可用资金")
        for c in (self.card_assets, self.card_liab, self.card_net, self.card_liquid):
            cards_row.addWidget(c, 1)
        body.addLayout(cards_row)

        # ---- 趋势卡 ----
        trend_card = QFrame()
        trend_card.setObjectName("card")
        trend_lay = QVBoxLayout(trend_card)
        trend_lay.setContentsMargins(theme.CARD_PADDING, 16, theme.CARD_PADDING, 16)
        trend_lay.setSpacing(10)

        trend_head = QHBoxLayout()
        # T1：总览只保留"近 30 天"迷你趋势，完整时间轴分析归报表页
        trend_title = QLabel("净资产趋势 · 近 30 天")
        trend_title.setObjectName("panelTitle")
        trend_head.addWidget(trend_title)
        trend_head.addStretch()
        trend_lay.addLayout(trend_head)

        self.trend = TrendChart()
        trend_lay.addWidget(self.trend)
        body.addWidget(trend_card, 1)

        # ---- 底部两列 ----
        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        # 资产分布卡
        dist_card = QFrame()
        dist_card.setObjectName("card")
        dist_lay = QVBoxLayout(dist_card)
        dist_lay.setContentsMargins(theme.CARD_PADDING, 16, theme.CARD_PADDING, 16)
        dist_lay.setSpacing(10)
        dist_head = QHBoxLayout()
        dist_title = QLabel("资产分布")
        dist_title.setObjectName("panelTitle")
        dist_head.addWidget(dist_title)
        dist_head.addStretch()
        self.dim_chips = ChipGroup(
            [("account", "按账户类型"), ("class", "按资产大类"),
             ("member", "按持有人"), ("liquidity", "按流动性")],
            default="account",
        )
        self.dim_chips.changed.connect(self._on_dim_changed)
        dist_head.addWidget(self.dim_chips)
        dist_lay.addLayout(dist_head)
        self.donut = DonutChart()
        dist_lay.addWidget(self.donut)
        bottom.addWidget(dist_card, 1)

        # 快捷信息卡
        quick_card = QFrame()
        quick_card.setObjectName("card")
        quick_lay = QVBoxLayout(quick_card)
        quick_lay.setContentsMargins(theme.CARD_PADDING, 16, theme.CARD_PADDING, 16)
        quick_lay.setSpacing(10)
        quick_title = QLabel("关注提醒")
        quick_title.setObjectName("panelTitle")
        quick_lay.addWidget(quick_title)
        self.quick_box = QVBoxLayout()
        self.quick_box.setSpacing(10)
        quick_lay.addLayout(self.quick_box)
        quick_lay.addStretch()
        bottom.addWidget(quick_card, 1)

        body.addLayout(bottom)

    # ------------------------------------------------------------------
    def refresh(self):
        # 成员列表可能变化 → 重建成员 Chip（保留当前选中）
        self._sync_member_chips()
        t = report_service.calc_totals(self._member_id)
        self._apply_totals(t)
        self._apply_week_compare(t)
        self._update_trend()
        self._update_donut()
        self._update_notice()
        self._update_quick()

        # 空状态：无账户时整页空状态
        if not account_dao.list_accounts():
            self.show_empty(
                "还没有账户",
                "先从账户开始，记录你的现金、理财、股票与基金",
                "+ 新增账户",
                self._goto_accounts,
            )
        else:
            self.hide_empty()

    def _goto_accounts(self):
        """引导到账户页（由主窗口连接 navigate_request 处理）。"""
        self.navigate_request.emit("accounts")

    def _sync_member_chips(self):
        """同步成员 Chip：保留当前 _member_id 对应的选中，避免每次 refresh 都被重置。"""
        items = [("all", "全部")]
        for m in member_dao.list_members():
            items.append((f"m{m['id']}", m["name"]))
        if self._member_id is None:
            default = "all"
        else:
            default = f"m{self._member_id}"
            if default not in [k for k, _ in items]:
                default = "all"  # 成员已删除则回退
        self.member_chips.rebuild(items, default=default)
        # 重建后 re-derive _member_id（rebuild 不发 changed 信号，需要手动同步）
        self._member_id = self._resolve_member()

    def _resolve_member(self):
        key = self.member_chips.current_key()
        if key == "all":
            return None
        return int(key[1:])

    def _on_member_changed(self, _key):
        self._member_id = self._resolve_member()
        t = report_service.calc_totals(self._member_id)
        self._apply_totals(t)
        self._apply_week_compare(t)
        self._update_donut()

    def _on_dim_changed(self, key):
        self._dimension = key
        self._update_donut()

    def _apply_totals(self, t: dict):
        self.card_assets.set_value(t["total_assets"])
        self.card_liab.set_value(t["total_liabilities"])
        self.card_net.set_value(t["net_worth"])
        self.card_liquid.set_value(t["liquid_funds"])
        if t["locked_funds"] > 0:
            self.card_liquid.set_sub(
                f"另有 ¥{t['locked_funds']:,.2f} 锁定，最近一笔 {t['next_unlock_date']} 可用"
            )
        else:
            self.card_liquid.set_sub("")

    def _apply_week_compare(self, t: dict):
        """总资产/净资产卡副行：与最近一条 ≥7 天前的快照对比（T2 轻量环比）。

        快照是家庭口径，成员视图没有对应历史，不显示对比。
        """
        for card in (self.card_assets, self.card_net):
            card.set_sub("")
        if self._member_id is not None:
            return
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        base = snapshot_dao.get_snapshot_before(cutoff, inclusive=True)
        if base is None:
            return
        self.card_assets.set_sub(self._compare_text(base["total_assets"], t["total_assets"]))
        self.card_net.set_sub(self._compare_text(base["net_worth"], t["net_worth"]))

    @staticmethod
    def _compare_text(base: float, current: float) -> str:
        """生成"较 7 日前 ±变化"文案；无基期（无快照）返回空串不显示。"""
        try:
            base = float(base or 0)
        except (TypeError, ValueError):
            return ""
        diff = current - base
        if base:
            pct = diff / abs(base) * 100
            return f"较 7 日前 {diff:+,.0f}（{pct:+.1f}%）"
        if diff:  # 基期为 0：百分比无意义，退回绝对额
            return f"较 7 日前 {diff:+,.0f}"
        return ""

    def _update_trend(self):
        self.trend.set_data(report_service.get_trend("1m"))

    def _update_donut(self):
        if self._dimension == "account":
            data = report_service.distribution_by_account_type(self._member_id)
        elif self._dimension == "class":
            data = report_service.distribution_by_asset_class(self._member_id)
        elif self._dimension == "member":
            data = report_service.distribution_by_member()
        else:
            data = report_service.distribution_by_liquidity(self._member_id)
        self.donut.set_data(data)

    # ------------------------------------------------------------------
    def _update_notice(self):
        """7 天内到期（含已过期）理财提醒；当天关闭后不再显示。"""
        if config.get_setting("maturity_notice_dismissed", "") == today_str():
            self.notice.setVisible(False)
            return
        maturing = account_dao.list_maturing(days=7)
        if not maturing:
            self.notice.setVisible(False)
            return
        today = today_str()
        parts = []
        for acc in maturing:
            avail = acc["available_date"]
            if avail <= today:
                days_ago = (datetime.strptime(today, "%Y-%m-%d")
                            - datetime.strptime(avail, "%Y-%m-%d")).days
                parts.append(f"“{acc['name']}”（¥{acc['balance']:,.0f}）已于 {days_ago} 天前到期可用")
            else:
                parts.append(f"“{acc['name']}”（¥{acc['balance']:,.0f}）将于 {avail} 可用")
        self.notice.set_text("；".join(parts))
        self.notice.setVisible(True)

    def _dismiss_notice(self):
        config.set_setting("maturity_notice_dismissed", today_str())
        self.notice.setVisible(False)

    def _update_quick(self):
        """关注提醒：理财到期 + 估值滞后资产，让总览承担"今天该关注什么"。

        行内容是 addLayout 加进去的嵌套布局，必须递归清理，否则旧行会泄漏。
        """
        clear_layout(self.quick_box)
        sections = 0

        # ① 30 天内到期（含已过期）的理财
        maturing = account_dao.list_maturing(days=30)
        if maturing:
            sections += 1
            self.quick_box.addWidget(self._section_label("理财到期（30 天内）"))
            for acc in maturing[:5]:
                row = QHBoxLayout()
                row.setSpacing(8)
                icon = QLabel()
                icon.setPixmap(svg_to_icon(theme.icon("bell", theme.ORANGE, 15), 15).pixmap(15, 15))
                row.addWidget(icon)
                text = QLabel(f"{acc['name']}  ¥{acc['balance']:,.0f}")
                text.setStyleSheet(f"color:{theme.TEXT_2}; font-size:13px;")
                row.addWidget(text)
                row.addStretch()
                date = QLabel(str(acc["available_date"]))
                date.setStyleSheet(f"color:{theme.TEXT_3}; font-size:12px;")
                row.addWidget(date)
                self.quick_box.addLayout(row)

        # ② 估值超过 90 天未更新的资产台账项（保障型保险无现金价值，不提醒）
        stale = self._stale_assets()
        if stale:
            sections += 1
            self.quick_box.addWidget(self._section_label("估值超 90 天未更新"))
            for asset, days in stale[:5]:
                row = QHBoxLayout()
                row.setSpacing(8)
                icon = QLabel()
                icon.setPixmap(svg_to_icon(theme.icon("info", theme.TEXT_3, 15), 15).pixmap(15, 15))
                row.addWidget(icon)
                text = QLabel(f"{asset['name']}  ¥{asset['value'] or 0:,.0f}")
                text.setStyleSheet(f"color:{theme.TEXT_2}; font-size:13px;")
                row.addWidget(text)
                row.addStretch()
                days_label = QLabel(f"{days} 天未更新")
                days_label.setStyleSheet(f"color:{theme.TEXT_3}; font-size:12px;")
                row.addWidget(days_label)
                self.quick_box.addLayout(row)
            if len(stale) > 5:
                more = QLabel(f"另有 {len(stale) - 5} 项…")
                more.setStyleSheet(f"color:{theme.TEXT_3}; font-size:12px;")
                self.quick_box.addWidget(more)
            link = QLabel(
                f'<a href="#assets" style="color:{theme.BLUE}; font-size:12px;'
                f' text-decoration:none;">去资产页更新估值 →</a>'
            )
            link.linkActivated.connect(lambda _=None: self.navigate_request.emit("assets"))
            self.quick_box.addWidget(link)

        if sections == 0:
            tip = QLabel("暂无需要关注的事项")
            tip.setStyleSheet(f"color:{theme.TEXT_3}; font-size:13px;")
            self.quick_box.addWidget(tip)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{theme.TEXT_3}; font-size:12px; font-weight:600;")
        return lab

    @staticmethod
    def _stale_assets() -> list[tuple[dict, int]]:
        """估值滞后资产：updated_at 距今超 90 天，按滞后天数降序。"""
        out: list[tuple[dict, int]] = []
        now = datetime.now()
        for a in asset_dao.list_assets():
            if a["type"] == "insurance" and a.get("insurance_subtype") == "protection":
                continue
            try:
                updated = datetime.strptime((a.get("updated_at") or "")[:10], "%Y-%m-%d")
            except ValueError:
                continue  # 脏时间戳不参与提醒
            days = (now - updated).days
            if days > 90:
                out.append((a, days))
        out.sort(key=lambda item: item[1], reverse=True)
        return out

    # ------------------------------------------------------------------
    def _take_snapshot(self):
        report_service.take_daily_snapshot()
        self.refresh()
        self.data_changed.emit()

    def _refresh_market(self):
        """把刷新行情请求转给主窗口统一处理。"""
        self.market_refresh_request.emit()

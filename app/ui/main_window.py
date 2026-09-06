"""主窗口（v2.0）：Sidebar(232px) + 内容区(QStackedWidget 8 页) + Statusbar(34px)。

UI 设计规范第 2 章：
    - 侧边栏：Logo + 8 个导航（总览/成员/账户/资产/负债/报表/AI助手 + 底部"设置"），
      内联 SVG 线性图标，激活态蓝底蓝字；
    - 每页自带 Topbar（PageBase）；
    - 状态栏：左"数据已自动保存 · 本机存储，密码保护"，右行情状态 + 上次备份时间。

职责：组装页面、行情启动/定时刷新、数据变更联动、设置变更联动。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from app import config
from app.services import report_service
from app.dao import holding_dao
from app.ui import theme
from app.ui.styles import APP_QSS
from app.ui.widgets.icon import find_app_icon, logo_pixmap, nav_icon
from app.ui.market_refresh import start_market_refresh
from app.ui.thread_helper import stop_all_threads
from app.ui.overview_page import OverviewPage
from app.ui.members_page import MembersPage
from app.ui.accounts_page import AccountsPage
from app.ui.assets_page import AssetsPage
from app.ui.liabilities_page import LiabilitiesPage
from app.ui.reports_page import ReportsPage
from app.ui.ai_chat_page import AiChatPage
from app.ui.settings_page import SettingsPage


class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("安航家资 · 家庭资产管理")
        self.resize(theme.WIN_W, theme.WIN_H)
        self.setMinimumSize(theme.WIN_MIN_W, theme.WIN_MIN_H)
        self.setStyleSheet(APP_QSS)

        self._build_ui()
        self._connect_signals()

        report_service.take_daily_snapshot()
        self.refresh_all()

        # v1.2 一次性迁移提示
        QTimer.singleShot(300, self._show_v1_2_migration_notice)

        if config.get_refresh_on_startup():
            QTimer.singleShot(500, self._refresh_market)
        self._setup_timer()

    def closeEvent(self, event):
        """关闭窗口时回收全部托管后台线程（主窗口行情 / AI 聊天 / 连接测试）。

        这些线程 parent=None 且阻塞在网络 IO 上，不主动停止的话，退出时
        Python 侧引用随窗口销毁，会触发
        "QThread: Destroyed while thread is still running" 而崩溃退出。
        """
        stop_all_threads(self)
        for page in self._pages.values():
            stop_all_threads(page)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Sidebar ----
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(theme.SIDEBAR_W)
        side_lay = QVBoxLayout(sidebar)
        side_lay.setContentsMargins(14, 20, 14, 14)
        side_lay.setSpacing(2)

        # Logo
        logo_box = QWidget()
        logo_box.setObjectName("sideLogo")
        logo_lay = QHBoxLayout(logo_box)
        logo_lay.setContentsMargins(10, 4, 10, 18)
        logo_lay.setSpacing(10)
        # Logo（按屏幕 DPR 物理分辨率渲染，避免高 DPI 屏上模糊）
        icon_path = find_app_icon()
        if icon_path:
            logo_pic = QLabel()
            logo_pic.setPixmap(logo_pixmap(icon_path, 36))
            logo_lay.addWidget(logo_pic)
        logo_text_box = QVBoxLayout()
        logo_text_box.setSpacing(0)
        logo_title = QLabel("安航家资")
        logo_title.setObjectName("sideLogoTitle")
        logo_slogan = QLabel("家庭资产管理")
        logo_slogan.setObjectName("sideLogoSlogan")
        logo_text_box.addWidget(logo_title)
        logo_text_box.addWidget(logo_slogan)
        logo_lay.addLayout(logo_text_box)
        logo_lay.addStretch()
        side_lay.addWidget(logo_box)

        # 导航
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.stack = QStackedWidget()

        nav_items = [
            ("overview", "总览", "home", OverviewPage),
            ("members", "成员", "members", MembersPage),
            ("accounts", "账户", "accounts", AccountsPage),
            ("assets", "资产", "assets", AssetsPage),
            ("liabilities", "负债", "liabilities", LiabilitiesPage),
            ("reports", "报表", "reports", ReportsPage),
            ("ai", "AI 助手", "ai", AiChatPage),
        ]
        self._pages: dict[str, QWidget] = {}
        for key, label, icon_key, cls in nav_items:
            btn = QPushButton(label)
            btn.setProperty("nav", "item")
            btn.setProperty("navKey", icon_key)
            btn.setCheckable(True)
            btn.setIcon(nav_icon(icon_key, theme.TEXT_2))
            btn.setIconSize(btn.iconSize())
            btn.setCursor(Qt.PointingHandCursor)
            self.nav_group.addButton(btn)
            side_lay.addWidget(btn)
            btn.toggled.connect(lambda checked, b=btn, k=key: self._on_nav_toggled(b, k, checked))
            page = cls()
            self._pages[key] = page
            self.stack.addWidget(page)

        side_lay.addStretch()

        # 底部：设置 + 版本
        bottom = QWidget()
        bottom.setObjectName("sideBottom")
        bottom_lay = QVBoxLayout(bottom)
        bottom_lay.setContentsMargins(0, 12, 0, 0)
        bottom_lay.setSpacing(2)
        settings_btn = QPushButton("设置")
        settings_btn.setProperty("nav", "item")
        settings_btn.setCheckable(True)
        settings_btn.setIcon(nav_icon("settings", theme.TEXT_2))
        settings_btn.setCursor(Qt.PointingHandCursor)
        self.nav_group.addButton(settings_btn)
        bottom_lay.addWidget(settings_btn)
        settings_btn.toggled.connect(lambda checked: self._on_nav_toggled(settings_btn, "settings", checked))
        self._settings_page = SettingsPage()
        self._pages["settings"] = self._settings_page
        self.stack.addWidget(self._settings_page)

        version_label = QLabel("v2.1 · 数据存于本机，密码保护")
        version_label.setObjectName("sideVersion")
        bottom_lay.addWidget(version_label)
        side_lay.addWidget(bottom)

        root.addWidget(sidebar)

        # ---- 内容区 ----
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.addWidget(self.stack)
        root.addWidget(content, 1)

        # ---- Statusbar（自绘，非 QStatusBar）----
        status_bar = QFrame()
        status_bar.setObjectName("statusbar")
        status_bar.setFixedHeight(theme.STATUSBAR_H)
        sb = QHBoxLayout(status_bar)
        sb.setContentsMargins(28, 0, 28, 0)
        sb.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(7, 7)
        dot.setObjectName("statusDot")
        sb.addWidget(dot)
        self.save_label = QLabel("数据已自动保存 · 本机存储，密码保护")
        sb.addWidget(self.save_label)
        sb.addStretch()
        self.market_label = QLabel("")
        sb.addWidget(self.market_label)
        self.backup_label = QLabel("")
        sb.addWidget(self.backup_label)
        content_lay.addWidget(status_bar)
        self._update_backup_label()

        self.nav_group.buttons()[0].setChecked(True)

    def _on_nav_toggled(self, btn: QPushButton, key: str, checked: bool):
        """导航切换：切页 + 同步全部导航图标颜色（激活蓝 / 常态灰）。"""
        if checked:
            self.stack.setCurrentWidget(self._pages[key])
        self._sync_nav_icons()

    def _sync_nav_icons(self):
        for b in self.nav_group.buttons():
            icon_key = self._icon_key_of(b)
            color = theme.BLUE if b.isChecked() else theme.TEXT_2
            b.setIcon(nav_icon(icon_key, color))

    @staticmethod
    def _icon_key_of(btn: QPushButton) -> str:
        # 导航按钮创建时已 setProperty("navKey", icon_key)，避免依赖中文文案反查（文案改即坏）
        return btn.property("navKey") or "info"

    # ------------------------------------------------------------------
    def _connect_signals(self):
        for page in self._pages.values():
            if hasattr(page, "data_changed"):
                page.data_changed.connect(self.refresh_all)
            if hasattr(page, "status_msg"):
                page.status_msg.connect(self._on_page_status)
        overview = self._pages.get("overview")
        if overview and hasattr(overview, "navigate_request"):
            # 总览页不再直接摸主窗口私有成员，改由信号驱动导航与行情刷新
            overview.navigate_request.connect(lambda key: self._goto_page(key))
            overview.market_refresh_request.connect(self._refresh_market)
        if hasattr(self._settings_page, "settings_changed"):
            self._settings_page.settings_changed.connect(self._on_settings_changed)
        if hasattr(self._settings_page, "market_settings_changed"):
            self._settings_page.market_settings_changed.connect(self.restart_timer)
        if hasattr(self._settings_page, "data_restored"):
            self._settings_page.data_restored.connect(self.refresh_all)

    def _on_page_status(self, msg: str):
        """页面发来的状态消息（如行情刷新结果）→ 状态栏。"""
        self.market_label.setText(msg)

    def _on_settings_changed(self):
        """设置变更（AI 授权等）后刷新 AI 页授权摘要。"""
        ai_page = self._pages.get("ai")
        if ai_page and hasattr(ai_page, "refresh_scope"):
            ai_page.refresh_scope()

    def refresh_all(self):
        for page in self._pages.values():
            if hasattr(page, "refresh"):
                page.refresh()

    # ------------------------------------------------------------------
    # 行情刷新
    # ------------------------------------------------------------------
    def _refresh_market(self):
        # 公共启动器内部已包含：列持仓 → 去重取代码 → 构造 fetcher → 连信号
        # → 防重入托管（启动刷新 / 定时刷新 / 手动刷新三者可能重叠）
        start_market_refresh(self, "_fetcher", self._on_market_ready, self._on_market_failed)

    def _on_market_ready(self, prices: dict):
        """行情就绪：整段 try/except 防止 update_prices/refresh 异常导致闪退。"""
        try:
            holding_dao.update_prices(prices)
            from app.utils import now_str
            self.market_label.setText(f"行情已更新 {now_str()[11:16]}")
            self.refresh_all()
        except Exception as e:
            self.market_label.setText("行情更新失败，显示缓存价格")
            print(f"[market] update failed: {e}")

    def _on_market_failed(self, err: str):
        self.market_label.setText("行情更新失败，显示缓存价格")

    def _setup_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_market)
        interval = config.get_refresh_interval()
        if interval > 0:
            self._timer.start(interval * 60 * 1000)

    def restart_timer(self):
        self._timer.stop()
        interval = config.get_refresh_interval()
        if interval > 0:
            self._timer.start(interval * 60 * 1000)

    def _update_backup_label(self):
        """状态栏显示最近备份时间（data/backups 下最新文件）。"""
        from app.database import get_data_dir
        try:
            backups = sorted((get_data_dir() / "backups").glob("*"))
            if backups:
                mtime = max(p.stat().st_mtime for p in backups)
                from datetime import datetime
                self.backup_label.setText(f"上次备份：{datetime.fromtimestamp(mtime):%Y-%m-%d %H:%M}")
                return
        except OSError:
            pass
        self.backup_label.setText("上次备份：—")

    # ------------------------------------------------------------------
    def _show_v1_2_migration_notice(self):
        if config.get_setting("v1_2_notice_pending", "0") != "1":
            return
        config.set_setting("v1_2_notice_pending", "0")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "账户类型已升级",
            "账户类型已升级：原银行卡/支付宝/微信账户已归入“现金”。\n"
            "如有定期存款或理财产品，请编辑对应账户，将类型改为“理财”并设置可用日期。",
        )

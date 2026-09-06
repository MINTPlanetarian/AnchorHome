"""设置页（v2.0，UI 设计规范 4.9）。

从对话框改为页面：topbar"设置" + 分组卡片纵向排列（安全/行情/AI 助手/数据备份/汇率/关于）。
信号：settings_changed（AI 授权等变更） / market_settings_changed（行情定时） / data_restored（恢复后）。
"""
from __future__ import annotations

import json
from datetime import datetime

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app import config, security
from app.services import ai_service, backup_service
from app.ui import theme
from app.ui.page_base import PageBase
from app.ui.widgets.button import make_button
from app.ui.widgets.icon import logo_pixmap, svg_to_icon
from app.ui.widgets.base_table import setup_table
from app.ui.thread_helper import start_thread

APP_VERSION = "v2.1"


class TestConnWorker(QThread):
    """后台测试 AI 连接。"""

    # 注意：不要命名为 finished —— 那是 QThread 内置信号，同名遮蔽会让
    # "线程真正结束"的信号永远连不上（线程托管依赖内置 finished）
    test_done = Signal(bool, str)

    def run(self):
        ok, msg = ai_service.test_connection()
        self.test_done.emit(ok, msg)


class SettingsPage(PageBase):
    """设置页。"""

    settings_changed = Signal()
    market_settings_changed = Signal()
    data_restored = Signal()

    def __init__(self, parent=None):
        super().__init__("设置", "密码、行情、AI 与数据备份")
        self._build_content()

    # ------------------------------------------------------------------
    def _build_content(self):
        body = self.body()
        body.setSpacing(16)

        # 1) 安全
        sec = QGroupBox("安全 · 修改启动密码")
        f = QFormLayout(sec)
        f.setSpacing(10)
        f.setLabelAlignment(Qt.AlignLeft)
        self.old_pwd = QLineEdit()
        self.old_pwd.setEchoMode(QLineEdit.Password)
        self.new_pwd = QLineEdit()
        self.new_pwd.setEchoMode(QLineEdit.Password)
        self.confirm_pwd = QLineEdit()
        self.confirm_pwd.setEchoMode(QLineEdit.Password)
        f.addRow(self._lab("旧密码"), self.old_pwd)
        f.addRow(self._lab("新密码（≥6位）"), self.new_pwd)
        f.addRow(self._lab("确认新密码"), self.confirm_pwd)
        change_btn = make_button("修改密码", "primary")
        change_btn.clicked.connect(self._change_password)
        f.addRow("", change_btn)
        body.addWidget(sec)

        # 2) 行情
        market = QGroupBox("行情刷新")
        f = QFormLayout(market)
        f.setSpacing(10)
        self.refresh_on_startup = QCheckBox("启动时自动刷新行情")
        f.addRow("", self.refresh_on_startup)
        self.refresh_interval = QComboBox()
        for val, label in [(0, "关闭"), (5, "每 5 分钟"), (15, "每 15 分钟"),
                           (30, "每 30 分钟"), (60, "每 60 分钟")]:
            self.refresh_interval.addItem(label, val)
        f.addRow(self._lab("定时刷新"), self.refresh_interval)
        save_market_btn = make_button("保存行情设置", "ghost")
        save_market_btn.clicked.connect(self._save_market)
        f.addRow("", save_market_btn)
        body.addWidget(market)

        # 3) AI 助手
        ai_group = QGroupBox("AI 助手（DeepSeek）")
        f = QFormLayout(ai_group)
        f.setSpacing(10)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("sk-...")
        f.addRow(self._lab("API Key"), self.api_key)
        self.base_url = QLineEdit()
        f.addRow(self._lab("Base URL"), self.base_url)
        self.model = QLineEdit()
        f.addRow(self._lab("模型名"), self.model)
        test_row = QHBoxLayout()
        test_btn = make_button("测试连接", "ghost")
        test_btn.clicked.connect(self._test_connection)
        test_row.addWidget(test_btn)
        self.test_result = QLabel("")
        self.test_result.setStyleSheet(f"font-size:12px; color:{theme.TEXT_3};")
        test_row.addWidget(self.test_result)
        test_row.addStretch()
        f.addRow("", test_row)

        scope_label = QLabel("数据授权范围（未勾选的数据绝不发送给 API）")
        scope_label.setObjectName("formLabel")
        f.addRow(scope_label)
        self.scope_summary = QCheckBox("资产负债汇总")
        self.scope_accounts = QCheckBox("账户汇总金额")
        self.scope_holdings = QCheckBox("持仓明细")
        self.scope_trend = QCheckBox("趋势数据")
        self.scope_liabilities = QCheckBox("负债明细")
        self.scope_assets = QCheckBox("资产台账")
        grid = QWidget()
        g = QHBoxLayout(grid)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(20)
        col1 = QVBoxLayout()
        col2 = QVBoxLayout()
        for cb in (self.scope_summary, self.scope_accounts, self.scope_holdings):
            col1.addWidget(cb)
        for cb in (self.scope_trend, self.scope_liabilities, self.scope_assets):
            col2.addWidget(cb)
        g.addLayout(col1)
        g.addLayout(col2)
        g.addStretch()
        f.addRow("", grid)

        save_ai_btn = make_button("保存 AI 配置", "primary")
        save_ai_btn.clicked.connect(lambda: self._save_ai())
        f.addRow("", save_ai_btn)
        body.addWidget(ai_group)

        # 4) 数据备份
        backup = QGroupBox("数据备份")
        b_lay = QVBoxLayout(backup)
        b_lay.setSpacing(10)
        btn_row = QHBoxLayout()
        enc_btn = make_button("导出加密备份（.fabak，推荐）", "primary")
        enc_btn.clicked.connect(self._export_encrypted)
        plain_btn = make_button("导出明文 JSON", "ghost")
        plain_btn.clicked.connect(self._export_plain)
        restore_btn = make_button("从备份恢复", "danger")
        restore_btn.clicked.connect(self._restore)
        btn_row.addWidget(enc_btn)
        btn_row.addWidget(plain_btn)
        btn_row.addWidget(restore_btn)
        btn_row.addStretch()
        b_lay.addLayout(btn_row)

        # 独立一行：导出结构化数据（供 AI Agent 分析）
        export_row = QHBoxLayout()
        export_btn = make_button("导出结构化数据（.json，供 AI 分析）", "ghost")
        export_btn.clicked.connect(self._export_structured)
        export_row.addWidget(export_btn)
        export_row.addStretch()
        b_lay.addLayout(export_row)
        export_hint = QLabel("导出一份包含账户、持仓、资产、负债及持有人等全部信息的中文键 JSON，便于 AI 或分析工具直接读取。")
        export_hint.setObjectName("formHint")
        export_hint.setWordWrap(True)
        b_lay.addWidget(export_hint)

        self.backup_info = QLabel("")
        self.backup_info.setObjectName("formHint")
        b_lay.addWidget(self.backup_info)
        body.addWidget(backup)

        # 5) 汇率
        fx = QGroupBox("汇率（外币账户折算用）")
        fx_lay = QVBoxLayout(fx)
        fx_lay.setSpacing(10)
        self.fx_table = QTableWidget(0, 2)
        self.fx_table.setHorizontalHeaderLabels(["币种", "汇率（1 币种 = ? CNY）"])
        # 第 0 列 Stretch、第 1 列 ResizeToContents（随表头/内容自适应），不再全列 Stretch
        setup_table(self.fx_table, row_height=40)
        fx_lay.addWidget(self.fx_table)
        fx_btn_row = QHBoxLayout()
        add_fx_btn = make_button("+ 新增币种", "ghost")
        add_fx_btn.clicked.connect(self._add_fx)
        save_fx_btn = make_button("保存汇率", "primary")
        save_fx_btn.clicked.connect(self._save_fx)
        fx_btn_row.addWidget(add_fx_btn)
        fx_btn_row.addWidget(save_fx_btn)
        fx_btn_row.addStretch()
        fx_lay.addLayout(fx_btn_row)
        body.addWidget(fx)

        # 6) 关于
        about = QGroupBox("关于")
        a_lay = QHBoxLayout(about)
        a_lay.setSpacing(12)
        from app.ui.widgets.icon import find_app_icon
        icon_path = find_app_icon()
        if icon_path:
            ico = QLabel()
            ico.setPixmap(logo_pixmap(icon_path, 40))
            a_lay.addWidget(ico)
        about_text = QLabel(f"<b>安航家资</b> {APP_VERSION}<br>"
                            f"<span style='color:{theme.TEXT_3}; font-size:12px;'>"
                            f"家庭资产管理工具 · 数据仅存储于本机，由启动密码保护</span>")
        a_lay.addWidget(about_text)
        a_lay.addStretch()
        body.addWidget(about)

        self._load()

    @staticmethod
    def _lab(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("formLabel")
        return lbl

    # ------------------------------------------------------------------
    def _change_password(self):
        old = self.old_pwd.text()
        new = self.new_pwd.text()
        confirm = self.confirm_pwd.text()
        salt_hex = config.get_setting("password_salt", "")
        pwd_hash = config.get_setting("password_hash", "")
        if not security.verify_password(old, salt_hex, pwd_hash):
            QMessageBox.warning(self, "提示", "旧密码错误")
            return
        if len(new) < 6:
            QMessageBox.warning(self, "提示", "新密码至少 6 位")
            return
        if new != confirm:
            QMessageBox.warning(self, "提示", "两次输入的新密码不一致")
            return
        encrypted_keys = ["ai_api_key"]
        decrypted = {}
        for key in encrypted_keys:
            decrypted[key] = security.decrypt_text(config.get_setting(key, "") or "")
        salt, pwd_hash = security.set_password(new)
        config.set_setting("password_salt", salt.hex())
        config.set_setting("password_hash", pwd_hash)
        for key, plain in decrypted.items():
            if plain:
                config.set_setting(key, security.encrypt_text(plain))
        QMessageBox.information(self, "完成", "密码已修改。")
        for w in (self.old_pwd, self.new_pwd, self.confirm_pwd):
            w.clear()

    def _save_market(self):
        config.set_setting("refresh_on_startup", "1" if self.refresh_on_startup.isChecked() else "0")
        config.set_setting("refresh_interval_minutes", str(self.refresh_interval.currentData()))
        QMessageBox.information(self, "完成", "行情设置已保存。")
        self.market_settings_changed.emit()

    # ------------------------------------------------------------------
    def _test_connection(self):
        self._save_ai(silent=True)
        self.test_result.setText("测试中…")
        worker = TestConnWorker(self)
        worker.test_done.connect(self._on_test_done)
        # 防重入 + 结束后 deleteLater：连点「测试连接」不再累积线程对象
        start_thread(self, "_test_worker", worker)

    def _on_test_done(self, ok: bool, msg: str):
        color = theme.GREEN if ok else theme.RED
        self.test_result.setStyleSheet(f"font-size:12px; color:{color};")
        self.test_result.setText(msg)

    def _save_ai(self, silent=False):
        api_key = self.api_key.text().strip()
        if api_key:
            config.set_setting("ai_api_key", security.encrypt_text(api_key))
        else:
            # 清空输入框保存时显式删除已存密钥，避免"以为删了其实还在"
            config.delete_setting("ai_api_key")
        config.set_setting("ai_base_url", self.base_url.text().strip() or ai_service.DEFAULT_BASE_URL)
        config.set_setting("ai_model", self.model.text().strip() or ai_service.DEFAULT_MODEL)
        config.set_setting("ai_scope_summary", "1" if self.scope_summary.isChecked() else "0")
        config.set_setting("ai_scope_accounts", "1" if self.scope_accounts.isChecked() else "0")
        config.set_setting("ai_scope_holdings", "1" if self.scope_holdings.isChecked() else "0")
        config.set_setting("ai_scope_trend", "1" if self.scope_trend.isChecked() else "0")
        config.set_setting("ai_scope_liabilities", "1" if self.scope_liabilities.isChecked() else "0")
        config.set_setting("ai_scope_assets", "1" if self.scope_assets.isChecked() else "0")
        self.settings_changed.emit()
        if not silent:
            QMessageBox.information(self, "完成", "AI 配置已保存。")

    # ------------------------------------------------------------------
    def _default_backup_name(self, ext: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d")
        return f"anhang_backup_{stamp}.{ext}"

    def _export_encrypted(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出加密备份", self._default_backup_name("fabak"), "加密备份 (*.fabak)"
        )
        if not path:
            return
        try:
            backup_service.export_backup(path, encrypted=True)
            QMessageBox.information(self, "完成", f"加密备份已导出到：\n{path}")
            self._refresh_backup_info()
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _export_plain(self):
        ret = QMessageBox.warning(
            self, "警告", "明文备份文件未加密，包含全部财务数据，请妥善保管！\n确定继续导出吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出明文备份", self._default_backup_name("json"), "JSON (*.json)"
        )
        if not path:
            return
        try:
            backup_service.export_backup(path, encrypted=False)
            QMessageBox.information(self, "完成", f"明文备份已导出到：\n{path}")
            self._refresh_backup_info()
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _export_structured(self):
        """导出结构化 JSON（账户/持仓/资产/负债/持有人全景，供 AI Agent 分析）。"""
        from app.services import export_service
        path, _ = QFileDialog.getSaveFileName(
            self, "导出结构化数据",
            f"anhang_assets_structured_{datetime.now():%Y%m%d}.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            export_service.export_structured_json(path)
            QMessageBox.information(self, "完成", f"结构化数据已导出到：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _restore(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择备份文件", "", "备份文件 (*.fabak *.json)"
        )
        if not path:
            return
        password = None
        if path.lower().endswith(".fabak"):
            pwd, ok = QInputDialog.getText(
                self, "输入密码", "请输入启动密码以解密备份：", QLineEdit.Password,
            )
            if not ok:
                return
            password = pwd
        ret = QMessageBox.warning(
            self, "确认恢复",
            "恢复将覆盖当前全部数据（恢复前会自动备份当前数据）。\n确定继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        try:
            counts = backup_service.import_backup(path, password)
            summary = "、".join(f"{k} {v} 条" for k, v in counts.items() if v)
            QMessageBox.information(self, "恢复完成", f"数据已恢复：\n{summary}")
            self.data_restored.emit()
            self._load()
        except Exception as e:
            QMessageBox.warning(self, "恢复失败", str(e))

    def _refresh_backup_info(self):
        from app.database import get_data_dir
        try:
            backups = sorted((get_data_dir() / "backups").glob("*"))
            if backups:
                mtime = max(p.stat().st_mtime for p in backups)
                self.backup_info.setText(f"上次备份：{datetime.fromtimestamp(mtime):%Y-%m-%d %H:%M}")
                return
        except OSError:
            pass
        self.backup_info.setText("上次备份：—")

    # ------------------------------------------------------------------
    @staticmethod
    def _fx_rate_item(code: str, rate) -> QTableWidgetItem:
        """汇率单元格。CNY 为本位币恒为 1，锁定不可编辑，防止误改污染全部折算。"""
        item = QTableWidgetItem(str(rate))
        if code.upper() == "CNY":
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _add_fx(self):
        code, ok = QInputDialog.getText(self, "新增币种", "输入币种代码（如 USD）：")
        if not ok or not code.strip():
            return
        code = code.strip().upper()
        if code == "CNY":
            QMessageBox.information(self, "提示", "CNY 为本位币，汇率恒为 1，无需添加。")
            return
        for row in range(self.fx_table.rowCount()):
            if self.fx_table.item(row, 0) and self.fx_table.item(row, 0).text() == code:
                QMessageBox.information(self, "提示", "该币种已存在")
                return
        row = self.fx_table.rowCount()
        self.fx_table.insertRow(row)
        self.fx_table.setItem(row, 0, QTableWidgetItem(code))
        self.fx_table.setItem(row, 1, QTableWidgetItem("1"))

    def _save_fx(self):
        rates = {}
        for row in range(self.fx_table.rowCount()):
            code_item = self.fx_table.item(row, 0)
            rate_item = self.fx_table.item(row, 1)
            if not code_item or not code_item.text().strip():
                continue
            try:
                rates[code_item.text().strip().upper()] = float(rate_item.text() or 0)
            except ValueError:
                QMessageBox.warning(self, "格式错误", f"第 {row + 1} 行汇率不是数字")
                return
        rates["CNY"] = 1.0  # 本位币兜底：即使表格数据被外部改脏，也不允许存入非 1 的 CNY
        config.set_setting("fx_rates", json.dumps(rates, ensure_ascii=False))
        QMessageBox.information(self, "完成", "汇率已保存。")

    # ------------------------------------------------------------------
    def _load(self):
        self.refresh_on_startup.setChecked(config.get_refresh_on_startup())
        interval = config.get_refresh_interval()
        idx = self.refresh_interval.findData(interval)
        if idx >= 0:
            self.refresh_interval.setCurrentIndex(idx)

        api_key = security.decrypt_text(config.get_setting("ai_api_key", "") or "")
        self.api_key.setText(api_key)
        self.base_url.setText(config.get_setting("ai_base_url", ai_service.DEFAULT_BASE_URL))
        self.model.setText(config.get_setting("ai_model", ai_service.DEFAULT_MODEL))
        self.scope_summary.setChecked(config.get_setting("ai_scope_summary", "1") == "1")
        self.scope_accounts.setChecked(config.get_setting("ai_scope_accounts", "0") == "1")
        self.scope_holdings.setChecked(config.get_setting("ai_scope_holdings", "0") == "1")
        self.scope_trend.setChecked(config.get_setting("ai_scope_trend", "0") == "1")
        self.scope_liabilities.setChecked(config.get_setting("ai_scope_liabilities", "0") == "1")
        self.scope_assets.setChecked(config.get_setting("ai_scope_assets", "0") == "1")

        # 汇率表
        self.fx_table.setRowCount(0)
        try:
            rates = json.loads(config.get_setting("fx_rates", "{}") or "{}")
        except json.JSONDecodeError:
            rates = {}
        if not isinstance(rates, dict):
            rates = {}  # settings 是明文表，非字典脏值不能让设置页崩溃
        for code, rate in rates.items():
            row = self.fx_table.rowCount()
            self.fx_table.insertRow(row)
            self.fx_table.setItem(row, 0, QTableWidgetItem(code))
            self.fx_table.setItem(row, 1, self._fx_rate_item(code, rate))
        if not rates:
            self.fx_table.insertRow(0)
            self.fx_table.setItem(0, 0, QTableWidgetItem("CNY"))
            self.fx_table.setItem(0, 1, self._fx_rate_item("CNY", 1))

        self._refresh_backup_info()

    def refresh(self):
        """页面切换时重载配置（防止外部变更）。"""
        self._load()

"""登录 / 首次设置密码对话框（v2.0，UI 设计规范 4.1）。

左右分栏：左侧品牌区（深蓝渐变 + 品牌语 + 卖点 + 波浪装饰），
右侧白色登录卡（锁形徽章 / 密码框 + 眼睛切换 / 全宽进入按钮）。
双态同窗口切换：登录态 ↔ 首次设置态（双密码框 + 一致性校验）。
行为：密码错误卡片抖动 400ms；回车提交；输错 5 次锁定 5 分钟（倒计时自动恢复）。
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QStackedLayout, QVBoxLayout, QWidget,
)

from app import config, security
from app.ui import theme
from app.ui.widgets.icon import logo_pixmap, svg_to_icon

WAVES_SVG = ('<svg width="800" height="150" viewBox="0 0 800 150" preserveAspectRatio="none" '
             'xmlns="http://www.w3.org/2000/svg" fill="none">'
             '<path d="M0 96 C130 60, 260 130, 400 96 C540 62, 670 128, 800 92 L800 150 L0 150 Z" '
             'fill="rgba(255,255,255,.10)"/>'
             '<path d="M0 122 C150 92, 290 148, 430 118 C570 88, 690 140, 800 112 L800 150 L0 150 Z" '
             'fill="rgba(255,255,255,.13)"/></svg>')

FEATURES = [
    "数据存于本机，不上传任何服务器，启动需密码",
    "股票基金行情自动刷新，盈亏一目了然",
    "AI 财务助手，随时为你的资产把把脉",
]


class LoginDialog(QDialog):
    """启动密码对话框。mode='setup' 为首次设置，'login' 为校验。"""

    def __init__(self, mode: str, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.setWindowTitle("安航家资 · 启动密码")
        self.setFixedSize(1024, 640)
        self.setStyleSheet(self._dialog_qss())
        self._build_ui()
        if self.mode == "login":
            self._check_lock_state()
            self._lock_timer = QTimer(self)
            self._lock_timer.setInterval(1000)
            self._lock_timer.timeout.connect(self._on_lock_tick)
            self._lock_timer.start()

    def _dialog_qss(self) -> str:
        t = theme
        return f"""
        QDialog {{ background: {t.SURFACE}; }}
        #brandPanel {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {t.BRAND_FROM}, stop:0.58 {t.BRAND_MID}, stop:1 {t.BRAND_TO});
        }}
        #brandName {{ font-size: 22px; font-weight: 700; letter-spacing: .06em; color: #fff; }}
        #brandSub {{ font-size: 11px; color: rgba(255,255,255,.72); letter-spacing: .18em; }}
        #slogan {{ font-size: 40px; font-weight: 700; color: #fff; line-height: 1.35; }}
        #feature {{ font-size: 14px; color: rgba(255,255,255,.92); }}
        #cardTitle {{ font-size: 26px; font-weight: 700; color: {t.TEXT}; }}
        #cardTip {{ font-size: 14px; color: {t.TEXT_2}; }}
        #pwdInput {{
            height: 46px; font-size: 15px; border: 1px solid {t.LINE_STRONG};
            border-radius: 10px; padding: 0 14px; background: {t.SURFACE};
        }}
        #pwdInput:focus {{ border-color: {t.BLUE}; }}
        #eyeBtn {{
            width: 32px; height: 32px; border-radius: 6px; border: none;
            background: transparent; color: {t.TEXT_3}; font-size: 12px;
        }}
        #eyeBtn:hover {{ color: {t.BLUE}; background: {t.BLUE_BG}; }}
        #loginBtn {{
            height: 46px; border-radius: 10px; background: {t.BLUE}; color: #fff;
            font-size: 15px; font-weight: 600; letter-spacing: .12em; border: none;
        }}
        #loginBtn:hover {{ background: {t.BLUE_DARK}; }}
        #loginBtn:disabled {{ background: #A8C8F5; }}
        #metaText {{ font-size: 12.5px; color: {t.TEXT_3}; }}
        #switchLink {{ color: {t.BLUE}; font-weight: 500; font-size: 13px; background: transparent; border: none; }}
        #switchLink:hover {{ text-decoration: underline; }}
        #errText {{ color: {t.RED}; font-size: 12.5px; }}
        """

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 左侧品牌区 ----
        brand = QFrame()
        brand.setObjectName("brandPanel")
        brand.setFixedWidth(470)
        b_lay = QVBoxLayout(brand)
        b_lay.setContentsMargins(56, 48, 56, 40)
        b_lay.setSpacing(0)

        # Logo（按屏幕 DPR 物理分辨率渲染，避免高 DPI 屏上模糊）
        logo_row = QHBoxLayout()
        logo_row.setSpacing(12)
        from app.ui.widgets.icon import find_app_icon
        icon_path = find_app_icon()
        if icon_path:
            logo_pic = QLabel()
            logo_pic.setPixmap(logo_pixmap(icon_path, 48))
            logo_row.addWidget(logo_pic)
        logo_text = QVBoxLayout()
        logo_text.setSpacing(1)
        name = QLabel("安航家资")
        name.setObjectName("brandName")
        sub = QLabel("FAMILY ASSET NAVIGATOR")
        sub.setObjectName("brandSub")
        logo_text.addWidget(name)
        logo_text.addWidget(sub)
        logo_row.addLayout(logo_text)
        logo_row.addStretch()
        b_lay.addLayout(logo_row)

        b_lay.addStretch()

        # 品牌语
        slogan = QLabel('让家庭资产，<br><span style="color:#FFD666;">安稳航行</span>。')
        slogan.setObjectName("slogan")
        slogan.setTextFormat(Qt.RichText)
        b_lay.addWidget(slogan)

        desc = QLabel("一个只属于你家庭的本地资产管理工具：账户、持仓、房产、负债、保障，"
                      "全部数据存于你自己的电脑，由启动密码保护。")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:15px; color:rgba(255,255,255,.82); line-height:1.8;")
        b_lay.addSpacing(14)
        b_lay.addWidget(desc)

        # 三条卖点
        b_lay.addSpacing(30)
        for text in FEATURES:
            row = QHBoxLayout()
            row.setSpacing(10)
            check = QLabel()
            check.setPixmap(svg_to_icon(theme.icon("check_gold", theme.BRAND_GOLD, 18), 18).pixmap(18, 18))
            row.addWidget(check)
            f = QLabel(text)
            f.setObjectName("feature")
            row.addWidget(f)
            row.addStretch()
            b_lay.addLayout(row)
            b_lay.addSpacing(10)

        # 波浪装饰（底部）
        waves = QLabel()
        waves.setPixmap(svg_to_icon(WAVES_SVG, 800).pixmap(800, 150))
        b_lay.addSpacing(20)
        b_lay.addWidget(waves)
        root.addWidget(brand)

        # ---- 右侧登录区 ----
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setAlignment(Qt.AlignCenter)
        right_lay.setContentsMargins(48, 40, 48, 40)

        self.card_stack = QStackedLayout()
        self.card_stack.setSpacing(0)
        right_lay.addLayout(self.card_stack)

        self._login_card = self._build_login_card()
        self._setup_card = self._build_setup_card()
        self.card_stack.addWidget(self._login_card)
        self.card_stack.addWidget(self._setup_card)
        self.card_stack.setCurrentIndex(0 if self.mode == "login" else 1)

        root.addWidget(right, 1)

    def _lock_badge(self, svg_name: str) -> QLabel:
        badge = QLabel()
        badge.setFixedSize(52, 52)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"background:{theme.BLUE_BG}; border-radius:14px;")
        badge.setPixmap(svg_to_icon(theme.icon(svg_name, theme.BLUE, 26), 26).pixmap(26, 26))
        return badge

    def _pwd_field(self, placeholder: str) -> tuple[QWidget, QLineEdit, QPushButton]:
        """密码输入框 + 眼睛切换按钮。"""
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        edit = QLineEdit()
        edit.setObjectName("pwdInput")
        edit.setEchoMode(QLineEdit.Password)
        edit.setPlaceholderText(placeholder)
        row.addWidget(edit, 1)
        eye = QPushButton("👁")
        eye.setObjectName("eyeBtn")
        eye.setCursor(Qt.PointingHandCursor)
        eye.clicked.connect(lambda: self._toggle_eye(edit))
        row.addWidget(eye)
        return wrap, edit, eye

    @staticmethod
    def _toggle_eye(edit: QLineEdit):
        edit.setEchoMode(QLineEdit.Normal if edit.echoMode() == QLineEdit.Password else QLineEdit.Password)

    def _field_block(self, label_text: str, placeholder: str) -> tuple[QWidget, QLineEdit]:
        """「表单标签 + 密码输入框」组合块，标签与输入框间距 4px。

        三层均设纵向 Fixed：QStackedLayout 令登录/设置两卡等高，多余高度会
        分给 Preferred 控件——不固定的话标签被拉高，文字居中后与输入框的
        视觉间距远大于 4px。
        """
        block = QWidget()
        v = QVBoxLayout(block)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        label = QLabel(label_text)
        label.setStyleSheet(f"font-size:14px; font-weight:500; color:{theme.TEXT_2};")
        wrap, edit, _eye = self._pwd_field(placeholder)
        for w in (label, wrap, block):
            sp = w.sizePolicy()
            sp.setVerticalPolicy(QSizePolicy.Fixed)
            w.setSizePolicy(sp)
        v.addWidget(label)
        v.addWidget(wrap)
        return block, edit

    # ------------------------------------------------------------------
    def _build_login_card(self) -> QWidget:
        card = QWidget()
        card.setFixedWidth(360)
        lay = QVBoxLayout(card)
        lay.setSpacing(0)

        lay.addWidget(self._lock_badge("lock"), 0, Qt.AlignLeft)
        lay.addSpacing(20)
        title = QLabel("欢迎回来")
        title.setObjectName("cardTitle")
        lay.addWidget(title)
        tip = QLabel("输入启动密码以解锁你的家庭资产")
        tip.setObjectName("cardTip")
        lay.addSpacing(8)
        lay.addWidget(tip)

        lay.addSpacing(24)
        block, self.pwd_edit = self._field_block("启动密码", "请输入密码")
        lay.addWidget(block)

        self.err_label = QLabel("")
        self.err_label.setObjectName("errText")
        self.err_label.setVisible(False)
        lay.addSpacing(10)
        lay.addWidget(self.err_label)

        lay.addSpacing(14)
        self.confirm_btn = QPushButton("进　入")
        self.confirm_btn.setObjectName("loginBtn")
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.clicked.connect(self._on_confirm)
        lay.addWidget(self.confirm_btn)

        lay.addSpacing(18)
        meta = QLabel("🔒 连续输错 5 次将锁定 5 分钟 · 所有数据仅保存在本机")
        meta.setObjectName("metaText")
        meta.setAlignment(Qt.AlignCenter)
        lay.addWidget(meta)

        lay.addSpacing(26)
        # 安全：登录态（已设密码）不提供"创建启动密码"入口，
        # 否则可绕过"输错 5 次锁定 5 分钟"直接重设密码，并因 Fernet 密钥更换丢失已加密的 AI Key
        if self.mode == "setup":
            switch = QPushButton("首次使用？创建启动密码")
            switch.setObjectName("switchLink")
            switch.setCursor(Qt.PointingHandCursor)
            switch.clicked.connect(lambda: self.card_stack.setCurrentIndex(1))
            lay.addWidget(switch, 0, Qt.AlignCenter)

        self.pwd_edit.returnPressed.connect(self._on_confirm)
        return card

    def _build_setup_card(self) -> QWidget:
        card = QWidget()
        card.setFixedWidth(360)
        lay = QVBoxLayout(card)
        lay.setSpacing(0)

        lay.addWidget(self._lock_badge("lock_plus"), 0, Qt.AlignLeft)
        lay.addSpacing(20)
        title = QLabel("创建启动密码")
        title.setObjectName("cardTitle")
        lay.addWidget(title)
        tip = QLabel("首次使用，请设置一个至少 6 位的密码保护你的数据")
        tip.setObjectName("cardTip")
        lay.addSpacing(8)
        lay.addWidget(tip)

        lay.addSpacing(24)
        block1, self.new_pwd = self._field_block("设置密码", "至少 6 位")
        lay.addWidget(block1)
        lay.addSpacing(14)
        block2, self.confirm_pwd = self._field_block("确认密码", "再次输入密码")
        lay.addWidget(block2)

        self.setup_err = QLabel("")
        self.setup_err.setObjectName("errText")
        self.setup_err.setVisible(False)
        lay.addSpacing(10)
        lay.addWidget(self.setup_err)

        lay.addSpacing(14)
        self.setup_btn = QPushButton("创建并进入")
        self.setup_btn.setObjectName("loginBtn")
        self.setup_btn.setCursor(Qt.PointingHandCursor)
        self.setup_btn.clicked.connect(self._on_setup)
        lay.addWidget(self.setup_btn)

        lay.addSpacing(18)
        meta = QLabel("🔒 密码经加密派生后仅保存在本机，请妥善牢记")
        meta.setObjectName("metaText")
        meta.setAlignment(Qt.AlignCenter)
        lay.addWidget(meta)

        lay.addSpacing(26)
        switch = QPushButton("已设置过密码？返回登录")
        switch.setObjectName("switchLink")
        switch.setCursor(Qt.PointingHandCursor)
        switch.clicked.connect(lambda: self.card_stack.setCurrentIndex(0))
        lay.addWidget(switch, 0, Qt.AlignCenter)

        self.new_pwd.returnPressed.connect(self._on_setup)
        self.confirm_pwd.returnPressed.connect(self._on_setup)
        return card

    # ------------------------------------------------------------------
    # 行为：抖动 / 锁定
    # ------------------------------------------------------------------
    def _shake_card(self):
        """卡片左右抖动动画 400ms。"""
        card = self.card_stack.currentWidget()
        if not hasattr(card, "pos"):
            return
        anim = QPropertyAnimation(card, b"pos", self)
        anim.setDuration(400)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        base = card.pos()
        steps = [(-6, 0), (6, 0), (-3, 0), (3, 0), (0, 0)]
        for i, (dx, dy) in enumerate(steps):
            anim.setKeyValueAt(i / (len(steps) - 1), base + QPoint(dx, dy))
        anim.start()
        self._shake_anim = anim  # 防止被回收

    def _show_error(self, label: QLabel, text: str):
        label.setText(text)
        label.setVisible(True)

    def _check_lock_state(self):
        locked, remain = security.is_locked()
        if locked:
            mins = remain // 60 + 1
            self._show_error(self.err_label, f"已锁定，请在 {mins} 分钟后重试")
            self.confirm_btn.setEnabled(False)
            self.pwd_edit.setEnabled(False)
        else:
            self.confirm_btn.setEnabled(True)
            self.pwd_edit.setEnabled(True)

    def _on_lock_tick(self):
        if not self.pwd_edit.isEnabled():
            locked, _ = security.is_locked()
            if not locked:
                self._check_lock_state()
                self.err_label.setText("锁定已解除，请重新输入密码")
                self.err_label.setVisible(True)
                self.pwd_edit.setFocus()

    # ------------------------------------------------------------------
    def _on_setup(self):
        """首次设置密码。

        安全守卫：仅在 setup 模式且尚未设置密码时生效。login 模式（已设密码）
        不应出现此入口（登录卡已不显示切换按钮），此处再防御一层，防止任何路径
        调用导致绕过锁定、无旧密码校验直接覆盖密码，进而因 Fernet 密钥更换而
        丢失已加密的 AI API Key。
        """
        if self.mode != "setup" or config.has_password():
            return
        pwd = self.new_pwd.text()
        if len(pwd) < 6:
            self._show_error(self.setup_err, "密码至少 6 位")
            self._shake_card()
            return
        if pwd != self.confirm_pwd.text():
            self._show_error(self.setup_err, "两次输入的密码不一致")
            self._shake_card()
            return
        salt, pwd_hash = security.set_password(pwd)
        config.set_setting("password_salt", salt.hex())
        config.set_setting("password_hash", pwd_hash)
        self.accept()

    def _on_confirm(self):
        """登录校验。"""
        pwd = self.pwd_edit.text()
        locked, _ = security.is_locked()
        if locked:
            self._check_lock_state()
            return

        salt_hex = config.get_setting("password_salt", "")
        pwd_hash = config.get_setting("password_hash", "")
        if not salt_hex or not pwd_hash:
            self._show_error(self.err_label, "密码数据异常，请联系支持")
            return

        if security.verify_password(pwd, salt_hex, pwd_hash):
            security.reset_fail()
            self.accept()
        else:
            remain = security.record_fail()
            self._shake_card()
            if remain <= 0:
                self._check_lock_state()
                self._show_error(self.err_label, "连续输错 5 次，已锁定 5 分钟")
            else:
                self._show_error(self.err_label, f"密码错误，还可尝试 {remain} 次")
            self.pwd_edit.clear()

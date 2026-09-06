"""AI 助手页（v2.0.6，按主流 AI 对话框 UI 重构，风格与其他页面一致）。

布局（WorkBuddy / DeepSeek 等主流 AI 对话框形式）：
    - 消息列表占满整个页面（scroll stretch=1）；
    - AI 消息：左侧 [头像] + 气泡（固定宽 = 视口宽 - 72px，几乎铺满）；
    - 用户消息：右侧 气泡 + [头像]，气泡右对齐；
    - 窗口缩放时统一刷新气泡宽度（showEvent/resizeEvent → _apply_bubble_widths）；
    - 底部输入条白卡圆角 + 「发送」primary，AI 思考时显示"正在思考…"。
历史：进入页面从 chat_history 加载渲染；仅"清空对话"清除。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QScrollArea, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget,
)

from app.services import ai_service
from app.ui import theme
from app.ui.page_base import PageBase
from app.ui.widgets.button import make_button
from app.ui.widgets.modal import Modal
from app.ui.thread_helper import start_thread
from app.ui.widgets.layout_util import clear_layout

# 聊天历史首屏只渲染最近若干条，向上滚动再分批懒加载更早的消息，
# 避免数百条历史一次性创建成百上千个气泡控件导致卡顿。
_INITIAL_MSGS = 20      # 首屏最多渲染 20 条（约 10 轮）
_OLDER_BATCH = 20       # 每次向上滚动再加载 20 条


class ChatWorker(QThread):
    """后台线程：调用 AI 接口，避免卡 UI。"""

    # 注意：不要命名为 finished —— 那是 QThread 内置信号，同名遮蔽会让
    # "线程真正结束"的信号永远连不上（线程托管依赖内置 finished）
    reply_ready = Signal(dict)
    failed = Signal(str)

    def __init__(self, user_msg: str, parent=None):
        super().__init__(parent)
        self._msg = user_msg

    def run(self):
        try:
            result = ai_service.chat(self._msg)
            self.reply_ready.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class ActionConfirmDialog(Modal):
    """AI 提议修改的确认弹窗。"""

    def __init__(self, desc: str, on_confirm, parent=None):
        super().__init__("AI 提议的修改", width=440, parent=parent)
        tip = QLabel("以下修改需要你的确认才会执行：")
        tip.setObjectName("formHint")
        self.body_layout.addWidget(tip)
        box = QFrame()
        box.setObjectName("card")
        b_lay = QVBoxLayout(box)
        b_lay.setContentsMargins(14, 12, 14, 12)
        desc_label = QLabel(desc)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color:{theme.TEXT}; font-size:14px; line-height:1.6;")
        b_lay.addWidget(desc_label)
        self.body_layout.addWidget(box)
        self.set_foot("取消", "确认执行", on_confirm)


class AiChatPage(PageBase):
    """AI 助手页：标准对话框 UI，气泡铺满消息区。"""

    data_changed = Signal()

    def __init__(self, parent=None):
        super().__init__("AI 小助手", "基于你授权数据的家庭财务分析")
        self._history_loaded = False
        self._bubbles: list[dict] = []  # {"bubble","browser","is_ai"}
        self._all_history: list[dict] = []  # 进入页面时一次性取回的全部历史（升序）
        self._render_start = 0          # 当前已渲染窗口在历史中的起始下标
        self._loading_older = False     # 懒加载期间防重入
        self._scroll_connected = False  # 滚动监听是否已连接（避免清空后重复连接）
        self._build_content()
        self.refresh_scope()
        self._load_history_or_welcome()
        self.refresh()

    # ------------------------------------------------------------------
    # 气泡宽度管理（几乎铺满消息区，窗口缩放自动刷新）
    # ------------------------------------------------------------------
    def _bubble_width(self) -> int:
        """AI 气泡宽度 = 聊天视口宽 - 72px（几乎铺满，右侧留呼吸空间）。"""
        vp_w = self.scroll.viewport().width() or self.scroll.width() or 960
        return max(680, vp_w - 72)

    def _apply_bubble_widths(self):
        """窗口尺寸变化后统一刷新全部气泡宽度与排版高度。"""
        w = self._bubble_width()
        for rec in self._bubbles:
            bubble = rec["bubble"]
            if rec["is_ai"]:
                bubble.setFixedWidth(w)
                browser = rec.get("browser")
                if browser is not None:
                    browser.setMaximumWidth(w - 28)
                    browser.document().setTextWidth(w - 28)
                    doc_h = browser.document().size().height() + 20
                    browser.setFixedHeight(min(max(40, int(doc_h)), 640))
            else:
                bubble.setMaximumWidth(w)  # 用户气泡自适应，仅限最大宽

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(60, self._apply_bubble_widths)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(30, self._apply_bubble_widths)

    # ------------------------------------------------------------------
    def _build_content(self):
        self.clear_btn = make_button("清空对话", "ghost")
        self.clear_btn.clicked.connect(self._clear_chat)
        self.add_action(self.clear_btn)

        body = self.body()

        # 消息滚动区（stretch=1 占满剩余空间）
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.msg_container = QWidget()
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setAlignment(Qt.AlignTop)
        self.msg_layout.setSpacing(16)
        self.msg_layout.setContentsMargins(4, 8, 12, 8)
        self.msg_layout.addStretch()  # 底部弹簧
        self.scroll.setWidget(self.msg_container)
        body.addWidget(self.scroll, 1)

        # 输入条（白卡圆角 12，固定在消息区下方）
        input_card = QFrame()
        input_card.setObjectName("chatInput")
        i_lay = QHBoxLayout(input_card)
        i_lay.setContentsMargins(12, 8, 8, 8)
        i_lay.setSpacing(8)
        self.input_edit = QTextEdit()
        self.input_edit.setFrameShape(QFrame.NoFrame)
        self.input_edit.setPlaceholderText("输入消息，如：分析一下我的资产配置是否合理？")
        self.input_edit.setFixedHeight(52)
        self.input_edit.setStyleSheet("QTextEdit { border: none; background: transparent; }")
        i_lay.addWidget(self.input_edit, 1)
        self.send_btn = make_button("发送", "primary")
        self.send_btn.setFixedHeight(36)
        self.send_btn.clicked.connect(self._send)
        i_lay.addWidget(self.send_btn)
        body.addWidget(input_card)

    # ------------------------------------------------------------------
    def refresh_scope(self):
        """刷新授权范围摘要。未配置 API Key 时聊天流顶部给系统引导气泡。"""
        from app import config
        parts = []
        mapping = [("ai_scope_summary", "汇总"), ("ai_scope_accounts", "账户"),
                   ("ai_scope_holdings", "持仓"), ("ai_scope_liabilities", "负债明细"),
                   ("ai_scope_assets", "资产台账"), ("ai_scope_trend", "趋势")]
        for key, name in mapping:
            if config.get_setting(key, "1" if key == "ai_scope_summary" else "0") == "1":
                parts.append(name)
        self.set_desc("已授权：" + ("、".join(parts) if parts else "无"))

    def refresh(self):
        self.refresh_scope()

    # ------------------------------------------------------------------
    def _avatar(self, is_ai: bool) -> QLabel:
        """消息头像：AI=蓝渐变方块"AI"，用户=蓝色方块"我"。"""
        av = QLabel("AI" if is_ai else "我")
        av.setFixedSize(32, 32)
        av.setAlignment(Qt.AlignCenter)
        if is_ai:
            av.setStyleSheet(
                f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f"stop:0 {theme.BLUE}, stop:1 {theme.BRAND_TO});"
                f"color:#fff; border-radius:10px; font-size:12px; font-weight:700;")
        else:
            av.setStyleSheet(
                f"background:{theme.BLUE}; color:#fff; border-radius:10px;"
                f"font-size:12px; font-weight:700;")
        return av

    def _build_bubble(self, role: str, text: str):
        """构建一条消息气泡控件，返回 (row_qlayout, record)。

        仅负责"造控件"，不决定插入位置——由 _add_bubble / _prepend_bubble 决定
        是追加到末尾还是插入到顶部（懒加载更早历史）。
        """
        is_ai = role != "user"
        max_w = self._bubble_width()
        av = self._avatar(is_ai)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.setContentsMargins(0, 0, 0, 0)

        if is_ai:
            bubble = QFrame()
            bubble.setObjectName("chatBubbleAI")
            bubble.setFixedWidth(max_w)
            browser = QTextBrowser()
            browser.setFrameShape(QFrame.NoFrame)
            browser.setOpenExternalLinks(True)
            browser.setStyleSheet("background: transparent; border: none;")
            browser.setMaximumWidth(max_w - 28)
            browser.setMarkdown(text)
            browser.document().setTextWidth(max_w - 28)
            doc_h = browser.document().size().height() + 20
            browser.setFixedHeight(min(max(40, int(doc_h)), 640))
            b_lay = QVBoxLayout(bubble)
            b_lay.setContentsMargins(14, 10, 14, 10)
            b_lay.addWidget(browser)
            row.addWidget(av, 0, Qt.AlignTop)
            row.addWidget(bubble, 1, Qt.AlignLeft)  # stretch=1 占满
            rec = {"bubble": bubble, "browser": browser, "is_ai": True}
        else:
            bubble = QFrame()
            bubble.setObjectName("chatBubbleUser")
            bubble.setMaximumWidth(max_w)  # 自适应：短消息小气泡，长消息撑到 max_w 换行
            label = QLabel(text)
            label.setWordWrap(True)
            label.setMaximumWidth(max_w - 28)
            label.setStyleSheet("color: #fff; background: transparent;")
            b_lay = QVBoxLayout(bubble)
            b_lay.setContentsMargins(14, 10, 14, 10)
            b_lay.addWidget(label)
            row.addStretch()
            row.addWidget(bubble, 0, Qt.AlignRight)
            row.addWidget(av, 0, Qt.AlignTop)
            rec = {"bubble": bubble, "browser": None, "is_ai": False}

        return row, rec

    def _add_bubble(self, role: str, text: str):
        """追加一条消息气泡到末尾（最新消息），并自动滚到底部。"""
        row, rec = self._build_bubble(role, text)
        self.msg_layout.insertLayout(self.msg_layout.count() - 1, row)
        self._bubbles.append(rec)
        QTimer.singleShot(30, self._scroll_bottom)

    def _prepend_bubble(self, role: str, text: str):
        """把更早的历史气泡插入到顶部（懒加载），不改变当前滚动视图位置。"""
        row, rec = self._build_bubble(role, text)
        self.msg_layout.insertLayout(0, row)
        self._bubbles.insert(0, rec)

    def _scroll_bottom(self):
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ------------------------------------------------------------------
    def _load_history_or_welcome(self):
        """进入页面时加载历史：首屏只渲染最近一窗，更早的滚动到顶再懒加载。"""
        if self._history_loaded:
            return
        self._history_loaded = True
        self._all_history = ai_service.get_full_history()  # 升序全量（仅文本，内存开销极小）
        if self._all_history:
            # 首屏窗口：最近 _INITIAL_MSGS 条；更早的留在 _all_history 待滚动加载
            self._render_start = max(0, len(self._all_history) - _INITIAL_MSGS)
            for h in self._all_history[self._render_start:]:
                self._add_bubble(h["role"], h["content"])
            # 仍有更早历史才需要监听滚动到顶
            if self._render_start > 0 and not self._scroll_connected:
                self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_top)
                self._scroll_connected = True
        elif ai_service.is_configured():
            self._add_welcome()
        else:
            self._add_bubble(
                "assistant",
                "⚙️ 尚未配置 AI 助手，请到「设置」页填写 DeepSeek API Key 后即可与我对话。\n\n"
                "*以上仅供参考，不构成投资建议*",
            )

    def _on_scroll_top(self, value: int):
        """滚到接近顶部时，懒加载更早的一批历史（向上插入），保持视图不跳动。"""
        if self._loading_older or value > 60:
            return
        if self._render_start <= 0:
            return
        self._loading_older = True
        sb = self.scroll.verticalScrollBar()
        old_max = sb.maximum()
        prev_start = self._render_start
        self._render_start = max(0, self._render_start - _OLDER_BATCH)
        # 从旧到新依次插入到顶部，维持时间顺序
        for h in self._all_history[self._render_start:prev_start]:
            self._prepend_bubble(h["role"], h["content"])
        # 顶部新增了内容，把滚动条值同步下移，使原视口内的消息停在原处
        QTimer.singleShot(0, lambda: sb.setValue(sb.value() + (sb.maximum() - old_max)))
        # 没有更早历史了：断开监听，避免无意义触发
        if self._render_start <= 0 and self._scroll_connected:
            try:
                self.scroll.verticalScrollBar().valueChanged.disconnect(self._on_scroll_top)
            except Exception:
                pass
            self._scroll_connected = False
        self._loading_older = False

    def _add_welcome(self):
        self._add_bubble(
            "assistant",
            "你好！我是你的家庭财务助手。可以问我资产配置、负债、趋势等相关问题。\n\n"
            "*以上仅供参考，不构成投资建议*",
        )

    # ------------------------------------------------------------------
    def _add_action_card(self, action: dict):
        desc = self._describe_action(action)
        dlg = ActionConfirmDialog(desc, lambda: self._execute_action(action, dlg), self)
        dlg.exec()

    @staticmethod
    def _action_int(action: dict, key: str) -> int | None:
        """安全取整型参数。模型输出的 id 可能是字符串甚至畸形值，失败返回 None。"""
        try:
            return int(action.get(key))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _action_money(value) -> str:
        """安全格式化金额。畸形值（None/非数字）原样展示，绝不在槽内抛异常。"""
        try:
            return f"¥{float(value):,.2f}"
        except (TypeError, ValueError):
            return str(value)

    def _describe_action(self, action: dict) -> str:
        op = action.get("op")
        reason = action.get("reason", "")
        suffix = f"\n原因：{reason}" if reason else ""
        if op == "update_asset_value":
            from app.dao import asset_dao
            item_id = self._action_int(action, "id")
            asset = asset_dao.get_asset(item_id) if item_id is not None else None
            name = asset["name"] if asset else f"资产#{action.get('id')}"
            return f"将「{name}」的估值更新为 {self._action_money(action.get('value', 0))}{suffix}"
        if op == "update_account_balance":
            from app.dao import account_dao
            item_id = self._action_int(action, "id")
            acc = account_dao.get_account(item_id) if item_id is not None else None
            name = acc["name"] if acc else f"账户#{action.get('id')}"
            return f"将「{name}」的余额更新为 {self._action_money(action.get('value', 0))}{suffix}"
        return f"执行操作：{op}（{reason}）"

    def _execute_action(self, action: dict, dlg: Modal):
        try:
            result = ai_service.execute_action(action)
            dlg.accept()
            self._add_bubble("assistant", f"✅ {result}")
            self.data_changed.emit()
        except Exception as e:
            QMessageBox.warning(self, "执行失败", str(e))

    # ------------------------------------------------------------------
    def _send(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        if not ai_service.is_configured():
            QMessageBox.warning(self, "未配置", "请先到「设置」页配置 DeepSeek API Key。")
            return
        self.input_edit.clear()
        self._add_bubble("user", text)

        self._thinking = QLabel("AI 正在思考…")
        self._thinking.setStyleSheet(f"color:{theme.TEXT_3}; font-size:12px;")
        row = QHBoxLayout()
        row.setContentsMargins(42, 0, 0, 0)
        row.addWidget(self._thinking)
        self._thinking_row = row
        self.msg_layout.insertLayout(self.msg_layout.count() - 1, row)
        self._scroll_bottom()

        self.send_btn.setEnabled(False)
        worker = ChatWorker(text, parent=None)
        worker.reply_ready.connect(self._on_reply)
        worker.failed.connect(self._on_error)
        # 防重入 + 结束后 deleteLater：旧写法把内置 finished 同时当业务信号和清理钩子，
        # 语义混乱且线程引用无人托管
        start_thread(self, "_worker", worker)

    def _remove_thinking(self):
        if hasattr(self, "_thinking") and self._thinking is not None:
            # 连同承载它的空布局一并移除，避免每次发送累积空布局条目
            row = getattr(self, "_thinking_row", None)
            if row is not None:
                self.msg_layout.removeItem(row)
                row.deleteLater()
                self._thinking_row = None
            self._thinking.deleteLater()
            self._thinking = None

    def _on_reply(self, result: dict):
        self._remove_thinking()
        self.send_btn.setEnabled(True)
        reply = result["reply"]
        if reply:
            self._add_bubble("assistant", reply)
        action = result.get("action")
        if action:
            self._add_action_card(action)

    def _on_error(self, err: str):
        self._remove_thinking()
        self.send_btn.setEnabled(True)
        self._add_bubble("assistant", f"⚠️ 请求失败：{err}")

    def _clear_chat(self):
        ret = QMessageBox.question(
            self, "清空对话", "确定清空所有对话历史吗？\n（仅清除本地聊天记录，不影响数据）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            ai_service.clear_chat()
            clear_layout(self.msg_layout)
            self.msg_layout.addStretch()
            self._bubbles.clear()
            # 重置历史窗口与滚动监听状态，避免清空后重连/残留旧 handler
            self._all_history = []
            self._render_start = 0
            self._loading_older = False
            if self._scroll_connected:
                try:
                    self.scroll.verticalScrollBar().valueChanged.disconnect(self._on_scroll_top)
                except Exception:
                    pass
                self._scroll_connected = False
            self._history_loaded = False
            self._load_history_or_welcome()

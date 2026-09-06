"""PageBase：页面基类（UI 设计规范 2.2 的页面侧结构）。

每页 = Topbar(64px：标题 + 描述 + 右侧操作按钮) + 滚动内容区(padding 24/28)。
提供 show_empty() / hide_empty() 整页空状态切换（规范 3.10）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QStackedLayout, QVBoxLayout, QWidget,
)

from app.ui import theme
from app.ui.widgets.empty_state import EmptyState
from app.ui.widgets.layout_util import clear_layout


class PageBase(QWidget):
    """含 topbar 与滚动内容区的页面基类。页面内容写入 body() 布局。"""

    data_changed = Signal()

    def __init__(self, title: str, desc: str = "", parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Topbar ----
        self.topbar = QFrame()
        self.topbar.setObjectName("topbar")
        self.topbar.setFixedHeight(theme.TOPBAR_H)
        tb = QHBoxLayout(self.topbar)
        tb.setContentsMargins(28, 0, 28, 0)
        tb.setSpacing(16)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("topbarTitle")
        tb.addWidget(self.title_label)

        self.desc_label = QLabel(desc)
        self.desc_label.setObjectName("topbarDesc")
        if not desc:
            self.desc_label.setVisible(False)
        tb.addWidget(self.desc_label)
        tb.addStretch()
        self._action_widgets: list = []
        root.addWidget(self.topbar)

        # ---- 滚动内容区 ----
        self.scroll = QScrollArea()
        self.scroll.setObjectName("contentScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.content = QWidget()
        self.content_stack = QStackedLayout(self.content)
        self.content_stack.setContentsMargins(0, 0, 0, 0)

        # 正常内容容器
        self.page_body = QWidget()
        self.body_layout = QVBoxLayout(self.page_body)
        self.body_layout.setContentsMargins(28, 24, 28, 16)
        self.body_layout.setSpacing(14)
        self.content_stack.addWidget(self.page_body)

        # 空状态容器（惰性创建）
        self.empty_host = QWidget()
        self.empty_host_layout = QVBoxLayout(self.empty_host)
        self.empty_host_layout.setContentsMargins(28, 24, 28, 16)
        self.content_stack.addWidget(self.empty_host)

        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

    # ------------------------------------------------------------------
    def add_action(self, widget) -> None:
        """往 topbar 右侧追加操作按钮。"""
        tb = self.topbar.layout()
        tb.addWidget(widget)
        self._action_widgets.append(widget)

    def set_desc(self, text: str) -> None:
        self.desc_label.setText(text)
        self.desc_label.setVisible(bool(text))

    def body(self) -> QVBoxLayout:
        return self.body_layout

    def show_empty(self, title: str, subtitle: str = "",
                   action_text: str | None = None, action_cb=None) -> None:
        """整页空状态（清空旧空状态后重建）。"""
        clear_layout(self.empty_host_layout)
        state = EmptyState(title, subtitle, action_text, action_cb)
        self.empty_host_layout.addWidget(state, 1)
        self.content_stack.setCurrentIndex(1)

    def hide_empty(self) -> None:
        self.content_stack.setCurrentIndex(0)

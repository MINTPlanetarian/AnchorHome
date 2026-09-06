"""Banner：提示条（UI 设计规范 3.9）。

blue 变体（口径说明/信息）与 orange 变体（到期提醒），圆角 10、左图标、可关闭。
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from app.ui import theme
from app.ui.widgets.icon import svg_to_icon


class Banner(QFrame):
    """提示条。variant: blue / orange。closable=True 时右侧显示 ✕。"""

    def __init__(self, text: str, variant: str = "blue", closable: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        self.setProperty("variant", variant)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        icon_color = theme.BLUE if variant == "blue" else theme.ORANGE
        icon_label = QLabel()
        icon_label.setPixmap(svg_to_icon(theme.icon("info", icon_color, 16), 16).pixmap(16, 16))
        lay.addWidget(icon_label)

        self.label = QLabel(text)
        self.label.setWordWrap(True)
        lay.addWidget(self.label, 1)

        if closable:
            self.close_btn = QPushButton("✕")
            self.close_btn.setFixedSize(24, 24)
            self.close_btn.clicked.connect(self.hide)
            lay.addWidget(self.close_btn)
        else:
            self.close_btn = None

    def set_text(self, text: str) -> None:
        self.label.setText(text)

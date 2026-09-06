"""EmptyState：空状态（UI 设计规范 3.10）。

居中浅灰线性插图 + 主文案 + 副文案 + primary 引导按钮。禁止只显示空表格。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui import theme
from app.ui.widgets.button import make_button
from app.ui.widgets.icon import svg_to_icon


class EmptyState(QWidget):
    """列表无数据时的整页空状态。"""

    def __init__(self, title: str, subtitle: str = "",
                 action_text: str | None = None, action_cb=None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)

        pic = QLabel()
        pic.setPixmap(svg_to_icon(theme.icon("empty", theme.LINE_STRONG, 64), 64).pixmap(64, 64))
        pic.setAlignment(Qt.AlignCenter)
        lay.addWidget(pic)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"font-size: 14px; color: {theme.TEXT_2}; font-weight: 500;")
        lay.addWidget(title_label)

        if subtitle:
            sub_label = QLabel(subtitle)
            sub_label.setAlignment(Qt.AlignCenter)
            sub_label.setStyleSheet(f"font-size: 13px; color: {theme.TEXT_3};")
            lay.addWidget(sub_label)

        if action_text and action_cb:
            btn = make_button(action_text, "primary")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(action_cb)
            btn_row = QVBoxLayout()
            btn_row.setAlignment(Qt.AlignCenter)
            btn_row.addWidget(btn)
            lay.addLayout(btn_row)

"""StatCard：统计卡片（UI 设计规范 3.4）。

白底 1px 边框圆角 14 + 轻阴影；hero 变体深蓝渐变白字。
结构：label(13px) → value(24px Bold) → sub(12px)。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QVBoxLayout

from app.ui import theme


class StatCard(QFrame):
    """统计数字卡片。hero=True 时为深蓝渐变 hero 卡。"""

    def __init__(self, label: str, hero: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setProperty("hero", "true" if hero else "false")
        self.setMinimumHeight(104)  # 容纳 label+value(24)+sub(12) 与 shadow 余量

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(4)

        self.label_widget = QLabel(label)
        self.label_widget.setObjectName("statLabel")
        self.value_widget = QLabel("¥0.00")
        self.value_widget.setObjectName("statValue")
        self.value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.sub_widget = QLabel("")
        self.sub_widget.setObjectName("statSub")
        self.sub_widget.setWordWrap(True)
        self.sub_widget.setVisible(False)

        lay.addWidget(self.label_widget)
        lay.addWidget(self.value_widget)
        lay.addWidget(self.sub_widget)
        lay.addStretch()

        # 轻阴影（仅统计卡；表格卡只用边框）
        from PySide6.QtGui import QColor
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(6)
        shadow.setOffset(0, 1)
        shadow.setColor(QColor(16, 24, 40, 12))
        self.setGraphicsEffect(shadow)

    # ------------------------------------------------------------------
    def set_value(self, value: float, prefix: str = "¥") -> None:
        self.value_widget.setText(f"{prefix}{value:,.2f}")

    def set_text(self, text: str) -> None:
        self.value_widget.setText(text)

    def set_sub(self, text: str) -> None:
        if text:
            self.sub_widget.setText(text)
            self.sub_widget.setVisible(True)
        else:
            self.sub_widget.setText("")
            self.sub_widget.setVisible(False)

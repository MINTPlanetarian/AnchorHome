"""Tag：语义标签（UI 设计规范 3.3）。

变体：blue / green / orange / gray / gold / red。高 24、全圆角、12px Medium。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


def make_tag(text: str, variant: str = "gray") -> QLabel:
    """生成一个 Tag 标签。"""
    tag = QLabel(text)
    tag.setProperty("tag", variant)
    tag.setAlignment(Qt.AlignCenter)
    return tag


def tag_in_cell(text: str, variant: str = "gray", top_margin: int = 12) -> QWidget:
    """把 Tag 装进容器，供表格单元格 setCellWidget 使用（垂直居中留白）。"""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, top_margin, 0, top_margin)
    lay.addWidget(make_tag(text, variant))
    lay.addStretch()
    return w


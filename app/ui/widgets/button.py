"""Button：统一按钮工厂（UI 设计规范 3.1）。

用 property: variant 命中全局 QSS（primary/ghost/danger），或 act/act-primary 表格按钮。
全项目按钮一律经 make_button 创建，禁止散落 setStyleSheet 定义按钮外观。
"""
from __future__ import annotations

from PySide6.QtWidgets import QPushButton


def make_button(text: str = "", variant: str = "ghost", parent=None) -> QPushButton:
    """创建带视觉变体的按钮。variant: primary / ghost / danger / act / act-primary。"""
    btn = QPushButton(text, parent)
    btn.setProperty("variant", variant)
    return btn


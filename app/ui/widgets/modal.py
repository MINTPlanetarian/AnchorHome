"""Modal：弹窗基类（UI 设计规范 3.8）。

宽 520 白底圆角 14、head(标题+✕) → body → foot(取消 ghost + 保存 primary)。
继承后填 body 内容即可；foot 按钮经 set_foot(cancel_text, ok_text, on_ok) 配置。
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui import theme
from app.ui.widgets.button import make_button
from app.ui.widgets.layout_util import clear_layout


class Modal(QDialog):
    """标准弹窗基类。"""

    def __init__(self, title: str, width: int = 520, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedWidth(width)
        self.setMinimumHeight(200)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # head
        head = QWidget()
        head.setObjectName("modalHead")
        head_lay = QHBoxLayout(head)
        head_lay.setContentsMargins(24, 18, 16, 14)
        title_label = QLabel(title)
        title_label.setObjectName("modalTitle")
        head_lay.addWidget(title_label)
        head_lay.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setObjectName("modalClose")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        head_lay.addWidget(close_btn)
        root.addWidget(head)

        # body
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(24, 18, 24, 6)
        self.body_layout.setSpacing(14)
        root.addWidget(self.body)

        # foot
        self.foot = QWidget()
        self.foot_lay = QHBoxLayout(self.foot)
        self.foot_lay.setContentsMargins(24, 10, 24, 20)
        self.foot_lay.addStretch()
        root.addWidget(self.foot)

        # 默认 foot：取消 + 保存
        self.ok_btn = None
        self.cancel_btn = None
        self.set_foot("取消", "保存", None)

    def resize_to_content(self):
        """子类 body 填完后调用：按 layout.sizeHint 自适应高（保留 setFixedWidth）。"""
        # 强制 layout 重新算 + 用 adjustSize 让 Qt 按 sizeHint 调整
        self.layout().invalidate()
        self.layout().activate()
        for child in self.findChildren(QWidget):
            if child.isVisible() and child.layout():
                child.layout().invalidate()
        # adjustSize 用 sizeHint 但保留 setFixedWidth
        self.adjustSize()

    def showEvent(self, event):
        """show 时强制按内容重算（init 时未 show，sizeHint 可能不准）。"""
        super().showEvent(event)
        QTimer.singleShot(0, self.resize_to_content)

    @staticmethod
    def _labeled(text: str) -> QLabel:
        """表单行标签（objectName=formLabel，供 QSS 统一着色）。

        原先 5 个弹窗类各复制一份相同实现，现上提到基类统一提供。
        """
        lbl = QLabel(text)
        lbl.setObjectName("formLabel")
        return lbl

    def set_foot(self, cancel_text: str, ok_text: str, on_ok, hide_cancel: bool = False,
                 ok_only: bool = False) -> None:
        """配置底部按钮。on_ok 为 None 时点保存 = accept()。

        hide_cancel / ok_only=True 时只显示确认按钮（head 已自带 ✕ 时避免重复）；
        ok_only 用于表达"仅确认"语义，调用处不必再传占位文案或用 setText 补间距。
        布局：左弹簧 + cancel + ok，让两个按钮靠右、foot 空白不可见。
        """
        clear_layout(self.foot_lay)       # 清空旧按钮（含可能残留的弹簧与子布局）
        self.ok_btn = make_button(ok_text, "primary")
        self.ok_btn.setMinimumHeight(36)
        self.ok_btn.clicked.connect(on_ok if on_ok else self.accept)
        if not hide_cancel and not ok_only:
            self.cancel_btn = make_button(cancel_text, "ghost")
            self.cancel_btn.setMinimumHeight(36)
            self.cancel_btn.clicked.connect(self.reject)
            self.foot_lay.addStretch()
            self.foot_lay.addWidget(self.cancel_btn)
        else:
            self.cancel_btn = None
            self.foot_lay.addStretch()
        self.foot_lay.addWidget(self.ok_btn)

    def body_add(self, widget) -> None:
        self.body_layout.addWidget(widget)

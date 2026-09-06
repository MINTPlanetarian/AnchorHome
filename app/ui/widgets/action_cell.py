"""ActionCell：所有表格"操作"列的统一组件（UI 设计规范 3.2 + v1.3 强约束）。

结构：[主按钮] [⋯]，间距 8；主按钮 act/act-primary 变体（全局 QSS），
⋯为 QToolButton(InstantPopup) 挂 QMenu，菜单项危险项红色（QSS[danger="true"]）。
宽度恒定（⋯ 与主按钮同宽同高、同内边距/圆角），任何窗口宽度/DPI 下不被裁剪。

用法：
    ActionCell("编辑", on_primary=cb, more_items=[("停用", cb1), ("删除", cb2, "danger")])
    primary_kind: "default"(蓝字蓝框) / "primary"(蓝底白字，如"本月已还款")
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QMenu, QPushButton, QToolButton, QWidget, QWidgetAction

from app.ui import styles

# 菜单项样式（组件内部唯一出处；danger 红字、hover 红底）
_MENU_ITEM_QSS = (
    "QPushButton { color:#1A1D26; background:transparent; border:none; text-align:left;"
    " padding:0 12px; font-size:13px; border-radius:6px; }"
    "QPushButton:hover { background:#F5F7FA; }"
)
_MENU_ITEM_DANGER_QSS = (
    "QPushButton { color:#DC2626; background:transparent; border:none; text-align:left;"
    " padding:0 12px; font-size:13px; border-radius:6px; }"
    "QPushButton:hover { background:#FCEAEA; }"
)


class ActionCell(QWidget):
    """主操作按钮 + ⋯ 菜单。"""

    def __init__(self, primary_text: str, on_primary, more_items=None,
                 primary_kind: str = "default", parent=None):
        super().__init__(parent)
        self.menu = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(8)

        # 主按钮（全局 QSS：variant=act / act-primary）
        self.main_btn = QPushButton(primary_text)
        self.main_btn.setProperty("variant", "act-primary" if primary_kind == "primary" else "act")
        self.main_btn.setCursor(Qt.PointingHandCursor)
        self.main_btn.setFixedHeight(28)
        # 全局 QSS 的 QPushButton{min-height:36px} 是硬约束，会压过代码 setFixedHeight；
        # 依"组件内样式就近覆盖"规则覆写为 0，28px 才能真正生效
        self.main_btn.setStyleSheet("QPushButton { min-height: 0px; }")
        self.main_btn.clicked.connect(on_primary)
        # 宽度按与 QSS act 规则同源的常量计算（min-width/padding/border），⋯ 按钮取同一值
        self.main_btn.ensurePolished()
        minw = styles.ACT_PRIMARY_MIN_WIDTH if primary_kind == "primary" else styles.ACT_MIN_WIDTH
        text_w = self.main_btn.fontMetrics().horizontalAdvance(primary_text)
        self._btn_w = (max(minw, text_w) + styles.ACT_PAD_X * 2
                       + (0 if primary_kind == "primary" else styles.ACT_BORDER * 2))
        self.main_btn.setFixedWidth(self._btn_w)
        layout.addWidget(self.main_btn)

        if more_items:
            # ⋯ 按钮
            self.more_btn = QToolButton()
            self.more_btn.setText("⋯")
            self.more_btn.setProperty("variant", "more")
            self.more_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            self.more_btn.setPopupMode(QToolButton.InstantPopup)
            self.more_btn.setCursor(Qt.PointingHandCursor)
            # 与主按钮同宽同高（QSS 同 padding/圆角），纵向天然对齐
            self.more_btn.setFixedSize(QSize(self._btn_w, 28))
            self.menu = QMenu(self.more_btn)
            self.menu.setMinimumWidth(128)
            for item in more_items:
                text = item[0]
                cb = item[1]
                kind = item[2] if len(item) > 2 else "default"
                self._add_menu_item(text, cb, kind)
            self.more_btn.setMenu(self.menu)
            layout.addWidget(self.more_btn)

        layout.addStretch()

    def _add_menu_item(self, text: str, callback, kind: str) -> None:
        """菜单项：普通 或 danger（红色文字，hover 红底）。"""
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(32)
        btn.setStyleSheet(_MENU_ITEM_DANGER_QSS if kind == "danger" else _MENU_ITEM_QSS)
        btn.clicked.connect(lambda _=False: self._on_item_clicked(callback))
        act = QWidgetAction(self.menu)
        act.setDefaultWidget(btn)
        self.menu.addAction(act)

    def _on_item_clicked(self, callback) -> None:
        self.menu.close()
        callback()

    def sizeHint(self) -> QSize:
        """合计主按钮 + ⋯ 按钮宽度，保证操作列 ResizeToContents 足够。

        纯常量计算（宽度在构造期已定）。+16px 基础余量：单元格控件的实际可用
        宽度会被 QSS ::item 内边距扣掉一笔，autofit/RTC 的比例余量在此之上兜底，
        保证等宽双按钮不重叠、不裁剪，多余部分由尾部 stretch 吸收。
        """
        w = self._btn_w
        if self.menu is not None:
            w += self._btn_w + 8
        return QSize(w + 16, 34)

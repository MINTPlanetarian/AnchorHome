"""Chip：筛选 Chip 互斥组（UI 设计规范 3.6）。

高 32 全圆角，默认白底灰字描边，active 蓝底白字；组内互斥。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from app.ui.widgets.layout_util import clear_layout


class ChipGroup(QWidget):
    """互斥筛选 Chip 组。

    items: [(key, label), ...]；changed 信号携带选中 key。
    """

    changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], default: str | None = None, parent=None):
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._keys: list[str] = []
        for key, label in items:
            btn = QPushButton(label)
            btn.setProperty("chip", "true")
            btn.setCheckable(True)
            self._group.addButton(btn)
            lay.addWidget(btn)
            self._keys.append(key)
            btn.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
        # 默认选中项
        idx = self._keys.index(default) if default in self._keys else 0
        self._group.buttons()[idx].setChecked(True)

    def current_key(self) -> str:
        """返回当前选中 key。

        不能用 QButtonGroup.checkedId()：addButton 未传 id 时默认 -1，所有按钮都一样，
        checkedId() 只能区分"有选中/无选中"，无法定位索引。改用 checkedButton() 反查。
        """
        btn = self._group.checkedButton()
        if btn is None:
            return self._keys[0]
        try:
            idx = self._group.buttons().index(btn)
        except ValueError:
            return self._keys[0]
        return self._keys[idx]

    def set_current(self, key: str) -> None:
        idx = self._keys.index(key) if key in self._keys else 0
        self._group.buttons()[idx].setChecked(True)

    def rebuild(self, items: list[tuple[str, str]], default: str | None = None) -> None:
        """重建全部 Chip（成员列表等动态数据变化时用）。"""
        lay = self.layout()
        clear_layout(lay)
        self._keys = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, label in items:
            btn = QPushButton(label)
            btn.setProperty("chip", "true")
            btn.setCheckable(True)
            self._group.addButton(btn)
            lay.addWidget(btn)
            self._keys.append(key)
            btn.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
        idx = self._keys.index(default) if default in self._keys else 0
        self._group.buttons()[idx].setChecked(True)

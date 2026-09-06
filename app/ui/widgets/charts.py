"""图表组件：TrendChart（净资产趋势折线图）+ DonutChart（资产分布环形图）。

UI 设计规范 4.2/4.7：
    - 趋势三线：总资产 #0064E6、总负债 #D97706、净资产 #16A34A（区分色，非涨跌语义）；
    - 环形图：中心总金额 + 右侧图例（色块 + 标签 + 金额 + 占比）。
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

import pyqtgraph as pg

from app.ui import theme
from app.ui.widgets.icon import svg_to_icon
from app.ui.widgets.layout_util import clear_layout


# ---------------------------------------------------------------------------
# 趋势折线图
# ---------------------------------------------------------------------------
class TrendChart(QWidget):
    """净资产趋势折线图（pyqtgraph）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.plot = pg.PlotWidget()
        self.plot.setBackground(theme.SURFACE)
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setMinimumHeight(260)
        self.plot.addLegend(offset=(10, 10))
        self.plot.getPlotItem().getAxis("left").setTextPen(pg.mkPen(theme.TEXT_3))
        self.plot.getPlotItem().getAxis("bottom").setTextPen(pg.mkPen(theme.TEXT_3))
        self._curve_assets = self.plot.plot([], [], pen=pg.mkPen(theme.TREND_ASSET, width=2), name="总资产")
        self._curve_liab = self.plot.plot([], [], pen=pg.mkPen(theme.TREND_LIAB, width=2), name="总负债")
        self._curve_net = self.plot.plot([], [], pen=pg.mkPen(theme.TREND_NET, width=2), name="净资产")
        lay.addWidget(self.plot, 1)

        self.hint = QLabel("")
        self.hint.setStyleSheet(f"color:{theme.TEXT_3}; font-size:13px;")
        self.hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.hint)

    def set_data(self, snapshots: list[dict]) -> None:
        if len(snapshots) < 2:
            # 数据不足：固定三条曲线只清空数据，避免 plot.clear() 后重建导致图例项残留/重复
            self._curve_assets.setData([], [])
            self._curve_liab.setData([], [])
            self._curve_net.setData([], [])
            self.hint.setText("数据不足，使用一段时间后可查看趋势")
            return
        self.hint.setText("")
        dates = [s["snapshot_date"] for s in snapshots]
        x = list(range(len(snapshots)))
        self._curve_assets.setData(x, [s["total_assets"] for s in snapshots])
        self._curve_liab.setData(x, [s["total_liabilities"] for s in snapshots])
        self._curve_net.setData(x, [s["net_worth"] for s in snapshots])
        ticks = []
        step = max(1, len(dates) // 6)
        for i in range(0, len(dates), step):
            ticks.append((i, dates[i][5:]))
        self.plot.getAxis("bottom").setTicks([ticks])


# ---------------------------------------------------------------------------
# 环形图
# ---------------------------------------------------------------------------
class DonutChart(QWidget):
    """环形图 + 中心总金额 + 右侧图例（色块+标签+金额+占比）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[tuple[str, float]] = []
        self.setMinimumHeight(240)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(20)

        # 左侧环形绘制区
        self._canvas = _DonutCanvas()
        lay.addWidget(self._canvas, 1)

        # 右侧图例
        self.legend_box = QVBoxLayout()
        self.legend_box.setSpacing(8)
        lay.addLayout(self.legend_box)

    def set_data(self, data: list[tuple[str, float]]) -> None:
        self._data = data
        self._canvas.set_data(data)
        self._rebuild_legend()

    def _rebuild_legend(self):
        # 图例行是通过 addLayout 加进去的，需递归清理，否则每次刷新都泄漏一屏控件
        clear_layout(self.legend_box)
        total = sum(v for _, v in self._data)
        if total <= 0:
            empty = QLabel("暂无数据")
            empty.setStyleSheet(f"color:{theme.TEXT_3}; font-size:13px;")
            self.legend_box.addWidget(empty)
            return
        for i, (label, value) in enumerate(self._data):
            row = QHBoxLayout()
            row.setSpacing(8)
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background:{theme.PIE_COLORS[i % len(theme.PIE_COLORS)]}; border-radius:5px;")
            row.addWidget(dot, 0, Qt.AlignVCenter)
            name = QLabel(label)
            name.setStyleSheet(f"color:{theme.TEXT_2}; font-size:13px;")
            row.addWidget(name)
            row.addStretch()
            pct = value / total * 100
            val = QLabel(f"¥{value:,.0f} · {pct:.1f}%")
            val.setStyleSheet(f"color:{theme.TEXT_2}; font-size:12px;")
            row.addWidget(val)
            self.legend_box.addLayout(row)


class _DonutCanvas(QWidget):
    """自绘环形图（QPainter），中心显示总金额。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[tuple[str, float]] = []
        self.setMinimumSize(180, 180)

    def set_data(self, data):
        self._data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        total = sum(v for _, v in self._data)
        side = min(self.width(), self.height()) - 8
        out_rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        r_out = side / 2
        r_in = r_out * 0.62
        center = out_rect.center()

        if total <= 0:
            painter.setPen(QColor(theme.TEXT_3))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无数据")
            return

        start_angle = 90 * 16
        for i, (label, value) in enumerate(self._data):
            span = int(-value / total * 360 * 16)
            painter.setBrush(QColor(theme.PIE_COLORS[i % len(theme.PIE_COLORS)]))
            painter.setPen(QColor(theme.SURFACE))
            painter.drawPie(out_rect, start_angle, span)
            start_angle += span

        # 中心挖空（环形效果）
        painter.setBrush(QColor(theme.SURFACE))
        painter.setPen(Qt.NoPen)
        in_rect = QRectF(center.x() - r_in, center.y() - r_in, r_in * 2, r_in * 2)
        painter.drawEllipse(in_rect)

        # 中心总金额
        painter.setPen(QColor(theme.TEXT_3))
        painter.setFont(QFont("Microsoft YaHei", 11))
        painter.drawText(self.rect().adjusted(0, -16, 0, -16), Qt.AlignCenter, "总金额")
        painter.setPen(QColor(theme.TEXT))
        painter.setFont(QFont("Microsoft YaHei", 15, QFont.Weight.Bold))
        painter.drawText(self.rect().adjusted(0, 8, 0, 8), Qt.AlignCenter, f"¥{total:,.0f}")

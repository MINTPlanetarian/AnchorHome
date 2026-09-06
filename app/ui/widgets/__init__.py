"""通用 UI 组件包（v2.0）：Button / ActionCell / Tag / StatCard / Chip / Modal / Banner / EmptyState。"""
from app.ui.widgets.action_cell import ActionCell
from app.ui.widgets.banner import Banner
from app.ui.widgets.base_table import cell_item, double_line_widget, money_item, setup_table
from app.ui.widgets.button import make_button
from app.ui.widgets.charts import DonutChart, TrendChart
from app.ui.widgets.chip import ChipGroup
from app.ui.widgets.empty_state import EmptyState
from app.ui.widgets.icon import nav_icon, svg_to_icon
from app.ui.widgets.modal import Modal
from app.ui.widgets.stat_card import StatCard
from app.ui.widgets.tag import make_tag, tag_in_cell

__all__ = [
    "ActionCell", "Banner", "ChipGroup", "EmptyState", "Modal", "StatCard",
    "TrendChart", "DonutChart", "cell_item", "double_line_widget", "money_item",
    "setup_table", "make_button", "make_tag", "tag_in_cell", "nav_icon", "svg_to_icon",
]

"""v2.0 设计令牌（Design Tokens）——UI 设计规范第 1 章的唯一视觉标准。

所有颜色、字号、间距、圆角只允许引用本模块常量，禁止在页面/组件中散落硬编码色值。
图标：内联 SVG（1.5px 线性描边风格，参照 HTML demo），经 theme.icon(name, color) 生成。
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 1.1 颜色
# ---------------------------------------------------------------------------
BLUE = "#0064E6"            # 品牌主色：主按钮、激活态、链接、强调数字
BLUE_DARK = "#0052C4"       # 主按钮 hover/pressed
BLUE_BG = "#EBF2FE"         # 选中项背景、信息提示条底色
BLUE_LINE = "#C9DEFC"       # 蓝色描边（act-btn、focus 环外的描边）
BG = "#F5F7FA"              # 内容区底色
SURFACE = "#FFFFFF"         # 卡片、表格、侧边栏、弹窗底色
LINE = "#E4E9F0"            # 卡片/表格/分割线细线
LINE_STRONG = "#D3DAE4"     # 输入框、次按钮描边
TEXT = "#1A1D26"            # 主文字
TEXT_2 = "#5A6474"          # 次要文字
TEXT_3 = "#98A2B3"          # 弱化文字（占位符、时间戳、"—"空值）
GREEN = "#16A34A"           # 正向：已启用、随时可用、涨
GREEN_BG = "#E8F7EE"
ORANGE = "#D97706"          # 提醒：已到期可用、临期
ORANGE_BG = "#FDF3E3"
RED = "#DC2626"             # 危险：删除、负向、跌
RED_BG = "#FCEAEA"
GOLD = "#B77900"            # 保险类型标签、金币色点缀
GOLD_BG = "#FCF3DD"

# 登录品牌区 / hero 统计卡渐变
BRAND_FROM = "#0A3D91"
BRAND_MID = "#0064E6"
BRAND_TO = "#2E8BFF"
BRAND_GOLD = "#FFD666"      # 品牌语强调金色

# 表格 hover 行底色、输入框 disabled 底色、tooltip
TABLE_HOVER = "#F8FAFD"
INPUT_DISABLED_BG = "#F3F5F8"
TOOLTIP_BG = "#1A1D26"

# 趋势图三线区分色（非涨跌语义，仅区分）
TREND_ASSET = "#0064E6"
TREND_LIAB = "#D97706"
TREND_NET = "#16A34A"

# 饼图色板
PIE_COLORS = [
    "#0064E6", "#D97706", "#16A34A", "#8B5CF6", "#DC2626",
    "#0EA5E9", "#EC4899", "#84CC16", "#F97316", "#6366F1",
]

# ---------------------------------------------------------------------------
# 1.2 字号
# ---------------------------------------------------------------------------
FS_DISPLAY = 26     # 登录页标题、关键大数字（Bold）
FS_TITLE = 18       # 页面标题 topbar（Bold）
FS_CARD_NUM = 24    # 统计卡数字（Bold）
FS_BODY = 14        # 正文、表格内容
FS_BODY_M = 14      # 导航项、按钮（Medium 500）
FS_SMALL = 13       # 辅助说明、表单 label
FS_MINI = 12        # 标签、状态栏、单元格副行
FS_TABLE_HEADER = 13  # 表头（与 styles.py QHeaderView::section 一致）

# ---------------------------------------------------------------------------
# 1.3 圆角 / 间距 / 阴影
# ---------------------------------------------------------------------------
RADIUS_SM = 8       # 按钮、输入框
RADIUS_MD = 10      # 提示条、弹窗内卡片
RADIUS_LG = 14      # 卡片、弹窗
TAG_RADIUS = 999    # 标签/筛选 chip 全圆角（高的一半）

CONTENT_PADDING = 24        # 内容区四周 padding
CARD_PADDING = 20           # 卡片内边距
TABLE_ROW_H = 52            # 表格双行单元格行高（单行 44）
TABLE_ROW_H_SINGLE = 44

# 窗口尺寸
WIN_MIN_W, WIN_MIN_H = 1100, 700
WIN_W, WIN_H = 1280, 800
SIDEBAR_W = 232
TOPBAR_H = 64
STATUSBAR_H = 34

# ---------------------------------------------------------------------------
# 图标（内联 SVG，viewBox 0 0 18 18，1.5px 线性描边）
# ---------------------------------------------------------------------------
_ICON_PATHS: dict[str, str] = {
    # 侧边栏导航
    "home": ('<path d="M2.5 7.2L9 2l6.5 5.2V15a1 1 0 0 1-1 1h-3.4v-4.4H6.9V16H3.5a1 1 0 0 1-1-1V7.2z" '
             'stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>'),
    "members": ('<circle cx="6.4" cy="6.2" r="2.6" stroke="currentColor" stroke-width="1.5"/>'
                '<path d="M1.8 15.4c.5-2.6 2.3-4 4.6-4s4.1 1.4 4.6 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
                '<circle cx="12.6" cy="6.6" r="2" stroke="currentColor" stroke-width="1.4"/>'
                '<path d="M12.4 11.6c1.9.2 3.2 1.4 3.7 3.4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>'),
    "accounts": ('<rect x="2" y="4" width="14" height="11" rx="2" stroke="currentColor" stroke-width="1.5"/>'
                 '<path d="M2 7.4h14" stroke="currentColor" stroke-width="1.5"/>'
                 '<path d="M5 11.6h3.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'),
    "assets": ('<path d="M9 2.2l6.8 4.4H2.2L9 2.2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>'
               '<path d="M3.4 8.4v5.4M7.3 8.4v5.4M10.7 8.4v5.4M14.6 8.4v5.4M2 15.6h14" '
               'stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'),
    "liabilities": ('<path d="M3 13.5L7 9l3 2.4 4.8-5.6" stroke="currentColor" stroke-width="1.5" '
                    'stroke-linecap="round" stroke-linejoin="round"/>'
                    '<path d="M2.2 15.8h13.6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'),
    "reports": ('<path d="M3 15.6V9.4M7.6 15.6V5.8M12.2 15.6v-4.6M16 15.6V3.4" '
                'stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>'),
    "ai": ('<rect x="3" y="5" width="12" height="9" rx="2.4" stroke="currentColor" stroke-width="1.5"/>'
           '<path d="M9 2v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
           '<circle cx="6.8" cy="9.4" r="1" fill="currentColor"/><circle cx="11.2" cy="9.4" r="1" fill="currentColor"/>'
           '<path d="M7 12h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>'),
    "settings": ('<circle cx="9" cy="9" r="2.4" stroke="currentColor" stroke-width="1.5"/>'
                 '<path d="M9 1.8v2M9 14.2v2M16.2 9h-2M3.8 9h-2M14.1 3.9l-1.4 1.4M5.3 12.7l-1.4 1.4M14.1 14.1l-1.4-1.4M5.3 5.3L3.9 3.9" '
                 'stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'),
    # 通用操作
    "plus": '<path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "refresh": ('<path d="M13.6 8a5.6 5.6 0 1 1-1.7-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>'
                '<path d="M13.8 1.8v2.6h-2.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "close": '<path d="M4.5 4.5l9 9M13.5 4.5l-9 9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    "paperclip": ('<path d="M12.8 7.4L7.9 12.3a3.2 3.2 0 0 1-4.5-4.5l5.5-5.5a2.1 2.1 0 0 1 3 3l-5.5 5.5a1.1 1.1 0 0 1-1.5-1.5l4.9-4.9" '
                  'stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>'),
    "lock": ('<rect x="4.5" y="10" width="15" height="10" rx="2.5" stroke="currentColor" stroke-width="1.8"/>'
             '<path d="M8 10V7.5a4 4 0 0 1 8 0V10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
             '<circle cx="12" cy="15" r="1.6" fill="currentColor"/>'),
    "lock_plus": ('<rect x="4.5" y="10" width="15" height="10" rx="2.5" stroke="currentColor" stroke-width="1.8"/>'
                  '<path d="M8 10V7.5a4 4 0 0 1 8 0V10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
                  '<path d="M12 13.4v3.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'),
    "eye": ('<path d="M2 10s3-5.2 8-5.2S18 10 18 10s-3 5.2-8 5.2S2 10 2 10z" stroke="currentColor" stroke-width="1.5"/>'
            '<circle cx="10" cy="10" r="2.2" stroke="currentColor" stroke-width="1.5"/>'),
    "shield": ('<path d="M8 1.8l5 2v3.9c0 3.2-2.1 5.4-5 6.5-2.9-1.1-5-3.3-5-6.5V3.8l5-2z" '
               'stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>'
               '<path d="M5.8 8l1.5 1.5 2.9-3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>'),
    "info": ('<circle cx="8" cy="8" r="6.6" stroke="currentColor" stroke-width="1.4"/>'
             '<path d="M8 7.2v3.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
             '<circle cx="8" cy="5" r=".9" fill="currentColor"/>'),
    "check_gold": ('<circle cx="9" cy="9" r="8" stroke="currentColor" stroke-width="1.6"/>'
                   '<path d="M5.6 9.2l2.2 2.2 4.6-4.8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "bell": '<path d="M9 2v1.5M4.5 12.5h9M5.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5l1 1.5h-9l1-1.5z" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "empty": ('<circle cx="9" cy="9" r="6.5" stroke="currentColor" stroke-width="1.3"/>'
              '<path d="M6.2 11.8c.6-2 2-3 2.8-3.3.8.3 2.2 1.3 2.8 3.3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>'
              '<circle cx="7" cy="7.2" r=".9" fill="currentColor"/><circle cx="11" cy="7.2" r=".9" fill="currentColor"/>'),
}


def icon(name: str, color: str = TEXT_2, size: int = 17) -> str:
    """返回指定颜色的内联 SVG 字符串（供 QIcon/QSvgRenderer 使用）。"""
    body = _ICON_PATHS.get(name, _ICON_PATHS["info"])
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 18 18" fill="none" '
            f'xmlns="http://www.w3.org/2000/svg">{body.replace("currentColor", color)}</svg>')

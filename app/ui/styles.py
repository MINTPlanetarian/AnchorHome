"""v2.0 全局 QSS 样式表（UI 设计规范第 5 章）。

所有颜色/字号/圆角从 app.ui.theme 令牌取值，不散落硬编码。
"""
from app.ui import theme

# act / act-primary 按钮几何常量（QSS 与 ActionCell 共用，改这里两侧同步生效）：
# min-width 为内容宽，总宽 = min-width + padding*2 + border*2
ACT_MIN_WIDTH = 40
ACT_PRIMARY_MIN_WIDTH = 72
ACT_PAD_X = 12
ACT_BORDER = 1
# 表格单元格 ::item 左右内边距：文字与单元格控件的留白；
# 该值会从 setCellWidget 控件的实际可用宽度中扣除，autofit_columns 依赖此常量补偿
TABLE_ITEM_PAD_X = 10


def _qss() -> str:
    t = theme
    return f"""
/* ===== 全局 ===== */
QWidget {{
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: {t.FS_BODY}px;
    color: {t.TEXT};
}}
QMainWindow, QDialog {{
    background: {t.BG};
}}
QToolTip {{
    background: {t.TOOLTIP_BG}; color: #ffffff; border: none;
    padding: 6px 10px; border-radius: 6px; font-size: 12px;
}}
QLabel {{ background: transparent; }}

/* ===== 页面级通用 ===== */
#pageTitle {{ font-size: 20px; font-weight: 700; color: {t.TEXT}; }}
#pageSubtitle {{ color: {t.TEXT_3}; font-size: 12px; }}
#panelTitle {{ font-size: 15px; font-weight: 700; color: {t.TEXT}; }}

/* ===== 按钮变体（property: variant） ===== */
QPushButton {{
    min-height: 36px; padding: 0 16px; border-radius: 8px;
    font-size: 14px; font-weight: 500; background: transparent; border: none;
}}
QPushButton[variant="primary"] {{
    background: {t.BLUE}; color: #ffffff;
}}
QPushButton[variant="primary"]:hover {{ background: {t.BLUE_DARK}; }}
QPushButton[variant="primary"]:pressed {{ background: {t.BRAND_FROM}; }}
QPushButton[variant="primary"]:disabled {{ background: #A8C8F5; color: #ffffff; }}
QPushButton[variant="ghost"] {{
    background: {t.SURFACE}; color: {t.TEXT_2}; border: 1px solid {t.LINE_STRONG};
}}
QPushButton[variant="ghost"]:hover {{ color: {t.BLUE}; border-color: {t.BLUE_LINE}; background: {t.BLUE_BG}; }}
QPushButton[variant="danger"] {{
    background: {t.SURFACE}; color: {t.RED}; border: 1px solid {t.RED};
}}
QPushButton[variant="danger"]:hover {{ background: {t.RED}; color: #ffffff; }}
QPushButton[variant="danger"]:disabled {{ color: {t.TEXT_3}; border-color: {t.LINE}; background: {t.SURFACE}; }}

/* 表格操作列按钮（ActionCell 内，由组件设置 property） */
QPushButton[variant="act"] {{
    min-width: {ACT_MIN_WIDTH}px; padding: 0 {ACT_PAD_X}px; border-radius: 6px;
    font-size: 13px; font-weight: 500; color: {t.BLUE}; background: {t.SURFACE};
    border: {ACT_BORDER}px solid {t.BLUE_LINE};
}}
QPushButton[variant="act"]:hover {{ background: {t.BLUE}; border-color: {t.BLUE}; color: #ffffff; }}
QPushButton[variant="act-primary"] {{
    min-width: {ACT_PRIMARY_MIN_WIDTH}px; padding: 0 {ACT_PAD_X}px; border-radius: 6px;
    font-size: 13px; font-weight: 500; color: #ffffff; background: {t.BLUE}; border: none;
}}
QPushButton[variant="act-primary"]:hover {{ background: {t.BLUE_DARK}; }}
QToolButton[variant="more"] {{
    height: 28px; padding: 0 12px; border-radius: 6px; font-size: 15px;
    color: {t.TEXT_2}; background: {t.SURFACE}; border: 1px solid {t.LINE_STRONG};
}}
QToolButton[variant="more"]::menu-indicator {{ image: none; width: 0; height: 0; }}
QToolButton[variant="more"]:hover {{ color: {t.BLUE}; border-color: {t.BLUE_LINE}; background: {t.BLUE_BG}; }}

/* ===== 侧边栏 ===== */
QFrame#sidebar {{ background: {t.SURFACE}; border-right: 1px solid {t.LINE}; }}
#sideLogo {{ border-bottom: 1px solid {t.LINE}; }}
#sideLogoTitle {{ font-size: 16px; font-weight: 700; letter-spacing: .04em; color: {t.TEXT}; }}
#sideLogoSlogan {{ font-size: 11px; color: {t.TEXT_3}; letter-spacing: .1em; }}
QPushButton[nav="item"] {{
    height: 40px; text-align: left; padding-left: 12px; border-radius: 8px;
    border: none; color: {t.TEXT_2}; font-weight: 500; font-size: 14px; background: transparent;
}}
QPushButton[nav="item"]:hover {{ background: {t.BG}; color: {t.TEXT}; }}
QPushButton[nav="item"]:checked {{ background: {t.BLUE_BG}; color: {t.BLUE}; font-weight: 600; }}
#sideVersion {{ color: {t.TEXT_3}; font-size: 11.5px; padding: 10px 12px 2px; }}
#sideBottom {{ border-top: 1px solid {t.LINE}; }}

/* ===== Topbar / Statusbar ===== */
#topbar {{ background: {t.SURFACE}; border-bottom: 1px solid {t.LINE}; }}
#topbarTitle {{ font-size: 18px; font-weight: 700; color: {t.TEXT}; }}
#topbarDesc {{ color: {t.TEXT_3}; font-size: 13px; }}
#statusbar {{ background: {t.SURFACE}; border-top: 1px solid {t.LINE}; color: {t.TEXT_3}; font-size: 12px; }}
#statusDot {{ background: {t.GREEN}; border-radius: 4px; }}

/* ===== 内容滚动区 ===== */
#contentScroll {{ background: {t.BG}; border: none; }}
#contentScroll > QWidget > QWidget {{ background: {t.BG}; }}

/* ===== 卡片 ===== */
QFrame#card {{
    background: {t.SURFACE}; border: 1px solid {t.LINE};
    border-radius: {t.RADIUS_LG}px;
}}

/* ===== 统计卡片 ===== */
QFrame#statCard {{
    background: {t.SURFACE}; border: 1px solid {t.LINE};
    border-radius: {t.RADIUS_LG}px;
}}
QFrame#statCard[hero="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {t.BRAND_FROM}, stop:1 {t.BLUE});
    border: none;
}}
#statLabel {{ font-size: 13px; color: {t.TEXT_2}; }}
#statValue {{ font-size: 24px; font-weight: 700; }}
#statSub {{ font-size: 12px; color: {t.TEXT_3}; }}
QFrame#statCard[hero="true"] #statLabel,
QFrame#statCard[hero="true"] #statSub {{ color: rgba(255,255,255,.78); }}
QFrame#statCard[hero="true"] #statValue {{ color: #ffffff; }}

/* ===== 标签（Tag） ===== */
QLabel[tag="blue"]   {{ background: {t.BLUE_BG};   color: {t.BLUE}; }}
QLabel[tag="green"]  {{ background: {t.GREEN_BG};  color: {t.GREEN}; }}
QLabel[tag="orange"] {{ background: {t.ORANGE_BG}; color: {t.ORANGE}; }}
QLabel[tag="gray"]   {{ background: #F0F2F5;       color: {t.TEXT_2}; }}
QLabel[tag="gold"]   {{ background: {t.GOLD_BG};   color: {t.GOLD}; }}
QLabel[tag="red"]    {{ background: {t.RED_BG};    color: {t.RED}; }}
QLabel[tag] {{
    height: 24px; padding: 0 10px; border-radius: 12px;
    font-size: 12px; font-weight: 500;
}}

/* ===== 筛选 Chip ===== */
QPushButton[chip="true"] {{
    height: 32px; padding: 0 14px; border-radius: 16px;
    font-size: 13px; font-weight: 500;
    color: {t.TEXT_2}; background: {t.SURFACE}; border: 1px solid {t.LINE_STRONG};
}}
QPushButton[chip="true"]:hover {{ color: {t.BLUE}; border-color: {t.BLUE_LINE}; }}
QPushButton[chip="true"]:checked {{ background: {t.BLUE}; border-color: {t.BLUE}; color: #ffffff; }}

/* ===== 表格 ===== */
QTableWidget {{
    background: {t.SURFACE}; border: 1px solid {t.LINE}; border-radius: {t.RADIUS_LG}px;
    gridline-color: {t.LINE}; selection-background-color: transparent;
    selection-color: {t.TEXT}; outline: none;
}}
QTableWidget::item {{ padding: 0 {TABLE_ITEM_PAD_X}px; border-bottom: 1px solid {t.LINE}; }}
QTableWidget::item:hover {{ background: {t.TABLE_HOVER}; }}
QTableWidget::item:selected {{ background: {t.BLUE_BG}; color: {t.TEXT}; }}
QHeaderView::section {{
    background: {t.SURFACE}; border: none; border-bottom: 1px solid {t.LINE};
    padding: 13px {TABLE_ITEM_PAD_X}px; color: {t.TEXT_3}; font-size: {t.FS_TABLE_HEADER}px; font-weight: 500;
}}
QTableCornerButton::section {{ background: {t.SURFACE}; border: none; }}

/* ===== 输入控件 ===== */
QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox, QTextEdit {{
    min-height: 40px; padding: 0 12px; background: {t.SURFACE};
    border: 1px solid {t.LINE_STRONG}; border-radius: 8px;
    font-size: 14px; color: {t.TEXT}; selection-background-color: {t.BLUE_BG};
}}
QTextEdit {{ padding: 8px 12px; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QTextEdit:focus {{
    border-color: {t.BLUE};
}}
QLineEdit:disabled, QDateEdit:disabled, QDoubleSpinBox:disabled {{
    background: {t.INPUT_DISABLED_BG}; color: {t.TEXT_3};
}}
QLineEdit::placeholder {{ color: {t.TEXT_3}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {t.TEXT_3};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {t.SURFACE}; border: 1px solid {t.LINE};
    border-radius: 8px; padding: 6px; outline: none;
}}
QComboBox QAbstractItemView::item {{ height: 34px; border-radius: 6px; padding: 0 10px; }}
QComboBox QAbstractItemView::item:selected {{ background: {t.BLUE_BG}; color: {t.BLUE}; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; height: 0; border: none; }}
QDateEdit::drop-down {{ border: none; width: 26px; }}

/* ===== 日历弹窗 ===== */
QCalendarWidget QWidget {{ alternate-background-color: {t.SURFACE}; }}
QCalendarWidget QToolButton {{ color: {t.TEXT}; background: transparent; border-radius: 6px; height: 28px; font-weight: 500; }}
QCalendarWidget QToolButton:hover {{ background: {t.BLUE_BG}; color: {t.BLUE}; }}
QCalendarWidget QAbstractItemView:enabled {{
    background: {t.SURFACE}; color: {t.TEXT};
    selection-background-color: {t.BLUE}; selection-color: #ffffff; outline: none;
}}
QCalendarWidget QAbstractItemView:disabled {{ color: {t.TEXT_3}; }}

/* ===== ⋯ 菜单 ===== */
QMenu {{
    background: {t.SURFACE}; border: 1px solid {t.LINE}; border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{ height: 30px; padding: 0 12px; border-radius: 6px; font-size: 13px; }}
QMenu::item:selected {{ background: {t.BG}; }}
QMenu::item[danger="true"] {{ color: {t.RED}; }}
QMenu::item[danger="true"]:selected {{ background: {t.RED_BG}; }}

/* ===== 滚动条 ===== */
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #D4DAE3; border-radius: 5px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: #B9C2CF; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #D4DAE3; border-radius: 5px; min-width: 40px; }}
QScrollBar::handle:horizontal:hover {{ background: #B9C2CF; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ===== 进度条（负债页） ===== */
QProgressBar {{
    height: 6px; background: #EEF1F5; border-radius: 3px; border: none; text-align: center;
    font-size: 12px; color: {t.TEXT_2};
}}
QProgressBar::chunk {{ background: {t.BLUE}; border-radius: 3px; }}

/* ===== 提示条 Banner ===== */
QFrame#banner {{
    background: {t.BLUE_BG}; border: 1px solid {t.BLUE_LINE};
    border-radius: 10px;
}}
QFrame#banner[variant="orange"] {{ background: {t.ORANGE_BG}; border-color: #F5D9A8; }}
QFrame#banner[variant="orange"] QLabel {{ color: {t.ORANGE}; }}
QFrame#banner QLabel {{ color: #1D4FA3; font-size: 13px; }}
QFrame#banner QPushButton {{ border: none; background: transparent; color: #1D4FA3; font-size: 16px; }}
QFrame#banner[variant="orange"] QPushButton {{ color: {t.ORANGE}; }}

/* ===== 弹窗 Modal ===== */
QDialog {{
    background: {t.SURFACE};
}}
#modalHead {{ border-bottom: 1px solid {t.LINE}; }}
#modalTitle {{ font-size: 17px; font-weight: 700; color: {t.TEXT}; }}
#modalClose {{
    width: 30px; height: 30px; border-radius: 6px;
    color: {t.TEXT_3}; font-size: 15px; border: none; background: transparent;
}}
#modalClose:hover {{ background: {t.BG}; color: {t.TEXT}; }}
#formLabel {{ font-size: 13px; font-weight: 500; color: {t.TEXT_2}; }}
#formRequired {{ color: {t.RED}; }}
#formHint {{ font-size: 12px; color: {t.TEXT_3}; }}
#formHint[warn="true"] {{ color: {t.ORANGE}; }}

/* ===== Radio Pills（保险子类型二选一） ===== */
QPushButton[pill="true"] {{
    min-height: 40px; border: 1px solid {t.LINE_STRONG}; border-radius: 8px;
    background: {t.SURFACE}; font-size: 14px; color: {t.TEXT_2}; font-weight: 500;
}}
QPushButton[pill="true"]:hover {{ border-color: {t.BLUE_LINE}; color: {t.BLUE}; }}
QPushButton[pill="true"]:checked {{
    border-color: {t.BLUE}; background: {t.BLUE_BG}; color: {t.BLUE};
}}

/* ===== 复选框 ===== */
QCheckBox {{ font-size: 13px; color: {t.TEXT_2}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border: 1px solid {t.LINE_STRONG};
    border-radius: 4px; background: {t.SURFACE};
}}
QCheckBox::indicator:checked {{ background: {t.BLUE}; border-color: {t.BLUE}; }}
QCheckBox::indicator:hover {{ border-color: {t.BLUE}; }}

/* ===== 分组卡片（设置页） ===== */
QGroupBox {{
    background: {t.SURFACE}; border: 1px solid {t.LINE};
    border-radius: 14px; margin-top: 28px; padding: 22px 20px 18px;
    font-size: 15px; font-weight: 700; color: {t.TEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 20px; padding: 2px 12px;
    background: {t.SURFACE}; border-radius: 4px;
    /* 不设 top: title 落在 margin 顶部,不与 border 重叠,完整显示 */
}}

/* ===== AI 聊天气泡 ===== */
#chatBubbleUser {{
    background: {t.BLUE}; color: #ffffff; border-radius: 14px;
    border-bottom-right-radius: 4px; padding: 10px 14px;
}}
#chatBubbleAI {{
    background: {t.SURFACE}; border: 1px solid {t.LINE}; border-radius: 14px;
    border-top-left-radius: 4px; padding: 10px 14px;
}}
#chatInput {{ background: {t.SURFACE}; border: 1px solid {t.LINE}; border-radius: 12px; }}
"""


APP_QSS = _qss()

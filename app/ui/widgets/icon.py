"""SVG 图标工具：把 theme.icon() 生成的内联 SVG 渲染为 QIcon。

统一 1.5px 线性描边风格（UI 设计规范 2.2），全应用图标唯一出处。
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.ui import theme


def svg_to_icon(svg: str, size: int = 17) -> QIcon:
    """把内联 SVG 字符串渲染为指定像素的 QIcon。"""
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    return QIcon(pm)


def logo_pixmap(icon_path: str, logical_size: int) -> QPixmap:
    """按屏幕 DPR 加载应用 logo，避免高 DPI 屏上放大发虚。

    原写法 QPixmap(path).scaled(逻辑尺寸) 产出的是 1x 位图（如 48×48），
    在 150%/200% 缩放的屏幕上被系统拉伸到 72/96 物理像素就模糊了。
    Qt6 的 QIcon.pixmap(逻辑尺寸) 会自动按屏幕 DPR 选最接近的 ICO 帧
    （本图标含 256px 大帧）放大到物理像素并标好 devicePixelRatio——
    直接传逻辑尺寸即可，切勿自己再乘 dpr（那会让显示尺寸翻倍）。
    """
    pm = QIcon(icon_path).pixmap(QSize(logical_size, logical_size))
    return pm


def nav_icon(name: str, color: str = theme.TEXT_2, size: int = 17) -> QIcon:
    """侧边栏导航图标（默认次要文字色，激活态由调用方传 BLUE）。"""
    return svg_to_icon(theme.icon(name, color, size), size)


def find_app_icon() -> str | None:
    """定位应用图标文件（安航家资.ico）。找不到时返回 None。

    候选路径按优先级：
        1. frozen 运行态：ico 经打包进 exe，位于 sys._MEIPASS 根目录；
        2. 项目根目录 / exe 同级的 安航家资.ico。

    原先 main.py 与 main_window.py 各有一份实现，且 login_dialog / settings_page
    反向导入了 main_window 的私有函数 _find_app_icon，现统一到本模块。
    """
    # app/ui/widgets/icon.py → 上溯四级：widgets → ui → app → 项目根
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    candidates = [
        os.path.join(root, "安航家资.ico"),
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(0, os.path.join(getattr(sys, "_MEIPASS", root), "安航家资.ico"))
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

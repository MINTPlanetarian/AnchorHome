"""公共工具函数。"""
from datetime import datetime


def now_str() -> str:
    """返回当前时间的 ISO 格式字符串（YYYY-MM-DD HH:MM:SS），用于 created_at / updated_at。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    """返回今日日期字符串（YYYY-MM-DD）。"""
    return datetime.now().strftime("%Y-%m-%d")

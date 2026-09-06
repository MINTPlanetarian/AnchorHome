"""全局配置读写模块。

封装 settings 表（key/value）的读写，提供常用配置项的便捷访问。
敏感项（如 AI API Key）由 security 模块加密后存入。
"""
from app.database import get_conn


def get_setting(key: str, default: str | None = None) -> str | None:
    """读取单个配置项。不存在或值为 NULL 时返回 default。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row is not None and row["value"] is not None:
            return row["value"]
        return default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    """写入单个配置项（存在则更新，不存在则插入）。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
    finally:
        conn.close()


def delete_setting(key: str) -> None:
    """删除单个配置项（如清空 API Key 输入框保存时撤销已存密钥）。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM settings WHERE key=?", (key,))
    finally:
        conn.close()


def get_setting_int(key: str, default: int = 0) -> int:
    """读取整数型设置；值为非数字（脏数据）时返回 default。

    settings 是明文表，值可能被外部工具改坏。解析必须兜底，否则 int() 抛
    ValueError 会让调用方（如登录页 is_locked）在启动阶段直接崩溃。
    """
    try:
        return int(str(get_setting(key, "") or "").strip())
    except (TypeError, ValueError):
        return default


def get_setting_float(key: str, default: float = 0.0) -> float:
    """读取浮点型设置；值为非数字（脏数据）时返回 default。"""
    try:
        return float(str(get_setting(key, "") or "").strip())
    except (TypeError, ValueError):
        return default


def has_password() -> bool:
    """是否已设置启动密码（password_hash 是否存在）。"""
    return bool(get_setting("password_hash"))


# ---------------------------------------------------------------------------
# 便捷访问：行情刷新相关
# ---------------------------------------------------------------------------
def get_refresh_on_startup() -> bool:
    """启动时是否自动刷新行情。"""
    return get_setting("refresh_on_startup", "0") == "1"


def get_refresh_interval() -> int:
    """定时刷新间隔（分钟），0 表示关闭。"""
    return get_setting_int("refresh_interval_minutes", 0)

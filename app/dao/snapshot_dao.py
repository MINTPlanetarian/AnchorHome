"""资产快照数据访问对象（DAO）。"""
from app.database import get_conn
from app.utils import now_str, today_str


def get_snapshot_by_date(date_str: str) -> dict | None:
    """按日期查询快照。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM asset_snapshots WHERE snapshot_date=?", (date_str,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_snapshot(date_str, total_assets, total_liabilities, net_worth) -> None:
    """插入一条快照（每天最多一条，snapshot_date 唯一）。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO asset_snapshots
                    (snapshot_date, total_assets, total_liabilities, net_worth, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (date_str, total_assets, total_liabilities, net_worth, now_str()),
            )
    finally:
        conn.close()


def list_snapshots(start_date: str | None = None) -> list[dict]:
    """列出快照，可按起始日期过滤，按日期升序返回。"""
    conn = get_conn()
    try:
        if start_date:
            rows = conn.execute(
                "SELECT * FROM asset_snapshots WHERE snapshot_date >= ? ORDER BY snapshot_date",
                (start_date,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM asset_snapshots ORDER BY snapshot_date"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_snapshot_before(date_str: str, inclusive: bool = True) -> dict | None:
    """查询早于 date_str 的最近一条快照（inclusive=True 时含当天）。

    供"较 7 日前"环比（总览页）与快照明细表首行环比（报表页）取基期。
    """
    op = "<=" if inclusive else "<"
    conn = get_conn()
    try:
        row = conn.execute(
            f"SELECT * FROM asset_snapshots WHERE snapshot_date {op} ?"
            " ORDER BY snapshot_date DESC LIMIT 1",
            (date_str,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

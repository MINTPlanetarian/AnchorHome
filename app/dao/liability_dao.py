"""负债与还款历史数据访问对象（DAO）。"""
from app.database import get_conn
from app.utils import now_str


def create_liability(name, type_, total_amount, remaining, interest_rate=None,
                     monthly_payment=None, note=None) -> int:
    """新增负债，返回 id。"""
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO liabilities
                    (name, type, total_amount, remaining, interest_rate, monthly_payment, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, type_, total_amount, remaining, interest_rate,
                 monthly_payment, note, now_str(), now_str()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_liability(liability_id, name, type_, total_amount, remaining,
                     interest_rate, monthly_payment, note) -> None:
    """更新负债。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                """
                UPDATE liabilities
                   SET name=?, type=?, total_amount=?, remaining=?, interest_rate=?,
                       monthly_payment=?, note=?, updated_at=?
                 WHERE id=?
                """,
                (name, type_, total_amount, remaining, interest_rate,
                 monthly_payment, note, now_str(), liability_id),
            )
    finally:
        conn.close()


def delete_liability(liability_id) -> None:
    """删除负债（还款历史随外键级联删除）。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM liabilities WHERE id=?", (liability_id,))
    finally:
        conn.close()


def get_liability(liability_id) -> dict | None:
    """按 id 查询负债。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM liabilities WHERE id=?", (liability_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_liabilities() -> list[dict]:
    """列出全部负债。"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM liabilities ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 还款
# ---------------------------------------------------------------------------
def repay(liability_id, amount, repay_date) -> None:
    """执行还款：扣减当前余额（最低扣到 0），并写入一条还款历史。

    用事务保证两步原子性。
    """
    conn = get_conn()
    try:
        with conn:
            row = conn.execute(
                "SELECT remaining FROM liabilities WHERE id=?", (liability_id,)
            ).fetchone()
            if row is None:
                raise ValueError("负债记录不存在")
            new_remaining = max(0.0, row["remaining"] - amount)
            conn.execute(
                "UPDATE liabilities SET remaining=?, updated_at=? WHERE id=?",
                (new_remaining, now_str(), liability_id),
            )
            conn.execute(
                """
                INSERT INTO repayment_history (liability_id, repay_date, amount, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (liability_id, repay_date, amount, now_str()),
            )
    finally:
        conn.close()


def list_repayments(liability_id) -> list[dict]:
    """列出某负债的全部还款历史（按时间倒序）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM repayment_history
             WHERE liability_id=?
             ORDER BY id DESC
            """,
            (liability_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def repay_summary_since(start_date: str | None) -> tuple[int, float]:
    """统计自 start_date（含当天）以来的还款笔数与总额；None 表示不限时间。

    供报表页负债构成卡显示"期间已还款 ¥x · n 笔"。
    """
    conn = get_conn()
    try:
        if start_date is None:
            row = conn.execute(
                "SELECT COUNT(*) AS c, COALESCE(SUM(amount), 0) AS s FROM repayment_history"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c, COALESCE(SUM(amount), 0) AS s"
                " FROM repayment_history WHERE repay_date >= ?",
                (start_date,),
            ).fetchone()
        return row["c"], float(row["s"] or 0.0)
    finally:
        conn.close()


def undo_last_repayment(liability_id) -> bool:
    """撤销最近一次还款：删除该条历史并把余额加回。返回是否有可撤销记录。"""
    conn = get_conn()
    try:
        with conn:
            row = conn.execute(
                """
                SELECT * FROM repayment_history
                 WHERE liability_id=?
                 ORDER BY id DESC LIMIT 1
                """,
                (liability_id,),
            ).fetchone()
            if row is None:
                return False
            # 删除历史记录
            conn.execute("DELETE FROM repayment_history WHERE id=?", (row["id"],))
            # 余额加回
            conn.execute(
                "UPDATE liabilities SET remaining = remaining + ?, updated_at=? WHERE id=?",
                (row["amount"], now_str(), liability_id),
            )
            return True
    finally:
        conn.close()

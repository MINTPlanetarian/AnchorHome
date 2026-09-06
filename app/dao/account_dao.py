"""账户数据访问对象（DAO）。

v1.1：账户关联持有人（member_id），查询 JOIN members 带出持有人姓名。
v1.2：新增 available_date（资金可用日期）+ list_liquid/list_maturing 流动性查询。
"""
from datetime import datetime, timedelta

from app.database import get_conn
from app.utils import now_str, today_str

# 查询账户时带出持有人姓名的公共字段
_SELECT_WITH_MEMBER = """
    SELECT a.*, m.name AS member_name
      FROM accounts a
      LEFT JOIN members m ON m.id = a.member_id
"""


def create_account(name, type_, currency="CNY", balance=0.0, institution=None,
                   note=None, member_id=None, available_date=None) -> int:
    """新增账户，返回新账户 id。

    member_id 为 None 时归属默认成员（id 最小的成员）。
    available_date 为 None 表示"随时可用"（仅理财类型使用）。
    """
    conn = get_conn()
    try:
        with conn:
            if member_id is None:
                row = conn.execute(
                    "SELECT id FROM members ORDER BY id LIMIT 1"
                ).fetchone()
                member_id = row["id"] if row else None
            cur = conn.execute(
                """
                INSERT INTO accounts
                    (name, type, currency, balance, institution, note, member_id,
                     available_date, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (name, type_, currency, balance, institution, note, member_id,
                 available_date, now_str(), now_str()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_account(account_id, name, type_, currency, balance, institution,
                   note, member_id, available_date=None) -> None:
    """更新账户字段（不含 is_active，避免误改停用状态）。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                """
                UPDATE accounts
                   SET name=?, type=?, currency=?, balance=?, institution=?,
                       note=?, member_id=?, available_date=?, updated_at=?
                 WHERE id=?
                """,
                (name, type_, currency, balance, institution, note, member_id,
                 available_date, now_str(), account_id),
            )
    finally:
        conn.close()


def delete_account(account_id) -> None:
    """删除账户（持仓随外键级联删除，由 UI 层先行提示）。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    finally:
        conn.close()


def get_account(account_id) -> dict | None:
    """按 id 查询账户（含持有人姓名）。"""
    conn = get_conn()
    try:
        row = conn.execute(
            _SELECT_WITH_MEMBER + " WHERE a.id=?", (account_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_accounts(active_only=False, member_id=None) -> list[dict]:
    """列出账户（含持有人姓名）。

    active_only=True 只返回启用账户；member_id 指定时按持有人过滤。
    """
    conn = get_conn()
    try:
        sql = _SELECT_WITH_MEMBER
        where = []
        params = []
        if active_only:
            where.append("a.is_active=1")
        if member_id is not None:
            where.append("a.member_id=?")
            params.append(member_id)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY a.id"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_by_member(member_id) -> list[dict]:
    """列出某成员名下的全部账户（含停用）。"""
    return list_accounts(active_only=False, member_id=member_id)


def list_liquid(member_id=None) -> list[dict]:
    """按 PRD v1.2 3.1 口径查询"立即可用"的账户：
    现金类型 + 理财类型中 available_date 为空或 ≤ 今天的账户。
    """
    conn = get_conn()
    try:
        sql = _SELECT_WITH_MEMBER
        where = [
            "a.is_active=1",
            "(a.type='cash' OR (a.type='wealth' AND (a.available_date IS NULL OR a.available_date <= ?)))",
        ]
        params = [today_str()]
        if member_id is not None:
            where.append("a.member_id=?")
            params.append(member_id)
        sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY a.id"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_maturing(days=7) -> list[dict]:
    """查询未来 days 天内到期（含已过期未处理）的理财账户，供到期提醒。"""
    conn = get_conn()
    try:
        deadline = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        sql = _SELECT_WITH_MEMBER + """
         WHERE a.is_active=1 AND a.type='wealth'
           AND a.available_date IS NOT NULL AND a.available_date <= ?
         ORDER BY a.available_date
        """
        rows = conn.execute(sql, (deadline,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_active(account_id, is_active: bool) -> None:
    """停用 / 启用账户。停用账户不计入总资产。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "UPDATE accounts SET is_active=?, updated_at=? WHERE id=?",
                (1 if is_active else 0, now_str(), account_id),
            )
    finally:
        conn.close()


def has_holdings(account_id) -> bool:
    """该账户下是否存在持仓（删除账户前检查）。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM holdings WHERE account_id=?", (account_id,)
        ).fetchone()
        return row["c"] > 0
    finally:
        conn.close()

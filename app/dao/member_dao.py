"""家庭成员（账户持有人）数据访问对象（DAO）。"""
from app.database import get_conn
from app.utils import now_str

# 成员关系枚举（PRD v1.1 FR-N1）
RELATIONS = ["本人", "配偶", "子女", "父母", "其他"]


def create_member(name: str, relation: str = "本人", note: str | None = None) -> int:
    """新增成员，返回 id。"""
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO members (name, relation, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, relation, note, now_str(), now_str()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_member(member_id: int, name: str, relation: str, note: str | None) -> None:
    """更新成员。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                """
                UPDATE members
                   SET name=?, relation=?, note=?, updated_at=?
                 WHERE id=?
                """,
                (name, relation, note, now_str(), member_id),
            )
    finally:
        conn.close()


def delete_member(member_id: int) -> None:
    """删除成员。调用方须先用 count_accounts 校验名下无账户。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM members WHERE id=?", (member_id,))
    finally:
        conn.close()


def get_member(member_id: int) -> dict | None:
    """按 id 查询成员。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_members() -> list[dict]:
    """列出全部成员（按 id 升序，默认"本人"排最前）。"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM members ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def default_member_id() -> int | None:
    """返回默认成员（id 最小的成员）的 id，无成员时返回 None。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT id FROM members ORDER BY id LIMIT 1").fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def count_accounts(member_id: int) -> int:
    """统计某成员名下的账户数（删除成员前校验用）。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM accounts WHERE member_id=?", (member_id,)
        ).fetchone()
        return row["c"]
    finally:
        conn.close()


def count_accounts_by_member() -> dict[int, int]:
    """一次性统计所有成员名下的账户数，返回 {member_id: 数量}。

    列表渲染"名下账户数"列和该列排序键各要一次，逐行查会变成 N+1；
    一次 GROUP BY 取回即可。
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT member_id, COUNT(*) AS c FROM accounts "
            "WHERE member_id IS NOT NULL GROUP BY member_id"
        ).fetchall()
        return {r["member_id"]: r["c"] for r in rows}
    finally:
        conn.close()

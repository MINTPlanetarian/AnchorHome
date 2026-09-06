"""资产台账与附件数据访问对象（DAO）。"""
from app.database import get_conn
from app.utils import now_str


# ---------------------------------------------------------------------------
# 资产台账
# ---------------------------------------------------------------------------
def create_asset(name, type_, value, purchase_date=None, note=None,
                 insurance_subtype=None, coverage=None, annual_premium=None,
                 insured_member_id=None) -> int:
    """新增资产项，返回 id。

    insurance_subtype/coverage/annual_premium/insured_member_id 仅保险类有意义；
    insured_member_id 为被保险人（关联 members.id）；
    保障型保险无现金价值，value 强制 0（不计入总资产）；储蓄型 value 表示现金价值。
    """
    # 口径守护：保障型保险现金价值无意义，强制 0
    if type_ == "insurance" and insurance_subtype == "protection":
        value = 0.0
    # 非保险类不存被保险人
    if type_ != "insurance":
        insured_member_id = None
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO assets
                    (name, type, value, purchase_date, note,
                     insurance_subtype, coverage, annual_premium, insured_member_id,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, type_, value, purchase_date, note,
                 insurance_subtype, coverage, annual_premium, insured_member_id,
                 now_str(), now_str()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_asset(asset_id, name, type_, value, purchase_date, note,
                 insurance_subtype=None, coverage=None, annual_premium=None,
                 insured_member_id=None) -> None:
    """更新资产项。"""
    # 口径守护：保障型保险现金价值无意义，强制 0
    if type_ == "insurance" and insurance_subtype == "protection":
        value = 0.0
    if type_ != "insurance":
        insured_member_id = None
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                """
                UPDATE assets
                   SET name=?, type=?, value=?, purchase_date=?, note=?,
                       insurance_subtype=?, coverage=?, annual_premium=?,
                       insured_member_id=?, updated_at=?
                 WHERE id=?
                """,
                (name, type_, value, purchase_date, note,
                 insurance_subtype, coverage, annual_premium, insured_member_id,
                 now_str(), asset_id),
            )
    finally:
        conn.close()


def delete_asset(asset_id) -> None:
    """删除资产项（附件随外键级联删除，文件需由调用方另行清理）。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM assets WHERE id=?", (asset_id,))
    finally:
        conn.close()


def get_asset(asset_id) -> dict | None:
    """按 id 查询资产项（带被保险人姓名 insured_name）。"""
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT a.*, m.name AS insured_name
              FROM assets a
              LEFT JOIN members m ON m.id = a.insured_member_id
             WHERE a.id=?
            """,
            (asset_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_assets() -> list[dict]:
    """列出全部资产项（带被保险人姓名 insured_name）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT a.*, m.name AS insured_name
              FROM assets a
              LEFT JOIN members m ON m.id = a.insured_member_id
             ORDER BY a.id
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 附件
# ---------------------------------------------------------------------------
def add_attachment(asset_id, file_name, file_path) -> int:
    """新增附件记录（file_path 为相对路径，如 attachments/xxx.jpg）。"""
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO attachments (asset_id, file_name, file_path, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (asset_id, file_name, file_path, now_str()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def list_attachments(asset_id) -> list[dict]:
    """列出某资产项的全部附件。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM attachments WHERE asset_id=? ORDER BY id", (asset_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_attachments_by_asset() -> dict[int, int]:
    """一次性统计各资产项的附件数，返回 {asset_id: 数量}。

    资产列表的"附件"列渲染与按该列排序各要一次，逐行查会变成 N+1；
    一次 GROUP BY 取回即可。
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT asset_id, COUNT(*) AS c FROM attachments GROUP BY asset_id"
        ).fetchall()
        return {r["asset_id"]: r["c"] for r in rows}
    finally:
        conn.close()


def get_attachment(attachment_id) -> dict | None:
    """按 id 查询附件。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM attachments WHERE id=?", (attachment_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_attachment(attachment_id) -> None:
    """删除附件记录。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
    finally:
        conn.close()

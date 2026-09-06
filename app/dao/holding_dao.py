"""持仓数据访问对象（DAO）。"""
from app.database import get_conn
from app.utils import now_str


def create_holding(account_id, code, name, market, quantity, cost_price) -> int:
    """新增持仓。current_price 初始为空，待刷新行情后填充。"""
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO holdings
                    (account_id, code, name, market, quantity, cost_price, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (account_id, code, name, market, quantity, cost_price, now_str(), now_str()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_holding(holding_id, quantity, cost_price) -> None:
    """修改持仓（加仓后手动改数量和成本价）。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                """
                UPDATE holdings
                   SET quantity=?, cost_price=?, updated_at=?
                 WHERE id=?
                """,
                (quantity, cost_price, now_str(), holding_id),
            )
    finally:
        conn.close()


def delete_holding(holding_id) -> None:
    """删除持仓。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM holdings WHERE id=?", (holding_id,))
    finally:
        conn.close()


def list_holdings_by_account(account_id) -> list[dict]:
    """按账户查询持仓列表。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM holdings WHERE account_id=? ORDER BY id", (account_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def holdings_market_value_map() -> dict:
    """一次性聚合所有持仓账户的市值（现价为空用成本价兜底）。

    返回 {account_id: 市值}，供 accounts 页排序/渲染、calc_totals、资产分布等
    批量场景复用，避免逐账户查询造成 N+1。

    口径与单账户 holdings_market_value 一致：quantity * COALESCE(current_price,
    cost_price, 0)；quantity 或价格为空时该笔贡献为 0。
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT account_id,
                   SUM(quantity * COALESCE(current_price, cost_price, 0)) AS mv
              FROM holdings
             GROUP BY account_id
            """
        ).fetchall()
        return {r["account_id"]: (r["mv"] or 0.0) for r in rows}
    finally:
        conn.close()


def list_all_holdings() -> list[dict]:
    """查询全部持仓（含账户信息），用于批量刷新行情。

    仅返回股票/基金账户的持仓（PRD v1.2：行情刷新只对 stock/fund 生效）。
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT h.*, a.name AS account_name, a.is_active AS account_active
              FROM holdings h
              JOIN accounts a ON a.id = h.account_id
             WHERE a.type IN ('stock', 'fund')
             ORDER BY h.id
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# 更新现价的 SQL：单条版与批量版共用，避免同一条语句在两处各维护一份
_UPDATE_PRICE_SQL = """
    UPDATE holdings
       SET current_price=?, price_updated_at=?, updated_at=?
     WHERE code=?
"""


def update_price(code: str, price: float, updated_at: str | None = None) -> None:
    """按代码更新现价与更新时间。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute(_UPDATE_PRICE_SQL, (price, updated_at or now_str(), now_str(), code))
    finally:
        conn.close()


def update_prices(prices: dict) -> None:
    """批量更新现价与更新时间（单事务，避免逐条开关连接）。

    prices: {code: price}
    只入库数字（>0），过滤 None / 非数值 / 异常负值，防止坏数据触发后续崩溃。
    """
    if not prices:
        return
    clean: dict[str, float] = {}
    for code, price in prices.items():
        if isinstance(price, (int, float)) and price == price and 0 < price < 1e9:  # 排除 NaN 与异常
            clean[code] = float(price)
    if not clean:
        return
    ts = now_str()
    conn = get_conn()
    try:
        with conn:
            for code, price in clean.items():
                conn.execute(_UPDATE_PRICE_SQL, (price, ts, ts, code))
    finally:
        conn.close()

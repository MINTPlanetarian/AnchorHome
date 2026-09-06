"""数据库连接与建表模块。

所有模块通过 get_conn() 获取 SQLite 连接。
建表 DDL 严格遵循 PRD 第 5 章定义，所有表含 created_at / updated_at（TEXT，ISO 格式）。
"""
import sqlite3
import sys
from pathlib import Path

from app.utils import now_str


def get_data_dir() -> Path:
    """返回数据目录。

    打包后（frozen）为 exe 同级 data/，开发时为项目根 data/。
    支持环境变量 FAMILY_ASSET_DATA_DIR 覆盖（供测试使用）。
    注意：必须用 sys.executable 判断 frozen 状态，否则 exe 会把数据写到临时目录导致丢失。
    """
    import os

    override = os.environ.get("FAMILY_ASSET_DATA_DIR")
    if override:
        d = Path(override)
        d.mkdir(parents=True, exist_ok=True)
        (d / "attachments").mkdir(exist_ok=True)
        (d / "backups").mkdir(exist_ok=True)
        return d

    if getattr(sys, "frozen", False):
        # PyInstaller 打包后运行
        base = Path(sys.executable).parent
    else:
        # 开发环境：database.py 位于 app/ 下，上溯两级得到项目根
        base = Path(__file__).resolve().parent.parent

    d = base / "data"
    d.mkdir(exist_ok=True)
    (d / "attachments").mkdir(exist_ok=True)
    (d / "backups").mkdir(exist_ok=True)
    return d


# 数据库文件路径（模块加载时的便捷常量；实际连接路径见 db_path()，会实时依据
# FAMILY_ASSET_DATA_DIR，支持测试切换数据目录而无需重启进程）。
DB_PATH = get_data_dir() / "family_asset.db"


def db_path() -> Path:
    """返回当前数据库文件路径，实时依据 FAMILY_ASSET_DATA_DIR 环境变量。"""
    return get_data_dir() / "family_asset.db"


def get_conn() -> sqlite3.Connection:
    """获取一个新的数据库连接，查询结果可按列名访问，并开启外键约束。"""
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # 并发写（如 AI 聊天子线程写库 vs 主线程写库）时最多等待 3 秒，
    # 避免立刻抛 "database is locked"
    conn.execute("PRAGMA busy_timeout = 3000")
    return conn


# ---------------------------------------------------------------------------
# 建表 DDL（严格对应 PRD 第 5 章）
# ---------------------------------------------------------------------------
_DDL_STATEMENTS = [
    # 5.1 settings — 全局设置表（key/value，敏感项存密文）
    """
    CREATE TABLE IF NOT EXISTS settings (
        key         TEXT PRIMARY KEY,
        value       TEXT
    )
    """,
    # 5.2 accounts — 账户表
    """
    CREATE TABLE IF NOT EXISTS accounts (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT    NOT NULL,
        type         TEXT    NOT NULL,
        currency     TEXT    NOT NULL DEFAULT 'CNY',
        balance      REAL    NOT NULL DEFAULT 0,
        institution  TEXT,
        note         TEXT,
        is_active    INTEGER NOT NULL DEFAULT 1,
        created_at   TEXT    NOT NULL,
        updated_at   TEXT    NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_accounts_type ON accounts(type)",
    # 5.3 holdings — 持仓表（股票/基金）
    """
    CREATE TABLE IF NOT EXISTS holdings (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id    INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        code          TEXT    NOT NULL,
        name          TEXT    NOT NULL,
        market        TEXT    NOT NULL,
        quantity      REAL    NOT NULL,
        cost_price    REAL    NOT NULL,
        current_price REAL,
        price_updated_at TEXT,
        created_at    TEXT    NOT NULL,
        updated_at    TEXT    NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_holdings_account ON holdings(account_id)",
    # 5.4 assets — 资产台账表
    """
    CREATE TABLE IF NOT EXISTS assets (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT    NOT NULL,
        type          TEXT    NOT NULL,
        value         REAL    NOT NULL,
        purchase_date TEXT,
        note          TEXT,
        created_at    TEXT    NOT NULL,
        updated_at    TEXT    NOT NULL
    )
    """,
    # 5.5 attachments — 附件表
    """
    CREATE TABLE IF NOT EXISTS attachments (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id    INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        file_name   TEXT    NOT NULL,
        file_path   TEXT    NOT NULL,
        created_at  TEXT    NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_attachments_asset ON attachments(asset_id)",
    # 5.6 liabilities — 负债表
    """
    CREATE TABLE IF NOT EXISTS liabilities (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        type            TEXT    NOT NULL,
        total_amount    REAL    NOT NULL,
        remaining       REAL    NOT NULL,
        interest_rate   REAL,
        monthly_payment REAL,
        note            TEXT,
        created_at      TEXT    NOT NULL,
        updated_at      TEXT    NOT NULL
    )
    """,
    # 5.7 repayment_history — 还款历史表
    """
    CREATE TABLE IF NOT EXISTS repayment_history (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        liability_id INTEGER NOT NULL REFERENCES liabilities(id) ON DELETE CASCADE,
        repay_date   TEXT    NOT NULL,
        amount       REAL    NOT NULL,
        created_at   TEXT    NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_repay_liability ON repayment_history(liability_id)",
    # 5.8 asset_snapshots — 资产快照表（趋势图数据源）
    """
    CREATE TABLE IF NOT EXISTS asset_snapshots (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_date     TEXT    NOT NULL UNIQUE,
        total_assets      REAL    NOT NULL,
        total_liabilities REAL    NOT NULL,
        net_worth         REAL    NOT NULL,
        created_at        TEXT    NOT NULL
    )
    """,
    # 5.9 chat_history — AI 对话历史表
    """
    CREATE TABLE IF NOT EXISTS chat_history (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        role       TEXT    NOT NULL,
        content    TEXT    NOT NULL,
        created_at TEXT    NOT NULL
    )
    """,
    # v1.1 新增 members — 家庭成员（账户持有人）表
    """
    CREATE TABLE IF NOT EXISTS members (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL,
        relation   TEXT    NOT NULL DEFAULT '本人',
        note       TEXT,
        created_at TEXT    NOT NULL,
        updated_at TEXT    NOT NULL
    )
    """,
]


def migrate_to_v1_1(conn: sqlite3.Connection) -> None:
    """v1.0 → v1.1 迁移：accounts 加 member_id 列 + 旧数据归属默认成员"本人"。

    幂等保证：
        - members 表由 DDL 的 CREATE TABLE IF NOT EXISTS 保证存在；
        - 用 PRAGMA table_info 判断 member_id 列是否已存在，存在则跳过 ALTER；
        - 仅当 members 表为空时插入默认成员；
        - 仅更新 member_id IS NULL 的账户。
    注意：SQLite 的 ALTER TABLE ADD COLUMN 不支持加外键约束，故 member_id
    只加普通 INTEGER 列，外键关系由应用层保证。
    """
    # 1) accounts 加 member_id 列（幂等）
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)")]
    if "member_id" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN member_id INTEGER")

    # 2) members 表为空 → 插入默认成员"本人"
    cnt = conn.execute("SELECT COUNT(*) AS c FROM members").fetchone()["c"]
    if cnt == 0:
        now = now_str()
        conn.execute(
            "INSERT INTO members (name, relation, note, created_at, updated_at)"
            " VALUES (?, ?, NULL, ?, ?)",
            ("本人", "本人", now, now),
        )

    # 3) 把所有未归属的旧账户归到默认成员（第一个成员）
    conn.execute(
        """
        UPDATE accounts
           SET member_id = (SELECT id FROM members ORDER BY id LIMIT 1)
         WHERE member_id IS NULL
        """
    )


def migrate_to_v1_2(conn: sqlite3.Connection) -> None:
    """v1.1 → v1.2 迁移：账户类型枚举重构 + available_date 字段。

    幂等保证：
        - available_date 列用 PRAGMA table_info 判断，存在则跳过 ALTER；
        - 枚举映射 UPDATE 本身幂等（bank/alipay/wechat 已不存在时无匹配行）。
    映射：cash 不变；bank/alipay/wechat → cash；stock/fund/credit_card/other 不变。
    无旧数据映射到 wealth——由用户手动改类型。
    """
    # 1) accounts 加 available_date 列（幂等）
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)")]
    if "available_date" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN available_date TEXT")

    # 2) 检测是否存在待迁移的旧类型账户，用于一次性升级提示
    legacy = conn.execute(
        "SELECT COUNT(*) AS c FROM accounts WHERE type IN ('bank','alipay','wechat')"
    ).fetchone()["c"]
    if legacy > 0:
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('v1_2_notice_pending', '1')"
        )

    # 3) 枚举映射：bank/alipay/wechat → cash
    conn.execute(
        "UPDATE accounts SET type='cash' WHERE type IN ('bank','alipay','wechat')"
    )


def migrate_assets_insurance(conn: sqlite3.Connection) -> None:
    """v1.3 资产表扩展：保险子类型与保障信息字段。

    幂等保证：用 PRAGMA table_info 判断列是否已存在，存在则跳过 ALTER。
    新增列：
        insurance_subtype  TEXT   —— 保险子类型：protection(保障型)/savings(储蓄型)
        coverage           REAL   —— 保额（保障型有意义，储蓄型可空）
        annual_premium     REAL   —— 年保费
    口径：保障型保险无现金价值，value 置 0（不计入总资产）；储蓄型保险
    value 表示现金价值，计入总资产。非保险类资产这些列留 NULL。
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(assets)")]
    for col, ctype in [
        ("insurance_subtype", "TEXT"),
        ("coverage", "REAL"),
        ("annual_premium", "REAL"),
        # v2.1：被保险人（关联 members.id，仅保险类有意义）
        ("insured_member_id", "INTEGER"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE assets ADD COLUMN {col} {ctype}")


def init_db() -> None:
    """启动时执行：按第 5 章 DDL 建表，并依次执行 v1.0→v1.1→v1.2 迁移。"""
    conn = get_conn()
    try:
        with conn:
            for ddl in _DDL_STATEMENTS:
                conn.execute(ddl)
            # v1.1 迁移：members 表 + accounts.member_id + 旧数据归"本人"
            migrate_to_v1_1(conn)
            # v1.2 迁移：账户类型重构 + available_date 列
            migrate_to_v1_2(conn)
            # v1.3 迁移：保险子类型与保障信息字段（v2.1 含 insured_member_id）
            migrate_assets_insurance(conn)
    finally:
        conn.close()

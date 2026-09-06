"""备份 / 恢复服务（v2 重构版）。

备份格式：
    - 加密备份（.fabak）：JSON 信封（含盐）+ Fernet 密文（用启动密码加密）；
    - 明文备份（.json）：完整 JSON，导出前弹窗警告未加密。
备份内容：数据库全量业务表（9 张，快照事务内导出保证一致）+ settings + 附件二进制（base64）。
完整性：payload 内置 SHA-256 checksum（tables+attachments 规范化 JSON），恢复前校验，损坏即报错。
恢复流程：自动备份当前数据 → 校验 → 清空各表与附件目录 → 重插（保留原始 id 保外键）→ 还原附件 → 验证行数。

版本兼容：v1 旧备份无 checksum，读取时跳过校验；_VERSION 升至 2。
"""
import base64
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from app import security
from app.database import get_conn, get_data_dir
from app.logging_setup import get_logger
from app.utils import now_str

logger = get_logger(__name__)

# 备份应用标识与版本号（v2：新增 checksum 完整性校验）
_APP_TAG = "family_asset"
_VERSION = 2

# 需要备份的数据表（业务数据）。members 排最前，保证恢复时先插成员再插账户。
_DATA_TABLES = [
    "members", "accounts", "holdings", "assets", "attachments",
    "liabilities", "repayment_history", "asset_snapshots", "chat_history",
]
# 恢复时保留当前密码/锁状态，不覆盖这些 settings 键
_PROTECTED_SETTINGS_KEYS = {
    "password_hash", "password_salt", "login_fail_count", "login_lock_until",
}


def _canonical_json(obj) -> str:
    """稳定序列化（排序键、紧凑分隔符），供 checksum 使用。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dump_tables(conn) -> dict:
    """在调用方开启的事务快照内逐表 SELECT * 导出为 dict（含 settings）。"""
    tables = {}
    for t in _DATA_TABLES:
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        tables[t] = [dict(r) for r in rows]
    tables["settings"] = [
        dict(r) for r in conn.execute("SELECT * FROM settings").fetchall()
    ]
    return tables


def _dump_attachments() -> dict:
    """读取 data/attachments/ 下所有文件，以相对路径为 key、base64 为 value。"""
    att_dir = get_data_dir() / "attachments"
    files = {}
    if att_dir.exists():
        for p in att_dir.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(get_data_dir())).replace("\\", "/")
                files[rel] = base64.b64encode(p.read_bytes()).decode("ascii")
    return files


def _build_payload() -> dict:
    """构造完整备份数据结构（快照事务保证表间一致 + checksum 完整性校验）。"""
    conn = get_conn()
    try:
        # 单事务快照：BEGIN 后只读 dump，避免导出期间写入导致表间不一致
        conn.execute("BEGIN")
        tables = _dump_tables(conn)
        conn.execute("ROLLBACK")
    finally:
        conn.close()

    attachments = _dump_attachments()
    payload = {
        "app": _APP_TAG,
        "version": _VERSION,
        "exported_at": now_str(),
        "tables": tables,
        "attachments": attachments,
    }
    # 完整性校验：对 tables+attachments 规范化 JSON 算 SHA-256
    core = {"tables": tables, "attachments": attachments}
    payload["checksum"] = hashlib.sha256(_canonical_json(core).encode("utf-8")).hexdigest()
    return payload


def _atomic_write_json(target_path: str, data: dict) -> None:
    """原子写：先写临时文件再 os.replace，避免导出中断产生半文件。"""
    tmp = target_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, target_path)


def export_backup(target_path: str, encrypted: bool = True) -> dict:
    """导出备份到指定路径，返回各表记录数统计。

    encrypted=True 写 .fabak（用启动密码加密，推荐）；否则写明文 .json。
    """
    payload = _build_payload()
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if encrypted:
        if not security.is_ready():
            raise RuntimeError("尚未完成密码校验，无法加密备份")
        token_b64 = base64.b64encode(security.encrypt_bytes(payload_bytes)).decode("ascii")
        envelope = {
            "app": _APP_TAG,
            "version": _VERSION,
            "salt": security.get_password_salt_hex(),
            "data": token_b64,
        }
        _atomic_write_json(target_path, envelope)
    else:
        _atomic_write_json(target_path, payload)
    return count_records()


def _read_payload(src_path: str, password: str | None) -> dict:
    """读取并解析备份文件为 payload dict（含 checksum 校验）。

    格式判定：
        - 明文备份：顶层含 "tables" 键（完整 payload）；
        - 加密备份：顶层含 "data" 键（Fernet 信封），需 password 解密。
    先判明文再判密文，避免键名碰撞导致误判。
    """
    with open(src_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("备份文件格式不兼容")

    if "tables" in raw:
        payload = raw
    elif "data" in raw:
        if not password:
            raise ValueError("该备份为加密格式，需要输入密码")
        salt_hex = raw.get("salt") or ""
        salt = bytes.fromhex(salt_hex) if salt_hex else b"\x00" * 16
        try:
            token_bytes = base64.b64decode(raw["data"])
            plain = security.decrypt_with_password(token_bytes, password, salt)
        except Exception:
            raise ValueError("密码错误，无法解密备份文件")
        payload = json.loads(plain.decode("utf-8"))
    else:
        raise ValueError("无法识别的备份文件格式")

    if payload.get("app") != _APP_TAG:
        raise ValueError("备份文件格式不兼容")
    version = payload.get("version")
    if version not in (1, 2):
        raise ValueError("备份版本不受支持")

    # v2 起：校验完整性（v1 旧备份无 checksum，跳过）
    if version == 2:
        core = {
            "tables": payload.get("tables", {}),
            "attachments": payload.get("attachments", {}),
        }
        calc = hashlib.sha256(_canonical_json(core).encode("utf-8")).hexdigest()
        if calc != payload.get("checksum"):
            raise ValueError("备份文件已损坏（校验和不匹配）")
    return payload


def _relative_to_attachments(rel: str) -> Path:
    """把备份里的相对路径（如 attachments/xxx.jpg）转成相对 attachments 的子路径。"""
    parts = Path(rel).parts
    if parts and parts[0] == "attachments":
        return Path(*parts[1:]) if len(parts) > 1 else Path()
    return Path(rel)


def _replace_attachments_dir(staged: Path | None, att_dir: Path) -> None:
    """用 staged 目录整体替换 attachments 目录；staged 为 None 表示清空旧目录。

    步骤：旧目录先改名备份（不直接删）→ staged 改名就位 → 清理旧目录。
    任一步失败都不会让 attachments 停留在"只有一半文件"的状态。
    """
    old_dir = None
    if att_dir.exists():
        old_dir = att_dir.parent / f"attachments.old_{datetime.now():%Y%m%d_%H%M%S}"
        att_dir.rename(old_dir)
    if staged is not None:
        staged.rename(att_dir)
    if old_dir is not None:
        shutil.rmtree(old_dir, ignore_errors=True)


def _auto_backup_before_restore() -> None:
    """恢复前自动备份当前数据（加密格式）到 auto_before_restore 目录。"""
    auto_dir = get_data_dir() / "backups" / "auto_before_restore"
    auto_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = auto_dir / f"auto_{stamp}.fabak"
    try:
        export_backup(str(target), encrypted=True)
    except Exception:
        # 自动备份失败不阻断恢复流程，但必须留下痕迹（否则事后无从追查）
        logger.warning("恢复前的自动备份失败，恢复流程仍继续", exc_info=True)


def import_backup(src_path: str, password: str | None) -> dict:
    """恢复备份：自动备份当前数据 → 校验 → 清空各表与附件 → 重插 → 还原附件 → 验证行数。

    返回统计信息 dict（各表恢复条数；_verified 后缀为恢复后核对行数）。
    """
    payload = _read_payload(src_path, password)
    tables = payload.get("tables", {})
    attachments = payload.get("attachments", {})

    _auto_backup_before_restore()

    conn = get_conn()
    counts: dict[str, int] = {}
    try:
        with conn:
            # 1) 清空数据（按外键依赖顺序，先删子表再删父表）
            conn.execute("DELETE FROM repayment_history")
            conn.execute("DELETE FROM holdings")
            conn.execute("DELETE FROM attachments")
            conn.execute("DELETE FROM liabilities")
            conn.execute("DELETE FROM accounts")
            conn.execute("DELETE FROM members")
            conn.execute("DELETE FROM assets")
            conn.execute("DELETE FROM asset_snapshots")
            conn.execute("DELETE FROM chat_history")

            # 2) 重新插入业务表（保留原始 id 以维持外键关系；列以备份为准，
            #    新 schema 多余列自动留默认/NULL，兼容 v1 旧备份）
            for t in _DATA_TABLES:
                rows = tables.get(t, [])
                for row in rows:
                    cols = list(row.keys())
                    placeholders = ",".join(["?"] * len(cols))
                    conn.execute(
                        f"INSERT INTO {t} ({','.join(cols)}) VALUES ({placeholders})",
                        [row[c] for c in cols],
                    )
                counts[t] = len(rows)

            # 3) 恢复 settings（排除密码/锁状态，保留当前启动密码）
            for row in tables.get("settings", []):
                if row["key"] in _PROTECTED_SETTINGS_KEYS:
                    continue
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (row["key"], row["value"]),
                )

            # 4) 恢复后验证行数（防止静默丢数据）
            for t in _DATA_TABLES:
                c = conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
                counts[f"{t}_verified"] = c
    finally:
        conn.close()

    # 5) 还原附件：先写入临时目录，全部成功后再做目录级替换。
    #    旧实现"先 rmtree 清空 → 再逐个写"，中途若 base64 损坏或磁盘写满，
    #    会留下"库已恢复、附件只有一半"的半截状态，且旧附件已无法复原。
    att_dir = get_data_dir() / "attachments"
    staged = get_data_dir() / "attachments.new"
    if staged.exists():
        shutil.rmtree(staged, ignore_errors=True)

    if attachments:
        staged.mkdir(parents=True, exist_ok=True)
        try:
            for rel, b64 in attachments.items():
                target = staged / _relative_to_attachments(rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(base64.b64decode(b64))
        except Exception:
            # 正式目录尚未被替换，不会造成半截状态
            logger.error("附件还原失败——数据已恢复但附件不完整，"
                         "可用「恢复前自动备份」回退（backups/auto_before_restore）",
                         exc_info=True)
            raise
        _replace_attachments_dir(staged, att_dir)
        counts["attachments_files"] = len(attachments)
    elif att_dir.exists():
        # 备份中不含附件：同样走"改名后再清理"，不直接删
        _replace_attachments_dir(None, att_dir)

    return counts


def count_records() -> dict:
    """统计当前数据库各表记录数（供导出/恢复确认框展示）。"""
    conn = get_conn()
    try:
        result = {}
        for t in _DATA_TABLES + ["settings"]:
            row = conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()
            result[t] = row["c"]
        return result
    finally:
        conn.close()

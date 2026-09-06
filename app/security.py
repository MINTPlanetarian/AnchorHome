"""启动密码与字段加密模块。

设计要点（遵循 PRD 5.1/5.2/7.4）：
- 启动密码用 PBKDF2（加盐，10 万次迭代）派生密钥，settings 表只存 hash + salt；
- Fernet 密钥由派生密钥进一步派生而来，仅存内存，绝不写盘；
- 加密范围：AI API Key 等敏感字段；
- 连续输错 5 次锁定 5 分钟（锁定状态记录在 settings 表）。
"""
import base64
import hashlib
import os
import time

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# PBKDF2 迭代次数（PRD 要求 10 万次）
_PBKDF2_ITERATIONS = 100_000
# 锁定相关配置
_MAX_FAILS = 5
_LOCK_SECONDS = 5 * 60

# 内存中的 Fernet 实例（登录成功后构造，进程内有效，绝不落盘）
_fernet: Fernet | None = None


def _derive_key(password: str, salt: bytes) -> bytes:
    """用 PBKDF2 从密码 + 盐派生 32 字节密钥。"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def _password_hash(derived_key: bytes) -> str:
    """对派生密钥做一次 SHA256，得到用于比对存储的哈希（十六进制）。"""
    return hashlib.sha256(derived_key).hexdigest()


def set_password(plain: str) -> tuple[bytes, str]:
    """设置新密码：生成随机盐 → 派生密钥 → 内存构造 Fernet。

    返回 (salt, password_hash)，由调用方写入 settings 表；
    密钥本身只保留在内存中，绝不落盘。
    注意：调用本函数会替换内存密钥——改密码场景须先解密敏感字段再重新加密。
    """
    global _fernet
    salt = os.urandom(16)
    key = _derive_key(plain, salt)
    _fernet = Fernet(base64.urlsafe_b64encode(key))
    return salt, _password_hash(key)


def verify_password(plain: str, salt_hex: str, expected_hash: str) -> bool:
    """校验输入密码；成功后同样在内存构造 Fernet 实例。"""
    global _fernet
    salt = bytes.fromhex(salt_hex)
    key = _derive_key(plain, salt)
    if _password_hash(key) != expected_hash:
        return False
    _fernet = Fernet(base64.urlsafe_b64encode(key))
    return True


# ---------------------------------------------------------------------------
# 加解密（依赖内存中的 Fernet 实例）
# ---------------------------------------------------------------------------
def is_ready() -> bool:
    """是否已完成密码校验、具备加解密能力。"""
    return _fernet is not None


def encrypt_text(plain: str) -> str:
    """加密文本（如 API Key）。返回 token 字符串；未登录时抛异常。"""
    if _fernet is None:
        raise RuntimeError("密钥尚未初始化，请先完成启动密码校验")
    return _fernet.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    """解密文本。token 无效或密钥不匹配时返回空串（由调用方处理）。"""
    if _fernet is None:
        return ""
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def encrypt_bytes(plain_bytes: bytes) -> bytes:
    """用内存 Fernet 加密二进制数据（用于加密备份）。未登录时抛异常。"""
    if _fernet is None:
        raise RuntimeError("密钥尚未初始化，请先完成启动密码校验")
    return _fernet.encrypt(plain_bytes)


def decrypt_with_password(token: bytes, password: str, salt: bytes) -> bytes:
    """用「指定密码 + 盐」解密字节流（用于恢复加密备份）。密码错误抛 InvalidToken。"""
    key = _derive_key(password, salt)
    f = Fernet(base64.urlsafe_b64encode(key))
    return f.decrypt(token)


def get_password_salt_hex() -> str:
    """读取启动密码盐（十六进制）。用于加密备份文件头。"""
    from app import config

    return config.get_setting("password_salt", "") or ""


# ---------------------------------------------------------------------------
# 锁定机制（连续输错 5 次锁定 5 分钟）
# ---------------------------------------------------------------------------
def _lock_state():
    """读取锁定状态。返回 (fail_count, lock_until_ts)。"""
    from app import config

    # 用 config 的兜底解析：settings 是明文表，脏值不该让登录页崩溃
    fail_count = config.get_setting_int("login_fail_count", 0)
    lock_until = config.get_setting_float("login_lock_until", 0.0)
    return fail_count, lock_until


def is_locked() -> tuple[bool, int]:
    """是否处于锁定状态。返回 (是否锁定, 剩余秒数)。"""
    _, lock_until = _lock_state()
    remain = int(lock_until - time.time())
    if remain > 0:
        return True, remain
    return False, 0


def record_fail() -> int:
    """记录一次失败，返回剩余可尝试次数；达到上限则写入锁定时间。"""
    from app import config

    fail_count, _ = _lock_state()
    fail_count += 1
    config.set_setting("login_fail_count", str(fail_count))
    if fail_count >= _MAX_FAILS:
        config.set_setting("login_lock_until", str(time.time() + _LOCK_SECONDS))
        return 0
    return _MAX_FAILS - fail_count


def reset_fail() -> None:
    """登录成功后清零失败计数与锁定时间。"""
    from app import config

    config.set_setting("login_fail_count", "0")
    config.set_setting("login_lock_until", "0")

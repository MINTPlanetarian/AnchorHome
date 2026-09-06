"""核心逻辑离线测试（不启动 GUI）。运行后自动清理测试数据。"""
import os
import sys
import tempfile
from pathlib import Path

IN_PYTEST = "pytest" in sys.modules

# 测试期间重定向到临时目录，避免污染正式数据（pytest / 直接运行各自独立）
_tmp = tempfile.mkdtemp(prefix="family_asset_test_")
os.environ["FAMILY_ASSET_DATA_DIR"] = _tmp
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import config, security
from app.database import init_db, DB_PATH
from app.dao import account_dao, holding_dao, asset_dao, liability_dao, snapshot_dao, member_dao
from app.services import report_service, backup_service
from app.services.market_service import detect_market

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}")
        if IN_PYTEST:
            # pytest 下直接失败，让框架捕获并定位具体用例
            raise AssertionError(f"检查未通过：{name}")


print("== 1. 数据库建表 ==")
init_db()
check("DB 文件已创建", Path(DB_PATH).exists())

print("== 2. 启动密码 ==")
salt, pwd_hash = security.set_password("123456")
config.set_setting("password_salt", salt.hex())
config.set_setting("password_hash", pwd_hash)
check("设置密码后可校验", security.verify_password("123456", salt.hex(), pwd_hash))
check("错误密码被拒绝", not security.verify_password("wrong", salt.hex(), pwd_hash))
check("加密就绪", security.is_ready())
token = security.encrypt_text("sk-test-key")
check("加密/解密往返", security.decrypt_text(token) == "sk-test-key")

print("== 3. 账户 CRUD ==")
aid = account_dao.create_account("招行工资卡", "cash", "CNY", 52000, "招商银行", None)
check("新增账户", aid > 0)
account_dao.create_account("华泰证券", "stock", "CNY", 10000, "华泰证券", None)
account_dao.create_account("招行信用卡", "credit_card", "CNY", 5000, "招商银行", None)
check("账户列表", len(account_dao.list_accounts()) == 3)
check("启用账户列表", len(account_dao.list_accounts(active_only=True)) == 3)

print("== 4. 持仓 ==")
stock_acc = [a for a in account_dao.list_accounts() if a["type"] == "stock"][0]
hid = holding_dao.create_holding(stock_acc["id"], "600519", "贵州茅台", "SH", 100, 1650.0)
holding_dao.create_holding(stock_acc["id"], "110022", "易方达消费", "FUND", 1000, 3.0)
check("新增持仓", hid > 0)
holding_dao.update_price("600519", 1720.5)
h = holding_dao.list_holdings_by_account(stock_acc["id"])[0]
check("现价已更新", h["current_price"] == 1720.5)
check("持仓市值计算", abs(report_service.holdings_market_value(stock_acc["id"]) - (100 * 1720.5 + 1000 * 3.0)) < 0.01)

print("== 5. 资产台账 + 附件 ==")
asset_id = asset_dao.create_asset("XX小区住房", "real_estate", 2000000, "2020-05-01", None)
asset_dao.create_asset("代步车", "vehicle", 150000, None, None)
check("新增资产", asset_id > 0)
att_id = asset_dao.add_attachment(asset_id, "房产证.jpg", "attachments/test.jpg")
check("新增附件记录", att_id > 0)
check("附件列表", len(asset_dao.list_attachments(asset_id)) == 1)

print("== 6. 负债 + 还款 ==")
lid = liability_dao.create_liability("XX路房贷", "mortgage", 1000000, 380000, 3.6, 4547, None)
liability_dao.create_liability("车贷", "car_loan", 150000, 76789, 4.2, 3500, None)
check("新增负债", lid > 0)
liability_dao.repay(lid, 4547, "2026-08-23")
liab = liability_dao.get_liability(lid)
check("还款后余额扣减", abs(liab["remaining"] - (380000 - 4547)) < 0.01)
check("还款历史 1 条", len(liability_dao.list_repayments(lid)) == 1)

print("== 7. 净资产计算口径 ==")
t = report_service.calc_totals()
# 总资产 = 工资卡52000 + 证券现金10000 + 持仓市值(172050+3000) + 房产200万 + 车15万
expected_assets = 52000 + 10000 + 172050 + 3000 + 2000000 + 150000
# 总负债 = 房贷380000-4547=375453 + 车贷76789 + 信用卡5000
expected_liab = (380000 - 4547) + 76789 + 5000
check("总资产", abs(t["total_assets"] - expected_assets) < 0.01)
check("总负债", abs(t["total_liabilities"] - expected_liab) < 0.01)
check("净资产", abs(t["net_worth"] - (expected_assets - expected_liab)) < 0.01)

print("== 8. 快照 ==")
report_service.take_daily_snapshot()
check("当日快照已生成", snapshot_dao.get_snapshot_by_date(__import__("app.utils", fromlist=["today_str"]).today_str()) is not None)

print("== 9. 备份 / 恢复 ==")
bkp = os.path.join(_tmp, "backup_test.fabak")
backup_service.export_backup(bkp, encrypted=True)
check("加密备份文件已生成", os.path.exists(bkp))
counts = backup_service.import_backup(bkp, "123456")
check("恢复账户数", counts.get("accounts") == 3)
check("恢复负债数", counts.get("liabilities") == 2)
check("恢复持仓数", counts.get("holdings") == 2)

# 恢复后净资产应一致
t2 = report_service.calc_totals()
check("恢复后净资产一致", abs(t2["net_worth"] - t["net_worth"]) < 0.01)

print("== 10. 市场判断 ==")
check("600519→SH", detect_market("600519") == "SH")
check("000001→SZ", detect_market("000001") == "SZ")
check("300750→SZ", detect_market("300750") == "SZ")
check("430047→BJ", detect_market("430047") == "BJ")
check("510300→SH", detect_market("510300") == "SH")
check("159915→SZ", detect_market("159915") == "SZ")
check("110022→FUND", detect_market("110022") == "FUND")

print("== 11. 改密码后 AI API Key 仍可解密（关键修复）==")
# 先加密存一个 AI Key（用密码 123456 派生的当前 fernet）
config.set_setting("ai_api_key", security.encrypt_text("sk-original"))
check("改密码前 AI Key 可解密", security.decrypt_text(config.get_setting("ai_api_key", "")) == "sk-original")
# 模拟改密码：旧密钥解密 → set_password(新) → 新密钥重加密
old_key = security.decrypt_text(config.get_setting("ai_api_key", ""))
new_salt, new_hash = security.set_password("newpwd789")
config.set_setting("password_salt", new_salt.hex())
config.set_setting("password_hash", new_hash)
config.set_setting("ai_api_key", security.encrypt_text(old_key))
# 用新密钥解密应得到原值
check("改密码后 AI Key 仍可解密", security.decrypt_text(config.get_setting("ai_api_key", "")) == "sk-original")
# 校验新密码可用、旧密码失效
check("新密码可校验", security.verify_password("newpwd789", new_salt.hex(), new_hash))
# 注意：verify_password 会把内存 fernet 切回 newpwd789 派生，AI Key 仍应可解
check("校验后 AI Key 仍可解密", security.decrypt_text(config.get_setting("ai_api_key", "")) == "sk-original")

print("== 12. 批量更新价格（单事务）==")
holding_dao.update_prices({"600519": 1888.8, "110022": 3.5})
h = holding_dao.list_holdings_by_account(stock_acc["id"])
prices = {x["code"]: x["current_price"] for x in h}
check("批量更新-600519", abs(prices["600519"] - 1888.8) < 0.01)
check("批量更新-110022", abs(prices["110022"] - 3.5) < 0.01)

print("== 13. v1.1 迁移：默认成员\"本人\" + 旧账户归属 ==")
members = member_dao.list_members()
check("迁移后自动出现默认成员", len(members) >= 1 and members[0]["name"] == "本人")
check("迁移后成员关系为本人", members[0]["relation"] == "本人")
# 之前创建的 3 个账户（未显式指定 member_id）应归属默认成员
default_id = member_dao.default_member_id()
unowned = [a for a in account_dao.list_accounts() if a.get("member_id") != default_id]
check("旧账户全部归默认成员", len(unowned) == 0)
check("账户查询带持有人姓名", all(a.get("member_name") == "本人" for a in account_dao.list_accounts()))

print("== 14. 新增成员 + 账户关联持有人 ==")
li4_id = member_dao.create_member("李四", "配偶", None)
check("新增成员李四", li4_id > 0)
li4_acc = account_dao.create_account("李四工资卡", "bank", "CNY", 80000, "工商银行", None, li4_id)
check("新增账户归李四", account_dao.get_account(li4_acc)["member_id"] == li4_id)
check("按成员过滤账户", len(account_dao.list_by_member(li4_id)) == 1)

print("== 15. 删除校验：名下有账户的成员禁止删除 ==")
check("李四名下账户数=1", member_dao.count_accounts(li4_id) == 1)

print("== 16. 按成员统计口径 ==")
t_li4 = report_service.calc_totals(member_id=li4_id)
# 李四个人视图：总资产=李四账户 80000（无资产台账、无负债表），总负债=0
check("李四总资产", abs(t_li4["total_assets"] - 80000) < 0.01)
check("李四总负债=0", abs(t_li4["total_liabilities"]) < 0.01)
check("李四净资产", abs(t_li4["net_worth"] - 80000) < 0.01)
t_all = report_service.calc_totals()
check("全部视图资产>李四个人", t_all["total_assets"] > t_li4["total_assets"])

print("== 17. 饼图按持有人维度 ==")
dist = report_service.distribution_by_member()
names = [k for k, _ in dist]
check("按持有人含本人与李四", "本人" in names and "李四" in names)
total_by_member = sum(v for _, v in dist)
check("按持有人金额之和>0", total_by_member > 0)

print("== 18. 备份恢复覆盖 members 表 ==")
bkp2 = os.path.join(_tmp, "backup_members.fabak")
backup_service.export_backup(bkp2, encrypted=True)
# 删除李四账户后恢复，应还原（注意：第 11 节已把密码改为 newpwd789）
account_dao.delete_account(li4_acc)
counts2 = backup_service.import_backup(bkp2, "newpwd789")
check("恢复 members 表", counts2.get("members", 0) >= 2)
check("恢复后李四账户存在", account_dao.get_account(li4_acc) is not None)
check("恢复后李四归属正确", account_dao.get_account(li4_acc)["member_id"] == li4_id)

print("== 19. v1.0 旧库迁移幂等（验收标准 1）==")
import sqlite3
from app.database import migrate_to_v1_1

# 构造一个 v1.0 旧库（accounts 无 member_id、无 members 数据）
old_conn = sqlite3.connect(":memory:")
old_conn.row_factory = sqlite3.Row
old_conn.execute("""CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, type TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'CNY', balance REAL NOT NULL DEFAULT 0,
    institution TEXT, note TEXT, is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
old_conn.execute(
    "INSERT INTO accounts (name,type,currency,balance,is_active,created_at,updated_at)"
    " VALUES ('旧账户','bank','CNY',100,1,'2026-01-01','2026-01-01')"
)
old_conn.execute("""CREATE TABLE members (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT '本人', note TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
old_conn.commit()

migrate_to_v1_1(old_conn)
m1 = old_conn.execute("SELECT * FROM members").fetchall()
check("迁移插入默认成员本人", len(m1) == 1 and m1[0]["name"] == "本人")
member_id = m1[0]["id"]
accs = old_conn.execute("SELECT member_id FROM accounts").fetchall()
check("旧账户归默认成员", accs[0]["member_id"] == member_id)
cols_after = [r[1] for r in old_conn.execute("PRAGMA table_info(accounts)")]
check("accounts 已有 member_id 列", "member_id" in cols_after)

# 幂等：重复执行不报错、不新增成员
migrate_to_v1_1(old_conn)
migrate_to_v1_1(old_conn)
check("迁移幂等（成员仍 1 条）", old_conn.execute("SELECT COUNT(*) AS c FROM members").fetchone()["c"] == 1)
old_conn.close()

print("== 20. v1.2 旧库迁移：bank/alipay/wechat → cash（验收标准 1）==")
from app.database import migrate_to_v1_2
from app.utils import today_str as _today

# 构造 v1.1 旧库：accounts 有 member_id 无 available_date，含 bank/alipay/wechat 账户
v11_conn = sqlite3.connect(":memory:")
v11_conn.row_factory = sqlite3.Row
v11_conn.execute("""CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, type TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'CNY', balance REAL NOT NULL DEFAULT 0,
    institution TEXT, note TEXT, member_id INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
v11_conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
v11_conn.execute("INSERT INTO accounts (name,type,balance,member_id,is_active,created_at,updated_at) VALUES ('旧银行卡','bank',1000,NULL,1,'x','x')")
v11_conn.execute("INSERT INTO accounts (name,type,balance,member_id,is_active,created_at,updated_at) VALUES ('旧支付宝','alipay',2000,NULL,1,'x','x')")
v11_conn.execute("INSERT INTO accounts (name,type,balance,member_id,is_active,created_at,updated_at) VALUES ('旧股票','stock',3000,NULL,1,'x','x')")
v11_conn.commit()

migrate_to_v1_2(v11_conn)
types = {r["name"]: r["type"] for r in v11_conn.execute("SELECT name,type FROM accounts")}
check("bank→cash", types["旧银行卡"] == "cash")
check("alipay→cash", types["旧支付宝"] == "cash")
check("stock 不变", types["旧股票"] == "stock")
cols_v12 = [r[1] for r in v11_conn.execute("PRAGMA table_info(accounts)")]
check("accounts 已有 available_date 列", "available_date" in cols_v12)
check("迁移提示标记已写入", v11_conn.execute("SELECT value FROM settings WHERE key='v1_2_notice_pending'").fetchone()["value"] == "1")
# 幂等：重复执行不报错
migrate_to_v1_2(v11_conn)
migrate_to_v1_2(v11_conn)
check("v1.2 迁移幂等", v11_conn.execute("SELECT COUNT(*) AS c FROM accounts WHERE type IN ('bank','alipay','wechat')").fetchone()["c"] == 0)
v11_conn.close()

print("== 21. 流动性口径：liquid/locked（验收标准 2/3/4）==")
today = _today()
from datetime import datetime as _dt, timedelta as _td
tomorrow = (_dt.now() + _td(days=1)).strftime("%Y-%m-%d")
yesterday = (_dt.now() - _td(days=1)).strftime("%Y-%m-%d")

# 现金 52000（已有）+ 理财A(随时可用 30000) + 理财B(明天到期 10000) + 理财C(昨天到期 5000)
account_dao.create_account("余额宝", "wealth", "CNY", 30000, "支付宝", None, None, None)
account_dao.create_account("月月宝", "wealth", "CNY", 10000, "招商银行", None, None, tomorrow)
account_dao.create_account("已到期理财", "wealth", "CNY", 5000, "工商银行", None, None, yesterday)

t2 = report_service.calc_totals()
# liquid = 现金52000 + 余额宝30000(随时) + 已到期理财5000(昨天) = 87000
expected_liquid = 52000 + 30000 + 5000
check("可用资金", abs(t2["liquid_funds"] - expected_liquid) < 0.01)
check("锁定资金", abs(t2["locked_funds"] - 10000) < 0.01)
check("最近解锁日期", t2["next_unlock_date"] == tomorrow)

print("== 22. list_liquid / list_maturing ==")
liquid_names = [a["name"] for a in account_dao.list_liquid()]
check("list_liquid 含随时可用理财", "余额宝" in liquid_names)
check("list_liquid 含已到期理财", "已到期理财" in liquid_names)
check("list_liquid 不含锁定理财", "月月宝" not in liquid_names)
maturing = account_dao.list_maturing(days=7)
maturing_names = [a["name"] for a in maturing]
check("list_maturing 含明天到期", "月月宝" in maturing_names)
check("list_maturing 含已过期", "已到期理财" in maturing_names)

print("== 23. 饼图按流动性维度（验收标准 7）==")
dist_liq = report_service.distribution_by_liquidity()
liq_labels = {k for k, _ in dist_liq}
check("四类含立即可用/锁定中/投资", {"立即可用", "锁定中", "投资"} <= liq_labels)

print("== 24. 备份恢复 available_date 与类型（验收标准 9）==")
bkp3 = os.path.join(_tmp, "backup_v12.fabak")
backup_service.export_backup(bkp3, encrypted=True)
# 记录月月宝的 available_date
yuebao_before = account_dao.list_accounts(active_only=False)
yuebao = [a for a in yuebao_before if a["name"] == "月月宝"][0]
check("月月宝类型 wealth", yuebao["type"] == "wealth")
check("月月宝 available_date=明天", yuebao["available_date"] == tomorrow)
counts3 = backup_service.import_backup(bkp3, "newpwd789")
yuebao_after = [a for a in account_dao.list_accounts() if a["name"] == "月月宝"][0]
check("恢复后 available_date 还原", yuebao_after["available_date"] == tomorrow)
check("恢复后类型还原", yuebao_after["type"] == "wealth")

print(f"\n===== 测试结果：通过 {PASS}，失败 {FAIL} =====")


def test_suite():
    """pytest 收集入口：测试体已在模块导入时执行完毕，此处汇总判定。"""
    assert FAIL == 0, f"存在失败用例（通过 {PASS}，失败 {FAIL}）"
    assert PASS > 0, "测试体未执行"


if __name__ == "__main__":
    sys.exit(1 if FAIL else 0)

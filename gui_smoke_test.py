"""GUI 冒烟测试（v2.0）：offscreen 模式下构建主窗口与所有页面，验证无异常。"""
import os
import sys
import tempfile

IN_PYTEST = "pytest" in sys.modules

# 测试期间重定向到临时目录 + offscreen（pytest / 直接运行各自独立）
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_tmp = tempfile.mkdtemp(prefix="family_asset_gui_")
os.environ["FAMILY_ASSET_DATA_DIR"] = _tmp

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import config, security  # noqa: E402
from app.database import init_db  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.login_dialog import LoginDialog  # noqa: E402
from app.ui.settings_page import SettingsPage  # noqa: E402
from app.services import report_service  # noqa: E402

init_db()
salt, pwd_hash = security.set_password("123456")
config.set_setting("password_salt", salt.hex())
config.set_setting("password_hash", pwd_hash)

from app.dao import account_dao, holding_dao, asset_dao, liability_dao  # noqa: E402
account_dao.create_account("招行工资卡", "cash", "CNY", 52000, "招商银行", None)
sa = account_dao.create_account("华泰证券", "stock", "CNY", 10000, "华泰证券", None)
account_dao.create_account("招行信用卡", "credit_card", "CNY", 5000, None, None)
account_dao.create_account("余额宝", "wealth", "CNY", 30000, "支付宝", None)
account_dao.create_account("公积金", "provident_fund", "CNY", 80000, "公积金中心", None)
holding_dao.create_holding(sa, "600519", "贵州茅台", "SH", 100, 1650.0)
asset_dao.create_asset("XX小区住房", "real_estate", 2000000, "2020-05-01", None)
asset_dao.create_asset("重疾险", "insurance", 0.0, "2021-11-05", None,
                       insurance_subtype="protection", coverage=500000, annual_premium=8000)
asset_dao.create_asset("年金险", "insurance", 120000, "2023-01-20", None,
                       insurance_subtype="savings", coverage=200000, annual_premium=20000)
liability_dao.create_liability("XX路房贷", "mortgage", 1000000, 380000, 3.6, 4547, None)
report_service.take_daily_snapshot()

app = QApplication.instance() or QApplication(sys.argv)

print("== 构建主窗口 ==")
win = MainWindow()
print("  主窗口标题:", win.windowTitle())
print("  页面数量:", len(win._pages))
for key, page in win._pages.items():
    print(f"    页面 {key}: {type(page).__name__}")

print("== 刷新所有页面 ==")
win.refresh_all()
print("  刷新完成")

print("== 总览页统计 ==")
t = report_service.calc_totals()
print("  可用资金:", t["liquid_funds"], "锁定资金:", t["locked_funds"])
print("  总资产(含公积金,不含保障型保险):", t["total_assets"])

print("== 账户对话框（含可用日期控件）==")
from app.ui.accounts_page import AccountDialog
adlg = AccountDialog()
print("  账户对话框已构建（可用日期控件:", adlg.avail_date_edit is not None, ")")

print("== 设置页 ==")
sp = SettingsPage()
print("  设置页已构建（备份信息:", sp.backup_info.text() or "—", ")")

print("== 登录对话框 ==")
ld = LoginDialog(mode="login")
print("  登录对话框已构建, 尺寸:", ld.width(), "x", ld.height())

print("== 页面切换 ==")
for key in ("overview", "accounts", "assets", "liabilities", "reports", "ai", "settings"):
    win.stack.setCurrentWidget(win._pages[key])
print("  全部页面切换正常")

print("\n===== GUI 冒烟测试通过 =====")


def test_suite():
    """pytest 收集入口：主窗口与所有页面已在模块导入时构建并刷新，无异常即通过。"""
    assert True

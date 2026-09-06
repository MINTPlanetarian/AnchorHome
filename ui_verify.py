"""v2.0 验收渲染脚本：offscreen 构建各页面并截图（供视觉核对与 v1.3 缩放矩阵验证）。"""
import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
_tmp = tempfile.mkdtemp(prefix="v2_preview_")
os.environ["FAMILY_ASSET_DATA_DIR"] = _tmp
os.makedirs("_preview", exist_ok=True)

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QApplication

from app import config, security
from app.database import init_db
from app.dao import account_dao, holding_dao, asset_dao, liability_dao

init_db()
salt, pwd_hash = security.set_password("123456")
config.set_setting("password_salt", salt.hex())
config.set_setting("password_hash", pwd_hash)

# 造数据
account_dao.create_account("招行工资卡", "cash", "CNY", 52000, "招商银行", None, available_date=None)
account_dao.create_account("余额宝", "wealth", "CNY", 30000, "支付宝", None, available_date=None)
account_dao.create_account("定期理财", "wealth", "CNY", 80000, "招商银行", None, available_date="2026-08-30")
account_dao.create_account("公积金", "provident_fund", "CNY", 96000, "公积金中心", None, available_date=None)
sa = account_dao.create_account("华泰证券", "stock", "CNY", 15000, "华泰证券", None, available_date=None)
account_dao.create_account("招行信用卡", "credit_card", "CNY", 5000, None, None, available_date=None)
holding_dao.create_holding(sa, "600519", "贵州茅台", "SH", 100, 1650.0)
holding_dao.create_holding(sa, "000858", "五粮液", "SZ", 200, 120.0)
asset_dao.create_asset("滨江花园住房", "real_estate", 2350000, "2019-06-12", "自住房 · 89㎡")
asset_dao.create_asset("家用轿车", "vehicle", 168000, "2022-03-08", "2022 款 · 日常代步")
asset_dao.create_asset("年金保险", "insurance", 120000, "2023-01-20", "xx人寿 · 60 岁起领",
                       insurance_subtype="savings", coverage=200000, annual_premium=20000)
asset_dao.create_asset("重大疾病险", "insurance", 0.0, "2021-11-05", "本人 · 保障至终身",
                       insurance_subtype="protection", coverage=500000, annual_premium=8000)
asset_dao.create_asset("投资金条", "precious_metal", 58000, "2024-02-14", "100g · 银行保管箱")
liability_dao.create_liability("XX路房贷", "mortgage", 1000000, 380000, 3.6, 4547, "首套")
liability_dao.create_liability("车贷", "car_loan", 150000, 92000, 4.8, 3200, None)

from app.ui.main_window import MainWindow
from app.ui.login_dialog import LoginDialog
from app.services import report_service

report_service.take_daily_snapshot()
for i in range(6):
    report_service.take_daily_snapshot()

app = QApplication(sys.argv)

# ---- 登录页 ----
ld = LoginDialog(mode="login")
ld.show()
app.processEvents()
ld.grab().save("_preview/01_login.png")
ld.close()

# ---- 主窗口各页 ----
win = MainWindow()
win.resize(1280, 800)
win.show()
app.processEvents()

def snap(key, name, w=None, h=None):
    win.stack.setCurrentWidget(win._pages[key])
    if w and h:
        win.resize(w, h)
    app.processEvents()
    win.grab().save(f"_preview/{name}.png")
    print(f"saved {name}")

snap("overview", "02_overview_1280")
snap("accounts", "03_accounts_1280")
snap("assets", "04_assets_1280")
snap("liabilities", "05_liabilities_1280")
snap("reports", "06_reports_1280")
snap("ai", "07_ai_1280")
snap("settings", "08_settings_1280")
snap("members", "09_members_1280")

# v1.3 缩放矩阵：最小尺寸下操作列应完整
snap("assets", "10_assets_1100_min", 1100, 700)
snap("accounts", "11_accounts_1100_min", 1100, 700)

print("ALL PREVIEWS SAVED to _preview/")

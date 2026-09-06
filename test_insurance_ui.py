"""v1.4 保险口径 UI 全链路回归测试（v2.0 组件适配版，offscreen 运行）。

覆盖：
  T1  类型切换触发保险区块显隐/标签刷新（P0-2）
  T2  保障型 Radio Pill → 现金价值禁用并清零
  T3  保存链路透传 DAO：result_data 保险三字段 → 落库（P0-1）
  T4  DAO 写路径守护：直接传大 value 的保障型也被强制 0（P1-2）
  T5  读路径守护：calc_totals / 资产大类 / 流动性分布排除保障型
  T6  AI execute_action：更新保险资产保留保险字段 + 保障型强制 0（P1-1）
  T7  编辑旧保险（无子类型）：Pills 均未选、不清零原估值（P1-3）

运行：QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe test_insurance_ui.py
"""
import os
import sys
import tempfile

IN_PYTEST = "pytest" in sys.modules

# 测试期间重定向到临时目录 + offscreen（pytest / 直接运行各自独立）
_tmp = tempfile.mkdtemp()
os.environ["FAMILY_ASSET_DATA_DIR"] = _tmp
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

import app.database as db  # noqa: E402
from app.dao import asset_dao  # noqa: E402
from app.services import report_service, ai_service  # noqa: E402
from app.ui.assets_page import AssetDialog  # noqa: E402

db.init_db()
_passed = 0


def check(name: str, cond: bool):
    global _passed
    if cond:
        _passed += 1
        print(f"[PASS] {name}")
    else:
        print(f"[FAIL] {name}")
        if IN_PYTEST:
            raise AssertionError(f"检查未通过：{name}")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# T1 类型切换触发保险区块显隐 / 标签刷新（P0-2）
# ---------------------------------------------------------------------------
dlg = AssetDialog()
dlg.type_combo.setCurrentIndex(dlg.type_combo.findData("real_estate"))
check("T1 非保险时保险区块隐藏", dlg.ins_field.isHidden() is True)
check("T1 非保险时标签=当前估值", dlg.value_label.text() == "当前估值")

dlg.type_combo.setCurrentIndex(dlg.type_combo.findData("insurance"))
check("T1 切到保险时保险区块显示", dlg.ins_field.isHidden() is False)
check("T1 切到保险时标签=现金价值", dlg.value_label.text() == "现金价值")

# ---------------------------------------------------------------------------
# T2 保障型禁用并清零现金价值（用 click 模拟真实用户点击）
# ---------------------------------------------------------------------------
dlg.pill_protection.click()
check("T2 保障型现金价值禁用", dlg.value_spin.isEnabled() is False)
check("T2 保障型现金价值=0", dlg.value_spin.value() == 0.0)
check("T2 保障型提示文案显示", dlg.value_hint.isHidden() is False)

dlg.pill_savings.click()
check("T2 储蓄型现金价值可用", dlg.value_spin.isEnabled() is True)

# ---------------------------------------------------------------------------
# T3 保存链路透传 DAO（P0-1）
# ---------------------------------------------------------------------------
dlg.pill_protection.click()
dlg.name_edit.setText("重疾险")
dlg.coverage_spin.setValue(500000)
dlg.premium_spin.setValue(8000)
dlg._on_save()
rd = dlg.result_data
check("T3 result_data 含保障型子类型", rd["insurance_subtype"] == "protection")
check("T3 result_data 含保额", rd["coverage"] == 500000)
check("T3 result_data 含年保费", rd["annual_premium"] == 8000)

aid = asset_dao.create_asset(
    rd["name"], rd["type"], rd["value"], rd["purchase_date"], rd["note"],
    rd["insurance_subtype"], rd["coverage"], rd["annual_premium"],
)
row = asset_dao.get_asset(aid)
check("T3 DB 写入子类型", row["insurance_subtype"] == "protection")
check("T3 DB 写入保额", row["coverage"] == 500000)
check("T3 DB 写入年保费", row["annual_premium"] == 8000)
check("T3 保障型 value=0", row["value"] == 0.0)

# ---------------------------------------------------------------------------
# T4 DAO 写路径守护（P1-2）
# ---------------------------------------------------------------------------
aid2 = asset_dao.create_asset(
    "重疾险X", "insurance", 999999,
    insurance_subtype="protection", coverage=100000, annual_premium=5000,
)
check("T4 DAO 强制保障型 value=0", asset_dao.get_asset(aid2)["value"] == 0.0)

# ---------------------------------------------------------------------------
# T5 读路径守护（P1-2）：脏数据 value 非 0 也在统计中排除
# ---------------------------------------------------------------------------
conn = db.get_conn()
conn.execute("UPDATE assets SET value=500000 WHERE id=?", (aid2,))
conn.commit()
conn.close()
check("T5 calc_totals 排除保障型(500000 不计入)", report_service.calc_totals()["total_assets"] == 0.0)

aid3 = asset_dao.create_asset(
    "年金险", "insurance", 120000,
    insurance_subtype="savings", coverage=200000, annual_premium=20000,
)
aid4 = asset_dao.create_asset("房产", "real_estate", 3000000)
check("T5 储蓄型现金价值+房产计入",
      report_service.calc_totals()["total_assets"] == 3120000.0)
cls_dist = dict(report_service.distribution_by_asset_class())
check("T5 资产大类含保险(储蓄型 120000)", cls_dist.get("保险") == 120000)
liq_dist = dict(report_service.distribution_by_liquidity())
check("T5 流动性其他=3120000(保障型被排除)", liq_dist.get("其他") == 3120000.0)

# ---------------------------------------------------------------------------
# T6 AI execute_action（P1-1）
# ---------------------------------------------------------------------------
ai_service.execute_action({"op": "update_asset_value", "id": aid3, "value": 150000, "reason": "测试"})
r = asset_dao.get_asset(aid3)
check("T6 execute_action 保留子类型", r["insurance_subtype"] == "savings")
check("T6 execute_action 保留保额", r["coverage"] == 200000)
check("T6 execute_action 保留年保费", r["annual_premium"] == 20000)
check("T6 execute_action 更新现金价值", r["value"] == 150000)

msg = ai_service.execute_action({"op": "update_asset_value", "id": aid2, "value": 888888, "reason": "测试"})
r2 = asset_dao.get_asset(aid2)
check("T6 保障型被 AI 改值仍强制 0", r2["value"] == 0.0)
check("T6 反馈显示实际生效值 0.00", "¥0.00" in msg)

# ---------------------------------------------------------------------------
# T7 编辑旧保险（无子类型）不清零（P1-3）
# ---------------------------------------------------------------------------
old = {
    "id": 999, "name": "老保险", "type": "insurance", "value": 50000,
    "purchase_date": None, "note": None, "insurance_subtype": None,
    "coverage": None, "annual_premium": None,
}
dlg2 = AssetDialog(old)
check("T7 旧保险保障型 pill 未选中", dlg2.pill_protection.isChecked() is False)
check("T7 旧保险储蓄型 pill 未选中", dlg2.pill_savings.isChecked() is False)
check("T7 旧保险现金价值未被清零", dlg2.value_spin.value() == 50000)
check("T7 旧保险现金价值可用", dlg2.value_spin.isEnabled() is True)

print(f"\nALL {_passed} CHECKS PASSED")


def test_suite():
    """pytest 收集入口：保险 UI 用例已在模块导入时执行完毕，此处汇总判定。"""
    assert _passed > 0, "保险 UI 用例未执行"


if __name__ == "__main__":
    sys.exit(0 if _passed else 1)

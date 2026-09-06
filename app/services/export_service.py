"""结构化数据导出（供 AI Agent 处理 / 分析 / 理解）。

与备份的区别：
    - 备份（backup_service）：逐表原样 dump，用于"恢复"，字段是数据库原始列名；
    - 本模块：**语义化、去重、带持有人上下文**的中文键 JSON，便于 AI 直接消费分析。
覆盖：成员 / 账户（含持有人、可用性、状态）/ 持仓（含盈亏）/ 资产（含被保险人、保险信息）/
    负债（含还款进度）+ 顶层汇总指标（总资产/总负债/净资产/可用资金/锁定资金）。
"""
from __future__ import annotations

import json
from datetime import datetime

from app import constants
from app.constants import type_label
from app.dao import (
    account_dao, asset_dao, holding_dao, liability_dao, member_dao,
)
from app.services import report_service

APP_DISPLAY_NAME = "安航家资"
EXPORT_VERSION = 1


def _liquidity_label(acc: dict) -> str:
    """账户可用性中文标签（与账户页表格口径一致）。"""
    if acc["type"] != "wealth":
        return "不适用"
    avail = acc.get("available_date")
    today = datetime.now().strftime("%Y-%m-%d")
    if not avail:
        return "随时可用"
    if avail <= today:
        return "已到期可用"
    return f"{avail} 可用"


def _holding_row(h: dict) -> dict:
    """持仓 → 中文键（现价为空时市值用成本价兜底，与软件口径一致）。"""
    qty = h.get("quantity") or 0
    cost = h.get("cost_price") or 0
    price = h.get("current_price")
    price_null = price is None
    if price_null:
        price = cost  # 兜底：现价缺失用成本价
    market_value = qty * price
    pnl = (price - cost) * qty
    pnl_pct = (price - cost) / cost * 100 if cost else 0.0
    return {
        "代码": h["code"],
        "名称": h["name"],
        "市场": h.get("market") or "未知",
        "所属账户": h.get("account_name") or "—",
        "数量": qty,
        "成本价": round(cost, 4),
        "现价": None if price_null else round(price, 4),
        "市值(现价缺失时按成本价兜底)": round(market_value, 2),
        "盈亏金额": round(pnl, 2),
        "盈亏百分比": round(pnl_pct, 2),
    }


def _asset_row(a: dict) -> dict:
    """资产 → 中文键（含被保险人/保险子类型）。"""
    row = {
        "名称": a["name"],
        "类型": type_label(constants.ASSET_TYPES, a["type"]),
        "估值/现金价值": a["value"],
        "购置日期": a.get("purchase_date") or "—",
        "备注": a.get("note") or "—",
    }
    if a["type"] == "insurance":
        row["保险子类型"] = type_label(
            constants.INSURANCE_SUBTYPES, a.get("insurance_subtype")) if a.get("insurance_subtype") else "未指定"
        row["被保险人"] = a.get("insured_name") or "未指定"
        row["保额"] = a.get("coverage")
        row["年保费"] = a.get("annual_premium")
        if a.get("insurance_subtype") == "protection":
            row["口径说明"] = "保障型保险：现金价值恒为 0，不计入总资产，仅作保障记录"
    return row


def _liability_row(l: dict) -> dict:
    """负债 → 中文键（含还款进度）。"""
    total = l.get("total_amount") or 0
    remaining = l.get("remaining") or 0
    repaid_pct = (total - remaining) / total * 100 if total else 0.0
    return {
        "名称": l["name"],
        "类型": type_label(constants.LIABILITY_TYPES, l["type"]),
        "总金额": total,
        "剩余金额": remaining,
        "已还比例%": round(max(0.0, repaid_pct), 2),
        "年利率%": l.get("interest_rate") or 0,
        "月还款额": l.get("monthly_payment") or 0,
        "备注": l.get("note") or "—",
    }


def build_structured_data() -> dict:
    """构造语义化、结构化、便于 AI 分析的家庭资产全景 JSON。"""
    members = member_dao.list_members()
    accounts = account_dao.list_accounts()
    holdings = holding_dao.list_all_holdings()
    assets = asset_dao.list_assets()
    liabilities = liability_dao.list_liabilities()

    totals = report_service.calc_totals()
    net = totals.get("net_worth") or 0.0
    total_assets = totals.get("total_assets") or 0.0
    total_liabilities = totals.get("total_liabilities") or 0.0

    return {
        "meta": {
            "应用": APP_DISPLAY_NAME,
            "导出时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "导出格式版本": EXPORT_VERSION,
            "说明": "本文件为家庭资产全景的结构化导出，供 AI 或数据分析工具直接读取分析。"
                    "保障型保险不计入总资产；公积金计入总资产但不计入可用资金。",
        },
        "汇总指标": {
            "总资产": round(total_assets, 2),
            "总负债": round(total_liabilities, 2),
            "净资产": round(net, 2),
            "可用资金": round(totals.get("liquid_funds") or 0.0, 2),
            "锁定资金": round(totals.get("locked_funds") or 0.0, 2),
            "资产负债率%": round(total_liabilities / total_assets * 100, 2)
                          if total_liabilities and total_assets else 0.0,
        },
        "家庭成员": [
            {"id": m["id"], "姓名": m["name"], "关系": m["relation"], "备注": m.get("note") or "—"}
            for m in members
        ],
        "账户": [
            {
                "id": a["id"],
                "名称": a["name"],
                "类型": type_label(constants.ACCOUNT_TYPES, a["type"]),
                "持有人": a.get("member_name") or "未归属",
                "开户机构": a.get("institution") or "—",
                "币种": a.get("currency") or "CNY",
                "余额": round(a.get("balance") or 0.0, 2),
                "可用性": _liquidity_label(a),
                "状态": "启用" if a.get("is_active") else "停用",
                "备注": a.get("note") or "—",
            }
            for a in accounts
        ],
        "持仓": [_holding_row(h) for h in holdings],
        "资产": [_asset_row(a) for a in assets],
        "负债": [_liability_row(l) for l in liabilities],
    }


def export_structured_json(target_path: str) -> None:
    """导出结构化 JSON 到指定路径（UTF-8、缩进 2、ensure_ascii=False）。"""
    data = build_structured_data()
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

"""报表服务：净资产计算、快照、趋势数据。

计算口径严格遵循 PRD 5.10：
    总资产   = 启用普通账户余额（按汇率折算）+ 持仓账户现金 + 持仓市值 + 资产台账估值
    总负债   = 负债表 remaining 之和 + 信用卡账户余额之和
    净资产   = 总资产 - 总负债
其中持仓市值 = Σ(quantity × current_price)，current_price 为空时用 cost_price 兜底。
"""
import json
from datetime import datetime, timedelta

from app import config
from app.constants import ACCOUNT_TYPE_LABELS, ASSET_TYPE_LABELS
from app.dao import account_dao, asset_dao, holding_dao, liability_dao, snapshot_dao
from app.utils import today_str

# 账户类型常量
CREDIT_CARD_TYPE = "credit_card"                     # 信用卡（负债含义）
HOLDING_ACCOUNT_TYPES = {"stock", "fund"}            # 持仓账户（股票/基金）
WEALTH_TYPE = "wealth"                               # 理财（涉及流动性）


def get_fx_rates() -> dict[str, float]:
    """读取外币汇率配置（JSON）。默认只含 CNY=1。"""
    raw = config.get_setting("fx_rates", "{}") or "{}"
    try:
        rates = json.loads(raw)
    except json.JSONDecodeError:
        rates = {}
    if not isinstance(rates, dict):
        rates = {}  # settings 是明文表，脏值兜底
    # 本位币恒为 1：一旦被误改（如存成 7.0），全部 CNY 余额都会按错误倍率
    # 折算，属于最高优先级的脏数据，读取时强制纠正
    rates["CNY"] = 1.0
    return rates


def _to_cny(amount: float, currency: str, rates: dict[str, float]) -> float:
    """将金额按币种折算为 CNY。找不到汇率时按 1 处理并返回原值。"""
    rate = rates.get(currency, 1.0)
    return amount * rate


def holdings_market_values() -> dict[int, float]:
    """批量取所有持仓账户的市值映射 {account_id: 市值}（现价空用成本价兜底）。

    一次聚合查询取回，供 accounts 页排序/渲染、calc_totals、资产分布等批量
    场景复用，消除逐账户查询的 N+1。
    """
    return holding_dao.holdings_market_value_map()


def holdings_market_value(account_id: int) -> float:
    """计算某持仓账户的全部持仓市值。现价为空时用成本价兜底。"""
    return holdings_market_values().get(account_id, 0.0)


def _asset_ledger_value(assets: list[dict]) -> float:
    """资产台账口径（v1.4）：保障型保险无现金价值，不计入总资产；其余按估值计入。

    这是读路径的统一守护——即使数据库里存在保障型保险的脏 value（如历史数据
    或绕过 UI 的写入），也在统计时排除，避免虚增净资产。
    """
    return sum(
        a["value"]
        for a in assets
        if not (a["type"] == "insurance" and a.get("insurance_subtype") == "protection")
    )


def _is_protection_insurance(asset: dict) -> bool:
    """判断是否为保障型保险（口径上不计入总资产）。"""
    return asset["type"] == "insurance" and asset.get("insurance_subtype") == "protection"


def calc_totals(member_id: int | None = None) -> dict:
    """计算总资产 / 总负债 / 净资产，并返回明细供报表与 AI 使用。

    member_id 为 None：统计全部（账户 + 资产台账 + 负债表）；
    member_id 指定：只统计该成员名下的账户（含持仓/信用卡），
        资产台账与负债表属家庭共有、不计入个人视图。

    v1.2 新增流动性口径（3.1）：
        liquid_funds  = 现金余额 + 理财(available_date 空或 ≤ 今天)余额
        locked_funds  = 理财(available_date > 今天)余额
        next_unlock_date = 锁定资金中最近的可用日期
    """
    rates = get_fx_rates()
    today = today_str()

    # 持仓市值映射一次取回（消除逐账户 N+1）
    mv_map = holdings_market_values()

    total_assets = 0.0
    total_liabilities = 0.0

    # 资产明细（供饼图使用）
    account_cash = 0.0        # 普通账户余额折算 CNY
    holding_cash = 0.0        # 持仓账户现金部分
    holding_value = 0.0       # 持仓市值
    credit_balance = 0.0      # 信用卡余额（负债）

    # 流动性明细（v1.2）
    liquid_funds = 0.0
    locked_funds = 0.0
    next_unlock_date = None

    # 1) 遍历启用账户（按成员过滤）
    for acc in account_dao.list_accounts(active_only=True, member_id=member_id):
        acc_type = acc["type"]
        balance_cny = _to_cny(acc["balance"], acc["currency"], rates)

        if acc_type == CREDIT_CARD_TYPE:
            # 信用卡余额表示已用额度，计入负债
            credit_balance += balance_cny
        elif acc_type in HOLDING_ACCOUNT_TYPES:
            # 持仓账户：现金部分 + 持仓市值（投资，不计入可用资金）
            holding_cash += balance_cny
            holding_value += mv_map.get(acc["id"], 0.0)
        else:
            # 普通资产账户
            account_cash += balance_cny
            # 流动性：现金立即可用；理财按 available_date 区分
            if acc_type == "cash":
                liquid_funds += balance_cny
            elif acc_type == WEALTH_TYPE:
                avail = acc.get("available_date")
                if not avail or avail <= today:
                    liquid_funds += balance_cny
                else:
                    locked_funds += balance_cny
                    if next_unlock_date is None or avail < next_unlock_date:
                        next_unlock_date = avail
            # other 类型不计入可用资金（兜底类型，流动性维度归"其他"）

    # 2) 资产台账估值与负债表：仅"全部"视图计入（无持有人概念）
    if member_id is None:
        asset_value = _asset_ledger_value(asset_dao.list_assets())
        liability_remaining = sum(l["remaining"] for l in liability_dao.list_liabilities())
    else:
        asset_value = 0.0
        liability_remaining = 0.0

    total_assets = account_cash + holding_cash + holding_value + asset_value
    total_liabilities = liability_remaining + credit_balance
    net_worth = total_assets - total_liabilities

    return {
        "total_assets": round(total_assets, 2),
        "total_liabilities": round(total_liabilities, 2),
        "net_worth": round(net_worth, 2),
        # 明细
        "account_cash": round(account_cash, 2),
        "holding_cash": round(holding_cash, 2),
        "holding_value": round(holding_value, 2),
        "asset_value": round(asset_value, 2),
        "credit_balance": round(credit_balance, 2),
        "liability_remaining": round(liability_remaining, 2),
        # 流动性（v1.2）
        "liquid_funds": round(liquid_funds, 2),
        "locked_funds": round(locked_funds, 2),
        "next_unlock_date": next_unlock_date,
    }


# ---------------------------------------------------------------------------
# 快照
# ---------------------------------------------------------------------------
def take_daily_snapshot() -> None:
    """若今天无快照则写入一条。启动时与用户手动点击时调用。

    数据为空时不记快照：首次启动（或刚恢复空库）写入一条全 0 记录，会让趋势图
    出现"从 0 暴涨"的假跳变，且这条脏数据会永久留在库里。
    """
    today = today_str()
    if snapshot_dao.get_snapshot_by_date(today) is not None:
        return  # 今天已有快照，跳过
    t = calc_totals()
    # 三项全为 0 说明还没有任何数据，跳过，避免污染趋势图
    if not (t["total_assets"] or t["total_liabilities"] or t["net_worth"]):
        return
    snapshot_dao.insert_snapshot(today, t["total_assets"], t["total_liabilities"], t["net_worth"])


def range_start(range_key: str) -> str | None:
    """范围键对应的起始日期（YYYY-MM-DD）；"all" 返回 None 表示不限。

    供趋势查询与报表页"期间已还款"等按时间过滤的统计共用，避免各处
    各自维护一份 范围键→天数 的映射。
    """
    days = {"1m": 30, "3m": 90, "6m": 180, "1y": 365}.get(range_key)
    if days is None:
        return None
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def get_trend(range_key: str) -> list[dict]:
    """按范围键取快照列表，供画趋势图。

    range_key: 1m / 3m / 6m / 1y / all
    """
    start = range_start(range_key)
    if start is None:
        return snapshot_dao.list_snapshots()
    return snapshot_dao.list_snapshots(start_date=start)


# ---------------------------------------------------------------------------
# 资产分布（供饼图）
# ---------------------------------------------------------------------------
# 类型 → 中文标签统一由 app.constants 提供（ACCOUNT_TYPE_LABELS / ASSET_TYPE_LABELS），
# 二者由 ACCOUNT_TYPES / ASSET_TYPES 列表派生，避免同一份映射在两处各维护一遍。


def _iter_account_amounts(member_id: int | None):
    """遍历账户（跳过信用卡），逐个产出 (acc, 折算后金额, 持仓市值)。

    这是四个 distribution_by_* 共用的骨架：取汇率 → 列账户 → 跳过信用卡
    → 折算 CNY → 持仓账户附带市值。原先这段在四个函数里各写一遍，
    一旦口径调整（例如改汇率取法）很容易漏改其中一处。
    非持仓账户的持仓市值恒为 0.0，调用方直接相加即可。
    """
    rates = get_fx_rates()
    mv_map = holdings_market_values()
    for acc in account_dao.list_accounts(active_only=True, member_id=member_id):
        if acc["type"] == CREDIT_CARD_TYPE:
            continue  # 信用卡是负债，不进入资产分布
        amount = _to_cny(acc["balance"], acc["currency"], rates)
        holdings = (mv_map.get(acc["id"], 0.0)
                    if acc["type"] in HOLDING_ACCOUNT_TYPES else 0.0)
        yield acc, amount, holdings


def _iter_asset_values(member_id: int | None):
    """遍历资产台账（跳过保障型保险），逐个产出 (asset, 估值)。

    资产台账（房产/车辆等）没有持有人概念，因此仅 member_id 为 None
    （全部视图）时才计入分布。
    """
    if member_id is not None:
        return
    for asset in asset_dao.list_assets():
        if _is_protection_insurance(asset):
            continue  # 保障型保险不计入资产分布
        yield asset, asset["value"]


def distribution_by_account_type(member_id: int | None = None) -> list[tuple[str, float]]:
    """按账户类型统计资产分布。返回 [(标签, 金额), ...]（金额均为 CNY，含持仓市值）。"""
    buckets: dict[str, float] = {}

    for acc, amount, holdings in _iter_account_amounts(member_id):
        label = ACCOUNT_TYPE_LABELS.get(acc["type"], acc["type"])
        buckets[label] = buckets.get(label, 0.0) + amount + holdings

    return sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)


def distribution_by_asset_class(member_id: int | None = None) -> list[tuple[str, float]]:
    """按资产大类统计资产分布：流动资金 / 投资持仓 / 房产 / 车辆 / 其他。

    资产台账（房产/车辆等）无持有人概念，仅 member_id 为 None（全部视图）时计入。
    """
    buckets = {"流动资金": 0.0, "投资持仓": 0.0}

    for acc, amount, holdings in _iter_account_amounts(member_id):
        if acc["type"] in HOLDING_ACCOUNT_TYPES:
            buckets["投资持仓"] += amount + holdings
        else:
            buckets["流动资金"] += amount

    for asset, value in _iter_asset_values(member_id):
        label = ASSET_TYPE_LABELS.get(asset["type"], "其他")
        buckets[label] = buckets.get(label, 0.0) + value

    return sorted(
        ((k, v) for k, v in buckets.items() if v > 0),
        key=lambda kv: kv[1], reverse=True,
    )


def distribution_by_member() -> list[tuple[str, float]]:
    """按持有人统计资产分布（每位成员名下账户的资产金额，含持仓市值）。

    返回 [(成员姓名, 金额), ...]，金额均为 CNY。信用卡（负债）不计入。
    """
    buckets: dict[str, float] = {}

    for acc, amount, holdings in _iter_account_amounts(None):
        name = acc.get("member_name") or "未归属"
        buckets[name] = buckets.get(name, 0.0) + amount + holdings

    return sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)


def distribution_by_liquidity(member_id: int | None = None) -> list[tuple[str, float]]:
    """按流动性统计资产分布：立即可用 / 锁定中 / 投资（股票基金）/ 其他。

    资产台账（房产/车辆等）归"其他"，仅 member_id 为 None（全部视图）时计入。
    """
    today = today_str()
    buckets = {"立即可用": 0.0, "锁定中": 0.0, "投资": 0.0, "公积金": 0.0, "其他": 0.0}

    for acc, amount, holdings in _iter_account_amounts(member_id):
        acc_type = acc["type"]

        if acc_type == "cash":
            buckets["立即可用"] += amount
        elif acc_type == WEALTH_TYPE:
            avail = acc.get("available_date")
            if not avail or avail <= today:
                buckets["立即可用"] += amount
            else:
                buckets["锁定中"] += amount
        elif acc_type in HOLDING_ACCOUNT_TYPES:
            buckets["投资"] += amount + holdings
        elif acc_type == "provident_fund":
            # 公积金计入总资产/净资产，但提取受限，不计入可用资金
            buckets["公积金"] += amount
        else:
            buckets["其他"] += amount

    for _asset, value in _iter_asset_values(member_id):
        buckets["其他"] += value

    return sorted(
        ((k, v) for k, v in buckets.items() if v > 0),
        key=lambda kv: kv[1], reverse=True,
    )

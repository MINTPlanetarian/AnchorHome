"""AI 助手服务：OpenAI 兼容协议调用 DeepSeek。

严守数据授权范围：
    - build_context() 只按 settings 中的授权勾选组装数据摘要；
    - 未勾选的数据绝不发送给 API；
    - 模型返回的修改操作（```action {...}```）只解析不执行，由 UI 弹确认框。
所有网络请求必须在子线程执行。
"""
import json
import math
import re

from app import config, security, constants
from app.constants import type_label
from app.database import get_conn
from app.dao import account_dao, asset_dao, holding_dao, liability_dao
from app.services import report_service
from app.utils import now_str, today_str

# 默认 DeepSeek 配置（PRD 6.1）
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

# 网络超时（秒）。OpenAI SDK 默认 600s：用户点发送后最长要干等 10 分钟，
# 期间发送按钮禁用且无法取消。这里收敛到 60s，失败最多自动重试 1 次。
AI_TIMEOUT_SECONDS = 60
AI_MAX_RETRIES = 1

SYSTEM_PROMPT = """你是家庭财务助手。你只能基于用户授权提供的数据进行分析。
回答末尾必须注明"以上仅供参考，不构成投资建议"。
若需要修改数据，单独输出一行格式：
```action {"op":"update_asset_value","id":1,"value":2350000,"reason":"..."} ```
除此之外不要输出其他格式的修改指令。"""


def _get_ai_config() -> tuple[str, str, str]:
    """读取并解密 AI 配置：返回 (api_key, base_url, model)。"""
    api_key = security.decrypt_text(config.get_setting("ai_api_key", "") or "")
    base_url = config.get_setting("ai_base_url", DEFAULT_BASE_URL) or DEFAULT_BASE_URL
    model = config.get_setting("ai_model", DEFAULT_MODEL) or DEFAULT_MODEL
    return api_key, base_url, model


def is_configured() -> bool:
    """是否已配置 API Key。"""
    api_key, _, _ = _get_ai_config()
    return bool(api_key)


def test_connection() -> tuple[bool, str]:
    """测试连接：发一条极小请求验证配置可用。返回 (是否成功, 提示信息)。"""
    api_key, base_url, model = _get_ai_config()
    if not api_key:
        return False, "尚未配置 API Key"
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url,
                        timeout=AI_TIMEOUT_SECONDS, max_retries=AI_MAX_RETRIES)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        return True, f"连接成功（模型：{model}）"
    except Exception as e:
        return False, f"连接失败：{e}"


# ---------------------------------------------------------------------------
# 数据授权：按勾选组装摘要
# ---------------------------------------------------------------------------
def build_context() -> str:
    """按设置中的授权勾选，组装数据摘要 JSON。

    - ai_scope_summary=1    → 总资产/总负债/净资产；
    - ai_scope_accounts=1   → 各账户名称+类型(中文)+余额；
    - ai_scope_holdings=1   → 持仓明细；
    - ai_scope_liabilities=1→ 负债明细(名称/类型/总额/剩余/已还/利率/月供/备注)；
    - ai_scope_assets=1     → 资产台账(名称/类型/现金价值，保险另含子类型/保额/年保费)；
    - ai_scope_trend=1      → 近 12 个月快照。
    未勾选的绝不包含。
    """
    ctx: dict = {}

    if config.get_setting("ai_scope_summary", "1") == "1":
        t = report_service.calc_totals()
        ctx["summary"] = {
            "总资产": t["total_assets"],
            "总负债": t["total_liabilities"],
            "净资产": t["net_worth"],
            "立即可用资金": t["liquid_funds"],
            "锁定资金": t["locked_funds"],
        }

    if config.get_setting("ai_scope_accounts", "0") == "1":
        # 账户数据按持有人（成员）分组输出，含流动性字段
        today = today_str()
        members_map: dict[int, dict] = {}
        for a in account_dao.list_accounts(active_only=True):
            mid = a.get("member_id")
            mname = a.get("member_name") or "未归属"
            if mid not in members_map:
                members_map[mid] = {"name": mname, "accounts": []}
            avail = a.get("available_date")
            # liquid=True 表示立即可用（现金，或理财中已到期/随时可用）
            liquid = (a["type"] == "cash") or (
                a["type"] == "wealth" and (not avail or avail <= today)
            )
            members_map[mid]["accounts"].append(
                {
                    "名称": a["name"], "类型": type_label(constants.ACCOUNT_TYPES, a["type"]),
                    "余额": a["balance"],
                    "币种": a["currency"], "available_date": avail,
                    "liquid": liquid,
                }
            )
        ctx["members"] = list(members_map.values())

    if config.get_setting("ai_scope_liabilities", "0") == "1":
        # 负债明细：含已还金额(推导)与利率/月供，便于 AI 做负债结构分析
        ctx["liabilities"] = [
            {
                "名称": l["name"],
                "类型": type_label(constants.LIABILITY_TYPES, l["type"]),
                "总金额": l["total_amount"],
                "剩余本金": l["remaining"],
                "已还金额": round((l["total_amount"] or 0) - (l["remaining"] or 0), 2),
                "年利率": l["interest_rate"],
                "月还款额": l["monthly_payment"],
                "备注": l["note"],
            }
            for l in liability_dao.list_liabilities()
        ]

    if config.get_setting("ai_scope_assets", "0") == "1":
        # 资产台账：保险类额外透传子类型/保额/年保费/被保险人，便于 AI 做保障分析
        assets = []
        for a in asset_dao.list_assets():
            item = {
                "名称": a["name"],
                "类型": type_label(constants.ASSET_TYPES, a["type"]),
                "现金价值": a["value"],
            }
            if a["type"] == "insurance":
                item["保险类型"] = type_label(constants.INSURANCE_SUBTYPES, a.get("insurance_subtype"))
                item["保额"] = a.get("coverage")
                item["年保费"] = a.get("annual_premium")
                # v2.1：被保险人（直接显示成员名，默认成员即资产所有者）
                if a.get("insured_name"):
                    item["被保险人"] = a["insured_name"]
            assets.append(item)
        ctx["assets"] = assets

    if config.get_setting("ai_scope_holdings", "0") == "1":
        ctx["holdings"] = [
            {
                "代码": h["code"], "名称": h["name"], "数量": h["quantity"],
                "成本价": h["cost_price"], "现价": h["current_price"],
            }
            for h in holding_dao.list_all_holdings()
        ]

    if config.get_setting("ai_scope_trend", "0") == "1":
        snapshots = report_service.get_trend("1y")
        ctx["trend"] = [
            {"日期": s["snapshot_date"], "总资产": s["total_assets"],
             "总负债": s["total_liabilities"], "净资产": s["net_worth"]}
            for s in snapshots
        ]

    return json.dumps(ctx, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 对话历史
# ---------------------------------------------------------------------------
def save_chat(role: str, content: str) -> None:
    """保存一条对话历史。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "INSERT INTO chat_history (role, content, created_at) VALUES (?, ?, ?)",
                (role, content, now_str()),
            )
    finally:
        conn.close()


def get_recent_history(rounds: int = 20) -> list[dict]:
    """取最近 N 轮（1 轮 = 2 条）对话历史，按时间升序返回。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?",
            (rounds * 2,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def get_full_history() -> list[dict]:
    """取全部对话历史（按时间升序），供聊天页做首屏窗口化与向上滚动懒加载。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT role, content FROM chat_history ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def clear_chat() -> None:
    """清空对话历史。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM chat_history")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 对话与 action 解析
# ---------------------------------------------------------------------------
_ACTION_RE = re.compile(r"```action\s*(\{.*?\})\s*```", re.DOTALL)


def parse_action(text: str) -> dict | None:
    """从回复文本中解析 ```action {...} ``` 块。无则返回 None。"""
    m = _ACTION_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def chat(user_msg: str) -> dict:
    """执行一轮对话。返回 {"reply": str, "action": dict|None}。

    多轮上下文：取 chat_history 最近 20 轮 + system + 授权数据摘要。
    本函数为阻塞式，调用方必须放在子线程执行。
    """
    api_key, base_url, model = _get_ai_config()
    if not api_key:
        raise RuntimeError("尚未配置 AI API Key，请到设置页配置")

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url,
                    timeout=AI_TIMEOUT_SECONDS, max_retries=AI_MAX_RETRIES)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": "当前授权数据摘要：" + build_context()},
    ]
    for h in get_recent_history(20):
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_msg})

    resp = client.chat.completions.create(model=model, messages=messages)
    reply = resp.choices[0].message.content or ""

    action = parse_action(reply)
    # 若含 action，从回复文本中去掉该行，避免在气泡里重复显示
    clean_reply = _ACTION_RE.sub("", reply).strip()

    # 保存历史
    save_chat("user", user_msg)
    save_chat("assistant", clean_reply)

    return {"reply": clean_reply, "action": action}


# ---------------------------------------------------------------------------
# 执行 AI 提议的修改（仅在用户点击“确认执行”后调用）
# ---------------------------------------------------------------------------
def execute_action(action: dict) -> str:
    """执行已确认的操作指令，返回结果描述。支持的操作：
        update_asset_value   —— 更新资产估值
        update_account_balance —— 更新账户余额
    """
    op = action.get("op")
    # 模型输出的 id/value 统一做健壮解析：畸形指令给出可读错误而非裸 traceback
    try:
        item_id = int(action["id"])
        value = float(action["value"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("操作指令格式不正确：id/value 缺失或不是数字")
    if not math.isfinite(value):
        raise ValueError("操作指令的 value 不是有效数字")
    if op == "update_asset_value":
        asset_id = item_id
        asset = asset_dao.get_asset(asset_id)
        if asset is None:
            raise ValueError("资产项不存在")
        # 口径守护：保障型保险无现金价值，实际生效值强制 0（避免 AI 虚增净资产）
        eff_value = 0.0 if (
            asset["type"] == "insurance" and asset.get("insurance_subtype") == "protection"
        ) else value
        asset_dao.update_asset(
            asset_id, asset["name"], asset["type"], eff_value,
            asset["purchase_date"], asset["note"],
            asset.get("insurance_subtype"), asset.get("coverage"), asset.get("annual_premium"),
            asset.get("insured_member_id"),
        )
        return f"已将「{asset['name']}」估值更新为 ¥{eff_value:,.2f}"

    if op == "update_account_balance":
        account_id = item_id
        acc = account_dao.get_account(account_id)
        if acc is None:
            raise ValueError("账户不存在")
        account_dao.update_account(
            account_id, acc["name"], acc["type"], acc["currency"], value,
            acc["institution"], acc["note"], acc.get("member_id"),
            acc.get("available_date"),
        )
        return f"已将「{acc['name']}」余额更新为 ¥{value:,.2f}"

    raise ValueError(f"不支持的操作类型：{op}")

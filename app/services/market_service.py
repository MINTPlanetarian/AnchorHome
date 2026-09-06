"""行情服务：A 股股票 / 场内基金 / 场外基金免费行情获取。

实现遵循《行情API获取说明.md》：
    - 代码 → 市场判断规则（detect_market）；
    - 方案一 akshare（首选）→ 方案二 腾讯 qt.gtimg.cn → 方案三 新浪 hq.sinajs.cn；
    - 批量优先、失败保留缓存价（三个数据源按顺序降级，单次失败不重试）；
    - 所有网络请求在子线程执行（MarketFetcher），避免卡 UI。
"""
from PySide6.QtCore import QThread, Signal

try:
    import akshare as ak
    _HAS_AKSHARE = True
except Exception:  # akshare 未安装或导入失败时自动降级
    ak = None
    _HAS_AKSHARE = False

import requests

from app.logging_setup import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 代码 → 市场判断
# ---------------------------------------------------------------------------
def detect_market(code: str) -> str:
    """根据证券代码判断市场。返回 'SH' / 'SZ' / 'BJ' / 'FUND'（场外基金）。

    判定规则（详见《行情API获取说明.md》）：
        1. 6 开头                -> SH（沪市A股、科创板688）
        2. 50/51/52/56/58 开头   -> SH（沪市ETF/LOF/封闭式基金）
        3. 588 开头              -> SH（科创板ETF，已含于 58 前缀）
        4. 000/001/002/003 开头  -> SZ（深市主板/中小板）
        5. 300/301 开头          -> SZ（创业板）
        6. 15/16 开头            -> SZ（深市ETF/LOF）
        7. 111/113/118 开头      -> SH（沪市可转债）
        8. 123/127/128 开头      -> SZ（深市可转债）
        9. 43/82/83/87/88/92 开头 -> BJ（北交所，92 为 2024 年起新号段）
       10. 其余                  -> FUND（场外开放式基金，走净值接口）

    注：场外基金与股票/可转债共用代码空间，纯前缀无法完全区分。
    例如 110 开头同时含上交所可转债（110043 无锡转债）与场外开放式基金
    （110022 易方达消费）。此处 110 不归入可转债，由录入时的账户类型推导
    market（fund 类型账户强制 FUND）作为更可靠的依据。
    """
    code = code.strip()
    if not (code.isdigit() and len(code) == 6):
        raise ValueError(f"无法识别的代码: {code}")

    # 1. 沪市 A 股 / 科创板（68*/60*/688 等 6 开头）
    if code[0] == "6":
        return "SH"
    # 2. 沪市 ETF/LOF/封闭式基金（含科创板ETF 588）
    if code[:2] in ("50", "51", "52", "56", "58"):
        return "SH"
    # 7. 沪市可转债（111/113/118）
    #    注：110 开头与场外基金重叠，不归入可转债，交由账户类型推导 market
    if code[:3] in ("111", "113", "118"):
        return "SH"
    # 4. 深市主板 / 中小板
    if code[:3] in ("000", "001", "002", "003"):
        return "SZ"
    # 5. 创业板
    if code[:3] in ("300", "301"):
        return "SZ"
    # 6. 深市 ETF/LOF
    if code[:2] in ("15", "16"):
        return "SZ"
    # 8. 深市可转债
    if code[:3] in ("123", "127", "128"):
        return "SZ"
    # 9. 北交所（43/82/83/87/88/92，92 为 2024 年起新号段）
    if code[:2] in ("43", "82", "83", "87", "88", "92"):
        return "BJ"
    # 10. 其余：场外开放式基金，走净值接口
    return "FUND"


def _with_prefix(code: str) -> str:
    """生成新浪/腾讯接口所需的带前缀代码，如 600519 -> sh600519。"""
    m = detect_market(code)
    return m.lower() + code


# ---------------------------------------------------------------------------
# 方案一：akshare
# ---------------------------------------------------------------------------
def _fetch_a_shares_by_akshare(codes: list[str]) -> dict:
    """用 akshare 全 A 股快照一次取回所有股票/场内基金现价。"""
    if not _HAS_AKSHARE:
        raise RuntimeError("akshare 不可用")
    df = ak.stock_zh_a_spot_em()
    result = {}
    spot = df.set_index("代码")
    for code in codes:
        if code in spot.index:
            try:
                result[code] = float(spot.loc[code, "最新价"])
            except (ValueError, TypeError):
                continue
    return result


def _fetch_fund_by_akshare(code: str) -> float:
    """场外基金：取最新单位净值（通常为上一交易日数据）。"""
    if not _HAS_AKSHARE:
        raise RuntimeError("akshare 不可用")
    df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
    if df is None or df.empty:
        raise RuntimeError(f"基金 {code} 无净值数据")
    return float(df.iloc[-1]["单位净值"])


def _fetch_fund_by_sina(code: str) -> float:
    """场外基金净值兜底：新浪 fu_ 接口（akshare 失败时使用）。

    返回形如：var hq_str_fu_013309="名称,时间,单位净值,累计净值,...";
    其中第 3 个逗号字段（索引 2）为单位净值。
    """
    url = f"https://hq.sinajs.cn/list=fu_{code}"
    resp = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=6)
    resp.raise_for_status()
    text = resp.content.decode("gbk")
    if "=" not in text or '"' not in text:
        raise RuntimeError(f"基金 {code} 新浪接口格式异常")
    payload = text.split("=", 1)[1].strip().strip(";").strip('"')
    parts = payload.split(",")
    if len(parts) < 3 or not parts[2]:
        raise RuntimeError(f"基金 {code} 无净值数据")
    return float(parts[2])


# ---------------------------------------------------------------------------
# 方案二：腾讯行情
# ---------------------------------------------------------------------------
def _fetch_by_tencent(codes: list[str]) -> dict:
    """腾讯批量接口：一次请求多个带前缀代码。返回 {code: price}。"""
    prefixed = [_with_prefix(c) for c in codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    text = resp.content.decode("gbk")
    prices = {}
    for line in text.strip().split(";"):
        if "=" not in line:
            continue
        payload = line.split("=", 1)[1].strip().strip('"')
        parts = payload.split("~")
        # parts[2]=代码, parts[3]=现价
        if len(parts) > 3 and parts[3]:
            try:
                prices[parts[2]] = float(parts[3])
            except ValueError:
                continue
    return prices


# ---------------------------------------------------------------------------
# 方案三：新浪行情
# ---------------------------------------------------------------------------
def _fetch_by_sina(codes: list[str]) -> dict:
    """新浪接口：必须带 Referer 头，否则 403。返回 {code: price}。"""
    prefixed = [_with_prefix(c) for c in codes]
    headers = {"Referer": "https://finance.sina.com.cn"}
    url = "https://hq.sinajs.cn/list=" + ",".join(prefixed)
    resp = requests.get(url, headers=headers, timeout=5)
    resp.raise_for_status()
    text = resp.content.decode("gbk")
    prices = {}
    for line in text.strip().split("\n"):
        if "=" not in line:
            continue
        # var hq_str_sh600519="贵州茅台,今开,昨收,当前价,..."
        var_part = line.split("=", 1)[0]           # var hq_str_sh600519
        code = var_part.split("_")[-1]             # sh600519
        code = code[2:]                            # 去掉前缀，得 600519
        payload = line.split("=", 1)[1].strip().strip('"').strip(";")
        parts = payload.split(",")
        if len(parts) > 3 and parts[3]:
            try:
                prices[code] = float(parts[3])     # parts[3]=当前价
            except ValueError:
                continue
    return prices


# ---------------------------------------------------------------------------
# 核心：批量获取（含降级决策树）
# ---------------------------------------------------------------------------
def fetch_all_prices(codes: list[str]) -> dict:
    """批量获取所有持仓现价。

    逐级补齐策略（对应说明文档第 6 章降级决策树）：
        1. akshare 全量快照 —— 只覆盖 A 股股票（不含 ETF/场内基金）；
        2. 腾讯批量接口 —— 补齐 akshare 缺失的代码（ETF 等）或 akshare 整体失败时的全部代码；
        3. 新浪接口 —— 腾讯仍未取到的继续补齐；
        4. 仍一无所得则抛异常，UI 提示并保留缓存价。
    场外基金（FUND）单独走 akshare 净值接口，失败时保留缓存价（不抛错）。
    返回 {code: price}，可能只含部分代码（个别失败不影响整体）。
    """
    codes = [c.strip() for c in codes if c and c.strip()]
    if not codes:
        return {}

    stock_codes = [c for c in codes if detect_market(c) != "FUND"]
    fund_codes = [c for c in codes if detect_market(c) == "FUND"]

    result: dict[str, float] = {}
    stock_failed: list[str] = []
    fund_failed: list[str] = []

    # --- 股票 / 场内基金：逐级补齐缺失（akshare → 腾讯 → 新浪） ---
    if stock_codes:
        # 方案一：akshare 全量快照（仅覆盖 A 股股票，ETF 不在其中）
        if _HAS_AKSHARE:
            try:
                result.update(_fetch_a_shares_by_akshare(stock_codes))
            except Exception:
                # 整体失败，留给下一级补齐；记日志以便排查"行情不准"
                logger.warning("akshare 行情获取失败，降级到腾讯接口", exc_info=True)

        # 方案二：腾讯批量接口，补齐 akshare 未取到的
        missing = [c for c in stock_codes if c not in result]
        if missing:
            try:
                result.update(_fetch_by_tencent(missing))
            except Exception:
                logger.warning("腾讯行情接口失败，降级到新浪接口", exc_info=True)

        # 方案三：新浪接口，兜底补齐
        missing = [c for c in stock_codes if c not in result]
        if missing:
            try:
                result.update(_fetch_by_sina(missing))
            except Exception:
                logger.warning("新浪行情接口失败（已是最低一级），沿用缓存价", exc_info=True)

        # 记下没取到价的股票/场内基金（用于报错时点名）
        stock_failed = [c for c in stock_codes if c not in result]
        if stock_failed:
            logger.warning("以下代码三级接口均未取到行情，沿用缓存价: %s",
                           ",".join(stock_failed))

    # --- 场外基金：akshare 净值为主，新浪净值兜底 ---
    for code in fund_codes:
        price = None
        if _HAS_AKSHARE:
            try:
                price = _fetch_fund_by_akshare(code)
            except Exception:
                price = None
        if price is None:
            try:
                price = _fetch_fund_by_sina(code)
            except Exception:
                price = None
        if price is not None:
            result[code] = price
        else:
            fund_failed.append(code)

    # 一只都没取到才报错，并点名失败的具体代码，便于排查
    if not result:
        msgs = []
        if stock_failed:
            msgs.append(f"股票/场内基金获取失败：{', '.join(stock_failed)}（多为网络不通）")
        if fund_failed:
            msgs.append(f"场外基金净值获取失败：{', '.join(fund_failed)}（akshare/新浪净值接口异常）")
        if not msgs:
            msgs.append("未获取到任何行情")
        raise RuntimeError("；".join(msgs) + "。显示为缓存价格。")

    return result


def lookup_name(code: str) -> str | None:
    """录入持仓时按代码自动补全名称。失败返回 None。"""
    if not _HAS_AKSHARE:
        return None
    try:
        if detect_market(code) == "FUND":
            df = ak.fund_name_em()
            row = df[df["基金代码"] == code]
            return str(row.iloc[0]["基金简称"]) if not row.empty else None
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == code]
        return str(row.iloc[0]["名称"]) if not row.empty else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 后台线程：批量刷新行情
# ---------------------------------------------------------------------------
class MarketFetcher(QThread):
    """后台行情线程：批量拉取所有持仓现价。

    信号：
        finished_with_prices(dict)  —— {code: price}
        failed(str)                 —— 错误信息
    """

    finished_with_prices = Signal(dict)
    failed = Signal(str)

    def __init__(self, codes: list[str], parent=None):
        super().__init__(parent)
        self._codes = list(codes)

    def run(self):
        try:
            prices = fetch_all_prices(self._codes)
            self.finished_with_prices.emit(prices)
        except Exception as e:
            self.failed.emit(str(e))

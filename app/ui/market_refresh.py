"""行情刷新启动器（主窗口与账户页共用）。

原先 main_window 与 accounts_page 各写了一遍：
    列持仓 → 去重取代码 → new MarketFetcher(parent=None) → 连两个信号 → 启动
两处实现的唯一差别只是"刷新完成后做什么"，容易在改动一端时漏掉另一端。
这里把公共部分收敛成一个函数，调用方只传回调。
"""
from __future__ import annotations

from app.dao import holding_dao
from app.services.market_service import MarketFetcher
from app.ui.thread_helper import start_thread


def start_market_refresh(owner, attr: str, on_ready, on_failed) -> bool:
    """启动一次行情刷新。

    Args:
        owner:     持有线程引用的对象（页面或主窗口）
        attr:      存放引用的属性名，如 "_fetcher"
        on_ready:  成功回调，接收 {code: price}
        on_failed: 失败回调，接收错误信息字符串

    Returns:
        True  已启动。
        False 未启动——原因可能是没有任何持仓，或上一次刷新仍在进行（防重入）。
              调用方如需区分，可自行调用 holding_dao.list_all_holdings() 判断。
    """
    holdings = holding_dao.list_all_holdings()
    if not holdings:
        return False
    codes = list({h["code"] for h in holdings})
    # parent=None：避免宿主先销毁时 C++ slot 在已删除对象上调用导致段错误闪退
    fetcher = MarketFetcher(codes, parent=None)
    fetcher.finished_with_prices.connect(on_ready)
    fetcher.failed.connect(on_failed)
    return start_thread(owner, attr, fetcher)

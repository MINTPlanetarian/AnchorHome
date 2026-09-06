"""后台 QThread 生命周期辅助。

背景：项目里多处写法是 `self._worker = SomeThread(...)` 然后 start()，
这带来两个崩溃风险：

1. **引用被覆盖**：重复点击刷新、或「启动刷新 + 定时刷新 + 手动刷新」叠加时，
   新的线程对象覆盖掉 `self._worker`，旧线程 Python 侧引用归零；若它仍在运行，
   PySide 会在 GC 时销毁运行中的 QThread，报
   "QThread: Destroyed while thread is still running"，进程直接崩。
2. **宿主先销毁**：窗口/弹窗关闭时线程还在跑，同样触发上述崩溃。

start_thread() / stop_thread() 统一托管：防重入、结束后自动释放引用并 deleteLater。
"""
from functools import partial

from PySide6.QtCore import QThread


def start_thread(owner, attr: str, thread: QThread) -> bool:
    """托管启动一个后台线程（信号请在调用前自行连接）。

    用法::

        t = MyWorker(...)
        t.some_signal.connect(self._on_done)
        start_thread(self, "_worker", t)

    Args:
        owner:  持有线程引用的对象（通常是页面或弹窗的 self）
        attr:   存放引用的属性名，如 "_fetcher" / "_worker"
        thread: 已构造、信号已连接、但尚未 start 的 QThread

    Returns:
        True  已启动。
        False 同名属性上的线程仍在运行，本次请求被丢弃（防重入）。
    """
    old = getattr(owner, attr, None)
    if old is not None:
        if old.isRunning():
            return False          # 防重入：上一条还没跑完，忽略本次请求
        _release(owner, attr)     # 已结束但尚未清理的残留线程，先释放
    setattr(owner, attr, thread)
    _register(owner, attr)
    # finished 是 QThread 内置信号；子类切勿用同名信号遮蔽它（见 settings_page / ai_chat_page）
    thread.finished.connect(partial(_release, owner, attr))
    thread.start()
    return True


def _register(owner, attr: str) -> None:
    """把属性名登记到 owner 名下，供 stop_all_threads() 在关闭时统一回收。"""
    attrs = getattr(owner, "_managed_thread_attrs", None)
    if attrs is None:
        attrs = set()
        owner._managed_thread_attrs = attrs
    attrs.add(attr)


def stop_all_threads(owner) -> None:
    """停止 owner 名下所有托管线程（主窗口/弹窗关闭时统一调用）。"""
    attrs = getattr(owner, "_managed_thread_attrs", None)
    if not attrs:
        return
    for attr in list(attrs):      # 拷贝后遍历：_release 会从集合中移除
        stop_thread(owner, attr)


def stop_thread(owner, attr: str, wait_ms: int = 3000) -> None:
    """停止并回收托管的线程，用于窗口/弹窗关闭时。

    最多等待 wait_ms 毫秒；超时则 terminate() 强制终止。本项目的工作线程
    阻塞在网络 IO 上且 run() 内无事件循环，quit() 对它们无效，只等待后放弃
    的话线程仍在运行，对象随后被销毁依旧会触发
    "QThread: Destroyed while thread is still running" 崩溃。强制终止只发生
    在关闭窗口的瞬间，最坏代价是本次请求结果作废（行情落库在 GUI 线程完成，
    不会损坏数据）。
    """
    thread = getattr(owner, attr, None)
    if thread is None:
        return
    try:
        if thread.isRunning():
            thread.requestInterruption()
            thread.quit()
            if not thread.wait(wait_ms):
                thread.terminate()
                thread.wait(1000)
    except RuntimeError:
        pass                      # C++ 对象已销毁
    finally:
        _release(owner, attr)


def _release(owner, attr: str) -> None:
    """释放 owner 上的线程引用与登记，并安排 deleteLater。"""
    attrs = getattr(owner, "_managed_thread_attrs", None)
    if attrs is not None:
        attrs.discard(attr)
    thread = getattr(owner, attr, None)
    if thread is None:
        return
    setattr(owner, attr, None)    # 先断引用，防止重复释放
    try:
        thread.deleteLater()
    except RuntimeError:
        pass

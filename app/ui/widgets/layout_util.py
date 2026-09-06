"""布局清理工具（递归）。

项目里多处需要"清空容器后重建"（刷新列表、切换图表、切换空状态等）。
常见写法是::

    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w:
            w.deleteLater()

这段只对**直接 addWidget 进来**的控件有效。如果当初是用 addLayout() 加的嵌套布局，
item.widget() 返回 None，分支被跳过——子布局及其内部的控件既不被销毁、也不从父
容器脱离：每次刷新都累积一批泄漏控件，且旧控件可能仍以最后的几何位置残留在界面上。

clear_layout() 递归处理这两种情况，全项目统一调用它。
"""


def clear_layout(layout) -> None:
    """递归清空布局：销毁所有控件、递归清理并销毁所有子布局。

    Args:
        layout: 要清空的 QLayout；为 None 时静默返回。
    """
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        w = item.widget()
        if w is not None:
            # 先脱离父容器，避免删除前仍参与布局/绘制
            w.setParent(None)
            w.deleteLater()
            continue
        child = item.layout()
        if child is not None:
            clear_layout(child)          # 先销毁子布局里的控件
            child.setParent(None)
            child.deleteLater()
        # 其余情况（如 QSpacerItem）随 takeAt 已移出布局，丢弃即可

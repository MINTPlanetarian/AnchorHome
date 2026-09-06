"""安航家资（FamilyAsset）程序入口。

启动流程：
    1. 初始化数据库（建表）；
    2. 判断是否已设置启动密码；
    3. 首次启动 → 设置密码对话框；后续 → 登录校验对话框；
    4. 校验通过后进入主窗口。
"""
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import config
from app.database import init_db
from app.logging_setup import setup_logging
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.widgets.icon import find_app_icon


def main() -> int:
    """程序入口。返回进程退出码。"""
    # 1) 初始化数据库
    init_db()
    # 配置日志：写到 数据目录/logs/app.log，排查行情降级、备份失败等问题
    setup_logging()

    # 创建 QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("安航家资")

    # 设置窗口标题栏图标（找不到文件时回退到 exe 内嵌图标）
    icon_path = find_app_icon()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    # 2) 首次启动设置密码 / 后续登录校验
    if config.has_password():
        login = LoginDialog(mode="login")
    else:
        login = LoginDialog(mode="setup")

    if login.exec() != LoginDialog.Accepted:
        return 0  # 用户取消登录，退出

    # 3) 进入主窗口
    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

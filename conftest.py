"""pytest 全局配置：统一测试环境。

- 测试期间将数据库/附件/备份重定向到临时目录，避免污染正式数据；
- 启用 Qt offscreen 平台插件，使 GUI 测试在无显示环境下可运行。

注意：各 test_*.py 在「直接运行（python xxx.py）」时会自行设置临时目录，
此处仅在 pytest 下、且环境变量尚未设置时兜底，保证 import app 前环境已就位。
"""
import os


def pytest_configure(config):
    # 兜底启用 offscreen；各 test_*.py 自行把数据目录重定向到独立临时目录
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

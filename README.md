# 安航家资（Anchorhome）

本地优先的家庭资产管理桌面工具。账户、股票基金持仓、房产车辆保险台账、负债与家庭成员
全部记录在你自己的电脑上，由启动密码保护，不上传任何服务器。

## 功能特性

- **总览**：总资产 / 负债 / 净资产 / 可用资金一屏呈现，"较 7 日前"环比、理财到期与
  估值滞后提醒、按持有人筛选。
- **账户**：现金 / 理财（含可用日期与流动性口径）/ 公积金 / 股票 / 基金 / 信用卡七类，
  支持多币种与汇率折算。
- **持仓**：股票、场内/场外基金自动获取现价（akshare → 腾讯 → 新浪 三级降级），
  盈亏一目了然。
- **资产台账**：房产、车辆、贵金属与保险（保障型不计入总资产、储蓄型按现金价值计入），
  支持附件管理。
- **负债**：房贷 / 车贷 / 消费贷等还款进度跟踪与还款历史。
- **报表**：净资产趋势、期间变动、资产构成、负债构成与快照明细表（可导出 CSV）。
- **AI 助手**：接入 DeepSeek（OpenAI 兼容协议），按勾选的数据授权范围发送摘要，
  AI 提议的修改需人工确认后才会执行。
- **安全**：启动密码（PBKDF2 派生），API Key 加密存储，加密备份（.fabak）与明文 JSON
  备份/恢复，恢复前自动备份当前数据。

## 技术栈

Python 3 · PySide6 · SQLite · akshare · pyqtgraph · PyInstaller

## 运行

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python main.py
```

首次启动会要求设置启动密码，数据自动保存在项目根目录的 `data/` 下。

## 运行测试

```bash
venv\Scripts\python -m pytest test_logic.py test_insurance_ui.py gui_smoke_test.py -q
```

- `test_logic.py`：核心逻辑（建表迁移 / 口径计算 / 备份恢复 / 行情市场判断）
- `test_insurance_ui.py`：保险口径 UI 全链路回归
- `gui_smoke_test.py`：主窗口与全部页面构建冒烟

测试自动重定向数据目录到临时文件夹，不会污染真实数据。

## 打包（Windows 单文件 exe）

```bash
build.bat
```

或手动执行：

```bash
venv\Scripts\pyinstaller.exe 安航家资.spec --noconfirm
```

产物为 `dist/安航家资.exe`，首次运行会在 exe 同级目录生成 `data/` 保存数据。

## 数据与隐私

- 所有数据仅存储于本机 `data/` 目录（SQLite + 附件 + 日志），卸载即删除。
- 启动密码用于保护应用入口；AI API Key 经 Fernet 加密存储；`.fabak` 备份为加密格式。
- AI 助手仅在用户勾选相应授权范围后，才会把对应数据摘要发送给所配置的大模型服务。
- 行情数据来自免费公开接口（akshare / 腾讯 / 新浪），接口变更可能导致刷新降级或失败。

## 目录结构

```
app/
  dao/        数据访问层（SQLite）
  services/   业务服务（报表口径 / 行情 / 备份 / AI / 导出）
  ui/         PySide6 界面（页面 + 组件 + 设计令牌）
main.py       程序入口
安航家资.spec PyInstaller 打包配置
```

# 个人交易系统：本地决策工作台 + AkShare 日线流水线

## 功能
- 板块轮动阶段初步判定、四项共振检查、入场 Checklist、风险仓位计算
- SQLite 本地交易日志与 CSV 导出
- AkShare 行业板块日线、沪深300日线同步
- SQLite 原始行情、派生指标、同步运行状态持久化
- 近 3/5 个交易日涨跌幅、相对沪深300强度（RS）、近3/10日均成交额比、MA5
- 同步可重复执行，按（板块/交易日）主键 upsert
- 每日任务 CLI，供 Windows Task Scheduler 或 cron 在收盘后调用

## 环境与启动
建议 Python 3.11+（使用 64 位 Python，并以 AKShare 当前安装说明为准）。
```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## 行情同步
首次建议回补 90 个自然日：
```bash
python -m services.daily_job --db market_data.sqlite3 --lookback-days 90
```
默认沪深300指数代码为 `csi000300`。行业板块通过 `stock_board_industry_name_em()` 和 `stock_board_industry_hist_em(..., period="日k", ...)` 获取；基准通过 `stock_zh_index_daily_em(symbol="csi000300", ...)` 获取。

程序提供单次 CLI 任务，不会自行在后台常驻或创建操作系统计划任务。请使用 Windows Task Scheduler 或 cron 配置为每个交易日收盘后运行，并监控退出码及 SQLite 的 `sync_runs` 表。建议先留出数据源更新延迟，再按实际更新情况调整执行时间。

## 指标定义
- ret3/ret5：当前收盘价相对 3/5 个交易日前收盘价的百分比变化。
- RS3/RS5：板块同期涨跌幅减去沪深300同期涨跌幅，单位为百分点。
- amount_ratio：近3个交易日平均成交额 / 近10个交易日平均成交额。
- ma5：最近5个交易日收盘价简单移动平均。
- 只有板块与沪深300共同存在的交易日参与计算；不足窗口的数据不输出指标。

## 数据质量与边界
- 对空数据、缺失必需字段、非数值、非正收盘价做校验；单个行业失败会记入错误摘要并继续其他行业。
- 第三方数据源可能延迟、修订或不可用；连续两日确认基于连续两次数据记录，当前版本尚无独立交易日历校验。
- 不连接券商、不下单、不自动交易，不构成投资建议。请先用历史数据验证策略。

## 定时任务示例
Windows Task Scheduler：程序指向虚拟环境的 python.exe，参数：
```text
-m services.daily_job --db market_data.sqlite3 --lookback-days 30
```
“起始于”设置为仓库目录。Linux/macOS cron：
```cron
10 16 * * 1-5 cd /path/to/personal-trading-system && .venv/bin/python -m services.daily_job --db market_data.sqlite3 --lookback-days 30
```
节假日和数据源空结果需在任务日志中核查；当前版本已提供上游请求指数退避重试、逐行业异常隔离、结构化日志和日志轮转；生产环境仍建议接入交易日历与外部告警。

## 失败重试与日志监控

- AKShare 每个上游请求默认最多尝试 3 次，采用指数退避（约 1、2 秒起步）和随机抖动；仅在请求层重试，字段校验/指标计算错误不会被当作网络故障反复重试。
- 可通过环境变量 `AKSHARE_RETRY_ATTEMPTS` 调整最大尝试次数，通过 `TRADING_LOG_LEVEL` 调整日志级别（默认 INFO）。
- 每次行业同步单独隔离；失败行业记录名称、异常堆栈和耗时，其余行业继续执行。整体状态为 `success`、`partial` 或 `failed`。
- CLI 默认同时输出控制台日志，并在 `logs/market_sync.jsonl` 写入 UTF-8 JSON Lines 日志；单文件达到 5 MB 后轮转，保留 5 个备份。日志目录可通过 `--log-dir` 修改。
- 任务非完整成功时返回非零退出码。建议计划任务按退出码告警，并定期检查 SQLite `sync_runs` 表中的状态和错误摘要。
- 示例：`python -m services.daily_job --db market_data.sqlite3 --lookback-days 90 --log-dir logs`

## 数据过期检测与告警

- 每次同步结束后，以沪深300最新交易日作为数据新鲜度基准；默认允许最多 5 个自然日的间隔（覆盖周末及常见短假期），超过阈值或基准数据为空则标记为 stale，并使任务返回非零退出码。
- 可用 `--max-data-age-days 5` 调整阈值。该检查是保守的日历天数规则，不是完整交易日历；长假期间可按实际情况调整，避免误报。
- 配置环境变量 `TRADING_ALERT_WEBHOOK_URL` 后，任务遇到部分失败、整体失败或数据过期时会向企业微信机器人 Webhook 发送标准文本消息（`msgtype=text`）。程序会检查企业微信返回的 `errcode`，不只检查 HTTP 状态码。Webhook 未配置时仍写日志并在命令行输出健康状态。
- 如需每次成功后也推送日报，添加 `--alert-on-success`。Webhook 投递失败只记录日志，不覆盖行情同步结果。
- 示例（Linux/macOS）：`export TRADING_ALERT_WEBHOOK_URL="https://your-webhook-endpoint"`；Windows PowerShell：`$env:TRADING_ALERT_WEBHOOK_URL="https://your-webhook-endpoint"`。请将真实地址放在运行环境变量或密钥管理中，不要提交到 Git。

- GitHub Actions 使用时，请在仓库 **Settings → Secrets and variables → Actions → New repository secret** 新建 `TRADING_ALERT_WEBHOOK_URL`，值填入重置后企业微信机器人的完整 Webhook URL；不要把 URL 写进仓库文件、Workflow 明文或提交记录。
- 本地运行时，可在操作系统环境变量或本地未跟踪的 `.env`/启动脚本中设置该变量；不要提交密钥。

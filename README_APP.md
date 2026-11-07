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

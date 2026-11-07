# 个人交易系统：可运行 MVP

本分支在原有 v2.3 规则手册基础上增加一个本地可运行的 Streamlit 决策工作台。

## 当前功能

- 板块轮动阶段初步判定：主升、补涨、退潮、冷门、观察
- 按 v2.3 阈值计算 RS、成交额变化等指标的规则判定
- 提供带日期历史记录的连续确认检查
- 四项共振检查和入场 Checklist
- 仓位计算：风险预算、方向性止损校验（多头止损低于入场价、空头止损高于入场价）、成本估算、阶段/信心/外部环境系数、资金占比上限
- 输入校验：拒绝无穷/非数值行情、重复板块日期、无效价格及超范围风险参数
- SQLite 本地交易日志，支持 CSV 导出
- CSV 导入与分析结果导出

## 启动

需要 Python 3.10 或更高版本。

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

浏览器打开 Streamlit 显示的本地地址，通常为 http://localhost:8501 。

## CSV 格式

必需列：

```csv
sector,ret3_pct,ret5_pct,rs3_pct,rs5_pct,amount_ratio,close,ma5
半导体,1.5,3.2,1.1,2.3,1.25,100,98
```

- 百分比填写数值，例如 1.5 代表 1.5%，不是 0.015。
- RS = 板块同期涨跌幅 - 沪深300同期涨跌幅。
- amount_ratio = 近3日日均成交额 / 近10日日均成交额。
- 可选 date 列用于按板块检查连续确认。带日期的历史行必须按交易日连续提供；同一板块同一日期不允许重复。

## 重要边界

- 当前不提供行情 API 接入，不自动采集行情、主力资金、PCR 或海外数据。
- 当前不连接券商，不发送订单，不构成自动交易系统。
- 单日导入时，主升/退潮连续确认无法验证，界面会标注为初步判断。
- 计划亏损是估算值；跳空、流动性、涨跌停和执行滑点可能使真实损失更大。
- SQLite 文件 `trading_journal.db` 默认保存在应用目录，请自行备份；不要把含个人交易记录的数据库提交到公开仓库。

## 后续建议

1. 接入可靠且有授权的数据源，并保存原始数据及时间戳。
2. 完成历史回测、样本外验证、手续费/滑点/停牌涨跌停建模。
3. 增加多标的组合风险、相关性和总风险敞口约束。
4. 模拟交易稳定后，再单独评估券商接口；默认保持人工确认。


## 行情同步
首次建议回补 90 个自然日：
```bash
python -m services.daily_job --db market_data.sqlite3 --lookback-days 90
```
行业板块通过 `stock_board_industry_name_em()` 和 `stock_board_industry_hist_em(..., period="日k", ...)` 获取。沪深300基准优先使用 `stock_zh_index_daily_em(symbol="csi000300", ...)`；当该东方财富接口返回空数据或异常时，自动回退到 AKShare 通用指数接口 `index_zh_a_hist(symbol="000300", period="daily", ...)`。两个接口均不可用或回退结果为空时，任务会明确报错，不会跳过基准数据继续生成误导性的 RS 分析。

程序提供单次 CLI 任务，不会自行在后台常驻或创建操作系统计划任务。请使用 Windows Task Scheduler 或 cron 配置为每个交易日收盘后运行，并监控退出码及 SQLite 的 `sync_runs` 表。建议先留出数据源更新延迟，再按实际更新情况调整执行时间。

## 指标定义
- ret3/ret5：当前收盘价相对 3/5 个交易日前收盘价的百分比变化。
- RS3/RS5：板块同期涨跌幅减去沪深300同期涨跌幅，单位为百分点。
- amount_ratio：近3个交易日平均成交额 / 近10个交易日平均成交额。
- ma5：最近5个交易日收盘价简单移动平均。
- 只有板块与沪深300共同存在的交易日参与计算；不足窗口的数据不输出指标。

## 数据质量与边界
- 对空数据、缺失必需字段、非数值、非正收盘价做校验；单个行业失败会记入错误摘要并继续其他行业。
- 第三方数据源可能延迟、修订或不可用；连续确认使用沪深300基准交易日序列；板块缺失的交易日会显式保留并重置连续确认，避免跨缺口误判。
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

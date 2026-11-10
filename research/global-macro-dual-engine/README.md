# A股全球宏观联动·双引擎量化交易系统

本目录独立归档全球宏观联动、A股市场确认、龙头短线与趋势波段双引擎研究系统。与仓库原有个人交易系统并行维护，不覆盖、不修改原有文件。

## 研究定位
- 龙头短线：目标持仓约3–5个交易日。
- 趋势波段：目标持仓约2–8周。
- 范围：沪深主板、创业板、科创板，交易制度按证券类别及历史时期处理。
- 当前阶段：理论规则规格化；尚未完成程序实现、历史回测和模拟交易验收。
- 目标：检验样本外统计优势，而非追求确定性预测。

## 最高优先级原则
1. 风险优先于收益，长期存活优先于短期收益。
2. 不确定性优先：事件、政策或潜在影响无法可靠判断时，不强行解释或交易。
3. 数据质量优先：关键数据缺失、异常、时间错位或存在未来数据泄漏时，不得正常产生依赖该数据的交易许可。
4. 宏观是背景和风险过滤器，不是单独买卖触发器；必须结合A股价格、成交、市场宽度和板块行为确认。
5. 所有评分、权重、阈值和风险比例均为待验证假设。
6. 硬性否决优先于评分；市场许可、个股许可和组合许可分层判断。

## 文档目录
- [01-system-overview-v1.0.md](01-system-overview-v1.0.md)：交易系统总纲。
- [02-uncertainty-risk-gate.md](02-uncertainty-risk-gate.md)：不确定性分级与风险否决。
- [03-market-regime-v1.1.md](03-market-regime-v1.1.md)：市场环境识别与择时规格。
- [04-sector-strength-rotation-v1.2.md](04-sector-strength-rotation-v1.2.md)：板块强度、主线识别与行业轮动基础规格。
- [05-leader-short-term-engine-v1.3.md](05-leader-short-term-engine-v1.3.md)：龙头短线引擎基础规格。
- [06-trend-swing-engine-v1.4.md](06-trend-swing-engine-v1.4.md)：趋势波段引擎、行业景气、公司质量、趋势与估值风险。
- [07-position-sizing-portfolio-risk-v1.5.md](07-position-sizing-portfolio-risk-v1.5.md)：仓位规模、组合暴露、流动性、熔断与执行约束。
- [08-executable-investment-framework-v1.6.md](08-executable-investment-framework-v1.6.md)：六步决策流程、每日操作清单及双引擎统一执行手册。
- [09-sentiment-cycle-model-v1.0.md](09-sentiment-cycle-model-v1.0.md)：情绪阶段、六维评分、统计口径、风险闸门与历史验证。
- [10-mainline-leader-identification-v1.0.md](10-mainline-leader-identification-v1.0.md)：主线确认、龙头身份分类、核心/跟风/补涨及失效规则。
- [11-entry-signal-model-v1.0.md](11-entry-signal-model-v1.0.md)：双引擎入场形态、假突破、失效条件、风险收益与交易清单。
- [12-unified-decision-state-machine-v1.0.md](12-unified-decision-state-machine-v1.0.md)：市场、个股、组合三级决策架构，状态转换、冲突处理与每日输出规范。
- [13-market-environment-indicator-dictionary-v1.0.md](13-market-environment-indicator-dictionary-v1.0.md)：第一批A股市场环境指标定义、数据源分级、时间治理、数据质量、特殊证券处理与重复计分控制。
- [14-market-breadth-model-v1.0.md](14-market-breadth-model-v1.0.md)：市场宽度四层结构、背离监控、双引擎适配与研究标签。
- [15-market-breadth-validation-v1.0.md](15-market-breadth-validation-v1.0.md)：市场宽度历史验证假设、Walk-forward设计、阈值校准和评价标准。
- [16-six-market-regimes-v1.0.md](16-six-market-regimes-v1.0.md)：A股六类市场状态、识别顺序、双引擎授权和状态转换原则。
- [17-market-regime-transition-conflict-v1.0.md](17-market-regime-transition-conflict-v1.0.md)：市场状态转换、证据冲突、滞回与置信度处理。
- [18-regime-engine-risk-budget-v1.0.md](18-regime-engine-risk-budget-v1.0.md)：市场状态、双引擎和组合三层风险预算联动。
- [19-dynamic-position-sizing-execution-v1.0.md](19-dynamic-position-sizing-execution-v1.0.md)：动态仓位、失效价格、分批建仓及A股执行约束。
- [20-execution-cost-liquidity-stress-v1.0.md](20-execution-cost-liquidity-stress-v1.0.md)：交易成本、成交真实性、流动性与极端压力测试。
- [21-dual-engine-backtest-validation-v1.0.md](21-dual-engine-backtest-validation-v1.0.md)：双引擎独立回测、Walk-forward、消融实验与准入标准。
- [22-leader-engine-backtest-v1.0.md](22-leader-engine-backtest-v1.0.md)：龙头短线四类形态、点时识别、退出和失败样本验证。\n- [23-trend-engine-backtest-v1.0.md](23-trend-engine-backtest-v1.0.md)：趋势波段行业景气、公司质量、四类形态、点时数据与历史回测准入规格。
- [24-portfolio-backtest-validation-v1.0.md](24-portfolio-backtest-validation-v1.0.md)：双引擎组合互补性、共同风险、资金冲突与组合样本外验证规格。
- [25-unified-data-architecture-backtest-foundation-v1.0.md](25-unified-data-architecture-backtest-foundation-v1.0.md)：统一数据层、点时治理、历史股票池、数据质量和回测复现架构。
- [CHANGELOG.md](CHANGELOG.md)：开发路线与版本记录。
- [conversation-log/](conversation-log/)：重要对话结论、用户决策、规则讨论和版本演进摘要；最新记录见0015。

## 对话与研究归档约定
持续归档重要用户判断、关键决策、逻辑分析、研究规则、公式、伪代码、待验证假设、反例和版本变更。采用结构化摘要，不承诺逐字备份全部聊天。公开仓库不存放账户凭证或个人敏感资料。

## 开发顺序
理论规格整合 → 统一指标字典与时间治理 → 数据质量验收 → 回测基础设施 → Walk-forward与样本外验证 → 模拟交易验收。理论规则稳定前不急于程序实现。

## 研究纪律
每项规则记录定义、公式、输入字段、观察周期、信号时间、可用时间、异常处理、参数来源、测试方法和失效条件。保留负面结果和被否定的假设。修改规则必须记录版本、理由和验证结果。

**状态声明：** 当前文档是研究讨论整理的规格初稿，不是已验证策略或可运行程序。仅供个人研究学习，不构成投资建议。

- [26-data-source-availability-quality-cost-v1.0.md](26-data-source-availability-quality-cost-v1.0.md)：免费优先的数据源、官方来源、质量验收与采购纪律。
- [conversation-log/0016-v1.0-free-first-data-sources.md](conversation-log/0016-v1.0-free-first-data-sources.md)：第26阶段免费优先数据源评估日志。

- [27-p0-free-data-sample-audit-v1.0.md](27-p0-free-data-sample-audit-v1.0.md)：P0免费数据同样本试采集设计、字段口径、质量验收与未完成事项。
- [conversation-log/0017-v1.0-p0-free-data-audit.md](conversation-log/0017-v1.0-p0-free-data-audit.md)：第27阶段试采集准备日志。

- P0采集程序以本目录GitHub文件为准：`p0_free_data_audit.py` V1.3及`requirements_p0_audit.txt`。部署前请阅读28号手册开头的【特别备注】。


## 第29阶段：P0采集程序部署前加固\n- [29-p0-audit-v1.3-hardening-and-audit-boundaries-v1.0.md](29-p0-audit-v1.3-hardening-and-audit-boundaries-v1.0.md)：Run ID隔离、旧文件污染防护、字段与重复日期检查、文件SHA-256及未解决事项。\n- [conversation-log/0019-v1.0-p0-audit-v1.3-hardening.md](conversation-log/0019-v1.0-p0-audit-v1.3-hardening.md)：第29阶段代码审查和部署决策。\n\n## 测试机部署与P0采集程序
- [28-p0-test-machine-deployment-and-acceptance-v1.0.md](28-p0-test-machine-deployment-and-acceptance-v1.0.md)：测试机部署、运行步骤、故障排查、质量验收清单与后续优化优先级。
- [conversation-log/0018-v1.0-test-machine-deployment.md](conversation-log/0018-v1.0-test-machine-deployment.md)：第28阶段脚本审查和部署决策。
- [p0_free_data_audit.py](p0_free_data_audit.py)：P0免费数据试采集脚本V1.3。
- [requirements_p0_audit.txt](requirements_p0_audit.txt)：P0采集脚本Python依赖。


> **测试机特别提醒：** 运行前准备Python 3.10–3.12、联网测试机和独立虚拟环境；运行后优先回传`manifest_and_results.json`、`comparison_summary.csv`、`data_quality_checks.csv`。不要上传密码、Cookie、代理凭证、`.venv`或未经授权的原始行情数据。具体清单见[28号部署手册](28-p0-test-machine-deployment-and-acceptance-v1.0.md)。

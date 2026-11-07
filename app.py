from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import date
import pandas as pd
import streamlit as st

from data.market_store import MarketStore
from services.market_sync import MarketSync

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "trading_journal.db"
STAGES = ["主升", "补涨", "退潮", "冷门", "观察"]
STAGE_MULTIPLIER = {"主升": 1.0, "补涨": 0.7, "退潮": 0.5, "冷门": 0.0, "观察": 0.5}
REQUIRED = ["sector", "ret3_pct", "ret5_pct", "rs3_pct", "rs5_pct", "amount_ratio", "close", "ma5"]


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
            entry REAL NOT NULL, stop REAL NOT NULL, target REAL,
            quantity INTEGER NOT NULL, planned_risk REAL NOT NULL,
            actual_pnl REAL, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def classify_raw(row):
    r3, r5 = float(row.rs3_pct), float(row.rs5_pct)
    ret5, amount = float(row.ret5_pct), float(row.amount_ratio)
    close, ma5 = float(row.close), float(row.ma5)
    cold = r5 <= -2.0 and ret5 <= 0 and amount <= 0.9
    retreat_flags = [
        r3 <= -1.0,
        amount <= 0.8,
        bool(getattr(row, "was_strong", False)) and float(row.ret3_pct) < 0,
        close < ma5,
    ]
    retreat = sum(retreat_flags) >= 2
    extreme = float(row.ret3_pct) < -3.0 and amount > 1.5
    if extreme:
        return "退潮", "极端放量下跌，触发当日强制退潮信号"
    if cold:
        return "冷门", "RS≤-2%、近5日不强且成交额持续低迷"
    if retreat:
        return "退潮", f"退潮条件满足 {sum(retreat_flags)} 项"
    main = ret5 > 0 and r5 >= 2.0 and r3 >= 1.0 and amount >= 1.2 and close >= ma5
    if main:
        return "主升", "主升五项条件全部满足（仍需连续两日确认）"
    rebound = ret5 > 0 and 0 <= r5 < 2.0 and amount >= 1.0
    if rebound:
        return "补涨", "近5日上涨、RS处于0%~2%、成交额不低于均值"
    return "观察", "未满足主升、补涨、退潮或冷门的完整条件"


def classify_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in REQUIRED[1:]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if out[REQUIRED].isna().any().any():
        raise ValueError("行情表存在空值或非数字字段，请检查必填列。")
    if (out["amount_ratio"] < 0).any():
        raise ValueError("成交额变化倍数不能为负数。")
    results = out.apply(classify_raw, axis=1, result_type="expand")
    out["初步阶段"] = results[0]
    out["判定依据"] = results[1]
    # Strict confirmation when a dated history is provided. Same sector's immediately
    # previous trading row must also satisfy the raw stage; otherwise show provisional.
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.sort_values(["sector", "date"])
        final = []
        for _, group in out.groupby("sector", sort=False):
            prev = None
            for _, row in group.iterrows():
                stage = row["初步阶段"]
                if stage == "主升" and prev != "主升":
                    stage = "观察"
                elif stage == "退潮" and prev not in ("退潮", "冷门") and "极端放量" not in row["判定依据"]:
                    stage = "观察"
                final.append((row.name, stage))
                prev = row["初步阶段"]
        stage_map = dict(final)
        out["最终阶段"] = out.index.map(stage_map)
        out["确认说明"] = out.apply(
            lambda r: "已连续确认/极端信号" if r["最终阶段"] == r["初步阶段"] else "首次触发，待下一交易日确认",
            axis=1,
        )
    else:
        out["最终阶段"] = out["初步阶段"]
        out["确认说明"] = "单日数据：仅为初步判定，无法验证连续两日确认"
    return out.sort_values("sector").reset_index(drop=True)


def calc_position(capital, risk_pct, entry, stop, cost_pct, multiplier, max_exposure_pct):
    if min(capital, risk_pct, entry, stop) <= 0:
        raise ValueError("资金、风险比例、入场价和止损价必须大于 0。")
    if entry == stop:
        raise ValueError("入场价不能等于止损价。")
    per_unit = abs(entry - stop) + entry * max(cost_pct, 0) / 100
    risk_budget = capital * risk_pct / 100
    raw_qty = int(risk_budget / per_unit)
    qty = int(raw_qty * max(0, multiplier))
    max_qty = int(capital * max_exposure_pct / 100 / entry)
    qty = min(qty, max_qty)
    invested = qty * entry
    planned_loss = qty * per_unit
    return {
        "risk_budget": risk_budget, "quantity": qty, "invested": invested,
        "exposure_pct": invested / capital * 100,
        "planned_loss": planned_loss, "risk_pct": planned_loss / capital * 100,
        "per_unit_risk": per_unit,
    }


def init_state():
    if "market_df" not in st.session_state:
        st.session_state.market_df = pd.DataFrame(columns=REQUIRED)


def main():
    st.set_page_config(page_title="个人交易系统", page_icon="📈", layout="wide")
    st.title("📈 个人交易系统 · 决策工作台")
    st.caption("v0.1 MVP｜规则计算、风险预算与交易日志。不是行情终端，不提供投资建议。")
    init_state()

    with st.sidebar:
        st.header("工作区")
        page = st.radio("功能", ["总览与板块轮动", "行情同步与自动分析", "共振检查", "仓位计算器", "交易日志", "数据格式说明"])
        st.divider()
        st.caption("数据默认保存在本机 SQLite；行情需由你导入或填写。")

    if page == "总览与板块轮动":
        st.subheader("板块轮动分析")
        st.info("导入每日板块指标 CSV，或在下方手工录入。单日数据只能给出初步阶段；连续确认必须提供带日期的历史记录。")
        upload = st.file_uploader("上传板块指标 CSV", type=["csv"])
        if upload is not None:
            try:
                incoming = pd.read_csv(upload)
                missing = [c for c in REQUIRED if c not in incoming.columns]
                if missing:
                    st.error("缺少字段：" + ", ".join(missing))
                else:
                    st.session_state.market_df = incoming
                    st.success(f"已载入 {len(incoming)} 行数据。")
            except Exception as exc:
                st.error(f"CSV 读取失败：{exc}")

        st.markdown("**手工录入（百分比字段请填数值，例如 1.5 表示 1.5%）**")
        with st.form("market_form"):
            c1, c2, c3, c4 = st.columns(4)
            sector = c1.text_input("板块名称", "半导体")
            ret3 = c2.number_input("近3日涨跌幅 %", value=1.0, step=0.1)
            ret5 = c3.number_input("近5日涨跌幅 %", value=3.0, step=0.1)
            rs3 = c4.number_input("近3日 RS %", value=1.2, step=0.1)
            c5, c6, c7, c8 = st.columns(4)
            rs5 = c5.number_input("近5日 RS %", value=2.2, step=0.1)
            amount = c6.number_input("成交额变化倍数", value=1.25, min_value=0.0, step=0.05)
            close = c7.number_input("最新收盘价", value=100.0, min_value=0.01)
            ma5 = c8.number_input("近5日均价", value=98.0, min_value=0.01)
            if st.form_submit_button("添加到本次分析"):
                new = pd.DataFrame([dict(sector=sector, ret3_pct=ret3, ret5_pct=ret5,
                    rs3_pct=rs3, rs5_pct=rs5, amount_ratio=amount, close=close, ma5=ma5)])
                st.session_state.market_df = pd.concat([st.session_state.market_df, new], ignore_index=True)
                st.rerun()

        df = st.session_state.market_df
        if not df.empty:
            try:
                analyzed = classify_table(df)
                st.dataframe(analyzed, use_container_width=True, hide_index=True)
                st.download_button("下载分析结果 CSV", analyzed.to_csv(index=False).encode("utf-8-sig"),
                                   "sector_rotation_result.csv", "text/csv")
                counts = analyzed["最终阶段"].value_counts()
                st.bar_chart(counts)
            except Exception as exc:
                st.error(str(exc))
            if st.button("清空本次行情数据"):
                st.session_state.market_df = pd.DataFrame(columns=REQUIRED)
                st.rerun()
        else:
            st.warning("尚未载入行情数据。")

    elif page == "行情同步与自动分析":
        st.subheader("AkShare 行业板块日线同步")
        st.info("按需手动触发一次历史行情同步。每日自动运行请配置操作系统计划任务，详见 README_APP.md。")
        market_db = APP_DIR / "market_data.sqlite3"
        st.caption(f"行情数据库：{market_db.name}")
        lookback = st.selectbox("回补自然日范围", [90, 180, 365], index=0)
        if st.button("立即同步行业板块与沪深300", type="primary"):
            try:
                with st.spinner("正在获取板块列表、沪深300及各行业历史日线；首次运行可能需要数分钟……"):
                    store = MarketStore(market_db)
                    result = MarketSync(store=store).run(lookback_days=int(lookback))
                st.success(f"同步完成：{result['sectors_ok']} 个板块成功，{result['sectors_failed']} 个失败。状态：{result['status']}")
                if result["errors"]:
                    st.warning("部分板块同步失败：")
                    st.code("\\n".join(result["errors"][:30]))
            except Exception as exc:
                st.error(f"行情同步失败：{type(exc).__name__}: {exc}")
        if market_db.exists():
            try:
                store = MarketStore(market_db)
                latest = store.latest_indicators()
                if not latest.empty:
                    st.markdown("**各板块最新指标与阶段**")
                    st.dataframe(latest, use_container_width=True, hide_index=True)
                    st.download_button("导出最新板块分析 CSV", latest.to_csv(index=False).encode("utf-8-sig"),
                                       "latest_sector_analysis.csv", "text/csv")
                else:
                    st.info("数据库已初始化，尚无可展示的指标。请先运行同步。")
                run = store.latest_run()
                if run:
                    st.caption(f"最近任务：{run[1]}｜状态：{run[3]}｜成功 {run[5]} / 失败 {run[6]}")
            except Exception as exc:
                st.warning(f"读取行情数据库失败：{exc}")

    elif page == "共振检查":
        st.subheader("四项共振检查")
        st.caption("遵循 v2.3 手册：四项中至少两项支持，才进入入场 Checklist。")
        a, b = st.columns(2)
        trend = a.selectbox("国内趋势状态", ["支持", "中性", "冲突"])
        flow = b.selectbox("主力资金方向", ["支持", "中性", "冲突"])
        model = a.selectbox("模型推荐板块匹配", ["支持", "中性", "冲突"])
        external = b.selectbox("外部风向标", ["支持", "中性", "严重冲突"])
        support = sum(x == "支持" for x in [trend, flow, model, external])
        conflict = sum(x in ("冲突", "严重冲突") for x in [trend, flow, model, external])
        st.metric("支持项数量", f"{support} / 4")
        if support >= 2:
            st.success("共振通过：可以进入入场 Checklist（不代表自动产生买卖信号）。")
        else:
            st.error("共振未通过：按系统规则暂不进入入场 Checklist。")
        st.write({"支持项": support, "冲突项": conflict, "四项结果": [trend, flow, model, external]})
        st.divider()
        st.markdown("**入场 Checklist**")
        checks = [
            "市场状态符合当前策略", "共振检查通过", "处于模型入场时间窗口",
            "板块阶段为主升或补涨", "价格结构已确认", "风险回报比达到设定阈值",
            "总风险敞口未超限", "情绪状态稳定", "止损与仓位已计算", "外部市场无重大冲突",
        ]
        passed = [st.checkbox(x, key=f"check_{i}") for i, x in enumerate(checks)]
        if all(passed):
            st.success("Checklist 全部通过。请人工复核数据来源与订单风险。")
        else:
            st.warning(f"尚有 {len(passed) - sum(passed)} 项未通过，按规则不应开仓。")

    elif page == "仓位计算器":
        st.subheader("仓位与风险预算")
        st.warning("计算结果是计划风险估算，不保证实际最大亏损；跳空、流动性、涨跌停、滑点可能扩大损失。")
        c1, c2, c3 = st.columns(3)
        capital = c1.number_input("账户总资金", min_value=1.0, value=1_000_000.0, step=10_000.0)
        risk_pct = c2.number_input("单笔风险上限 %", min_value=0.01, max_value=10.0, value=1.0, step=0.1)
        exposure = c3.number_input("单标的最大资金占比 %", min_value=1.0, max_value=100.0, value=30.0, step=1.0)
        c4, c5, c6 = st.columns(3)
        entry = c4.number_input("计划入场价", min_value=0.01, value=50.0, step=0.1)
        stop = c5.number_input("止损价", min_value=0.001, value=47.0, step=0.1)
        cost = c6.number_input("往返成本估计 %（含滑点）", min_value=0.0, value=0.2, step=0.05)
        stage = st.selectbox("板块阶段", STAGES, index=0)
        confidence = st.selectbox("模型信心系数", ["高（1.0）", "中（0.7）", "低（0.4）"])
        confidence_mult = {"高（1.0）": 1.0, "中（0.7）": 0.7, "低（0.4）": 0.4}[confidence]
        external_mult = st.selectbox("外部市场调整系数", [1.0, 0.7, 0.5], format_func=lambda x: str(x))
        mult = STAGE_MULTIPLIER[stage] * confidence_mult * external_mult
        try:
            result = calc_position(capital, risk_pct, entry, stop, cost, mult, exposure)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("建议数量（股/份）", f"{result['quantity']:,}")
            k2.metric("预计投入资金", f"{result['invested']:,.2f}")
            k3.metric("资金占比", f"{result['exposure_pct']:.2f}%")
            k4.metric("估算计划亏损", f"{result['planned_loss']:,.2f}")
            st.write(f"风险预算：{result['risk_budget']:,.2f}；估算风险占净值：{result['risk_pct']:.3f}%；每单位风险：{result['per_unit_risk']:.4f}")
            if result["quantity"] == 0:
                st.error("当前阶段或风险参数导致建议数量为 0。")
        except Exception as exc:
            st.error(str(exc))

    elif page == "交易日志":
        st.subheader("交易记录")
        with st.form("trade_form"):
            c1, c2, c3 = st.columns(3)
            trade_date = c1.date_input("交易日期", value=date.today())
            symbol = c2.text_input("标的代码/名称")
            side = c3.selectbox("方向", ["多", "空"])
            c4, c5, c6 = st.columns(3)
            entry = c4.number_input("入场价", min_value=0.001, value=10.0)
            stop = c5.number_input("止损价", min_value=0.001, value=9.5)
            target = c6.number_input("目标价（可选，0 表示不填）", min_value=0.0, value=0.0)
            c7, c8 = st.columns(2)
            qty = c7.number_input("数量", min_value=1, value=100, step=100)
            planned_risk = c8.number_input("计划风险金额", min_value=0.0, value=50.0)
            pnl = st.number_input("实际盈亏（未平仓可填 0）", value=0.0)
            notes = st.text_area("交易理由 / 复盘")
            submitted = st.form_submit_button("保存交易")
            if submitted:
                if not symbol.strip() or entry == stop:
                    st.error("请填写标的，且入场价不能等于止损价。")
                else:
                    with db() as conn:
                        conn.execute("""INSERT INTO trades
                            (trade_date,symbol,side,entry,stop,target,quantity,planned_risk,actual_pnl,notes)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (str(trade_date), symbol.strip(), side, entry, stop,
                             target or None, int(qty), planned_risk, pnl, notes))
                    st.success("交易记录已保存到本机数据库。")
        with db() as conn:
            history = pd.read_sql_query("SELECT * FROM trades ORDER BY trade_date DESC, id DESC", conn)
        if not history.empty:
            st.dataframe(history, use_container_width=True, hide_index=True)
            st.download_button("导出交易日志 CSV", history.to_csv(index=False).encode("utf-8-sig"),
                               "trading_journal.csv", "text/csv")
            st.metric("已记录交易笔数", len(history))
        else:
            st.info("还没有交易记录。")

    else:
        st.subheader("数据格式说明")
        st.markdown("""
上传 CSV 必须包含以下列名（英文列名，百分比填数值而不是小数）：

| 字段 | 含义 | 示例 |
|---|---|---:|
| sector | 板块名称 | 半导体 |
| ret3_pct | 板块近3日涨跌幅（%） | 1.5 |
| ret5_pct | 板块近5日涨跌幅（%） | 3.2 |
| rs3_pct | 近3日相对沪深300强度（百分点） | 1.1 |
| rs5_pct | 近5日相对沪深300强度（百分点） | 2.3 |
| amount_ratio | 近3日日均成交额 / 近10日日均成交额 | 1.25 |
| close | 最新收盘价 | 100 |
| ma5 | 近5日均价 | 98 |

可选列：date（交易日期，YYYY-MM-DD）。若提供日期，程序按板块时间序列检查连续确认；请上传足够的历史交易日数据，而不是仅上传最新一天。

注意：当前 MVP 不连接行情供应商、不自动抓取资金流/PCR/海外数据、不下单。所有外部数据需人工核验后输入。建议先用模拟数据和历史数据验证，不要直接用于实盘。
        """)
        st.code("pip install -r requirements.txt\nstreamlit run app.py", language="bash")


if __name__ == "__main__":
    main()

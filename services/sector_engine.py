"""Calculate sector momentum, relative strength, turnover expansion and stage labels."""
from __future__ import annotations

import pandas as pd


def _pct_change(series: pd.Series, periods: int):
    return (series / series.shift(periods) - 1.0) * 100.0


def calculate_indicators(sector_history: pd.DataFrame, benchmark_history: pd.DataFrame,
                         sector: str) -> pd.DataFrame:
    if sector_history.empty or benchmark_history.empty:
        return pd.DataFrame()

    s = sector_history.copy()
    b = benchmark_history[["date", "close"]].copy()
    s["date"] = pd.to_datetime(s["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    b["date"] = pd.to_datetime(b["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    s = s.dropna(subset=["date"])
    b = b.dropna(subset=["date"])
    s = s.sort_values("date")
    b = b.sort_values("date")

    # Keep the benchmark calendar as the canonical session sequence. Missing sector
    # sessions remain explicit rows so stage confirmation cannot jump over a gap.
    merged = b.rename(columns={"close": "benchmark_close"}).merge(
        s, on="date", how="left", validate="one_to_one"
    )
    for col in ("close", "amount", "benchmark_close"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    merged.loc[merged["close"] <= 0, "close"] = float("nan")
    merged.loc[merged["benchmark_close"] <= 0, "benchmark_close"] = float("nan")

    merged["ret3_pct"] = _pct_change(merged["close"], 3)
    merged["ret5_pct"] = _pct_change(merged["close"], 5)
    merged["benchmark_ret3_pct"] = _pct_change(merged["benchmark_close"], 3)
    merged["benchmark_ret5_pct"] = _pct_change(merged["benchmark_close"], 5)
    merged["rs3_pct"] = merged["ret3_pct"] - merged["benchmark_ret3_pct"]
    merged["rs5_pct"] = merged["ret5_pct"] - merged["benchmark_ret5_pct"]
    merged["ma5"] = merged["close"].rolling(5, min_periods=5).mean()
    amount3 = merged["amount"].rolling(3, min_periods=3).mean()
    amount10 = merged["amount"].rolling(10, min_periods=10).mean()
    merged["amount_ratio"] = amount3 / amount10.where(amount10 > 0)
    merged["sector"] = sector

    # Discard only the common indicator warm-up. Do not drop later rows with missing
    # sector observations: classify_indicators uses them to reset confirmation state.
    return merged.iloc[9:].reset_index(drop=True)


def classify_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply v2.3 thresholds and require consecutive valid trading-session observations."""
    if frame.empty:
        return frame.copy()
    out = frame.sort_values(["sector", "date"]).copy()
    initial, reasons = [], []
    previous_raw_by_sector = {}
    required = ("ret3_pct", "ret5_pct", "rs3_pct", "rs5_pct",
                "amount_ratio", "close", "ma5")
    for row in out.itertuples(index=False):
        if any(pd.isna(getattr(row, field)) for field in required):
            initial.append("数据缺失")
            reasons.append("该交易日板块行情缺失或指标窗口不完整，连续确认已重置")
            previous_raw_by_sector[row.sector] = None
            continue
        previous_raw = previous_raw_by_sector.get(row.sector)
        cold = row.rs5_pct <= -2.0 and row.ret5_pct <= 0 and row.amount_ratio <= 0.9
        retreat_flags = [row.rs3_pct <= -1.0, row.amount_ratio <= 0.8,
                         previous_raw in ("主升", "补涨") and row.ret3_pct < 0,
                         row.close < row.ma5]
        extreme = row.ret3_pct < -3.0 and row.amount_ratio > 1.5
        if extreme:
            stage, reason = "退潮", "极端放量下跌，触发当日强制退潮信号"
        elif cold:
            stage, reason = "冷门", "RS≤-2%、近5日不强且成交额持续低迷"
        elif sum(retreat_flags) >= 2:
            stage, reason = "退潮", f"退潮条件满足 {sum(retreat_flags)} 项"
        elif (row.ret5_pct > 0 and row.rs5_pct >= 2.0 and row.rs3_pct >= 1.0
              and row.amount_ratio >= 1.2 and row.close >= row.ma5):
            stage, reason = "主升", "主升五项条件全部满足"
        elif row.ret5_pct > 0 and 0 <= row.rs5_pct < 2.0 and row.amount_ratio >= 1.0:
            stage, reason = "补涨", "近5日上涨、RS处于0%~2%、成交额不低于均值"
        else:
            stage, reason = "观察", "未满足主升、补涨、退潮或冷门的完整条件"
        initial.append(stage)
        reasons.append(reason)
        previous_raw_by_sector[row.sector] = stage
    out["初步阶段"] = initial
    out["判定依据"] = reasons
    final = []
    for _, group in out.groupby("sector", sort=False):
        previous = None
        for row in group.itertuples():
            stage = row.初步阶段
            if stage == "数据缺失":
                final.append((row.Index, stage))
                previous = None
                continue
            if stage in ("主升", "退潮") and previous != stage and "极端放量" not in row.判定依据:
                stage = "观察"
            final.append((row.Index, stage))
            previous = row.初步阶段
    stage_map = dict(final)
    out["最终阶段"] = [stage_map[i] for i in out.index]
    return out.reset_index(drop=True)

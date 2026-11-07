"""Historical portfolio risk analytics from user-supplied CSV snapshots."""
from __future__ import annotations

import math
import pandas as pd


def _dated_frame(frame: pd.DataFrame, value_name: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError("历史数据不能为空。")
    if "date" not in frame.columns:
        raise ValueError("历史数据必须包含 date 日期列。")
    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    if data["date"].isna().any():
        raise ValueError("date 包含无法识别的日期。")
    if data["date"].duplicated().any():
        raise ValueError("同一日期存在重复记录，请先合并。")
    data = data.sort_values("date").set_index("date")
    if data.empty:
        raise ValueError("没有可用的历史记录。")
    return data


def analyze_return_correlation(
    prices: pd.DataFrame,
    min_observations: int = 3,
) -> dict:
    """Calculate daily return correlations from a date + one-column-per-symbol price CSV."""
    if not isinstance(min_observations, int) or min_observations < 2:
        raise ValueError("min_observations 至少为 2。")
    data = _dated_frame(prices, "price")
    symbols = [column for column in data.columns]
    if len(symbols) < 2:
        raise ValueError("价格数据至少需要两个标的列。")
    for symbol in symbols:
        data[symbol] = pd.to_numeric(data[symbol], errors="coerce")
        values = data[symbol].dropna().to_numpy(dtype=float)
        if not all(math.isfinite(float(value)) and value > 0 for value in values):
            raise ValueError(f"{symbol} 价格必须是有限正数。")
    returns = data.pct_change(fill_method=None)
    correlation = returns.corr(min_periods=min_observations)
    counts = returns.notna().astype(int).T.dot(returns.notna().astype(int))
    return {
        "returns": returns,
        "correlation": correlation,
        "observation_counts": counts,
        "symbols": symbols,
        "min_observations": min_observations,
    }


def analyze_drawdown(
    nav_history: pd.DataFrame,
    warning_drawdown_pct: float = 10.0,
) -> dict:
    """Calculate drawdown against the historical running peak of a NAV series."""
    if not math.isfinite(float(warning_drawdown_pct)) or not 0 < warning_drawdown_pct <= 100:
        raise ValueError("回撤预警阈值必须大于 0 且不超过 100%。")
    data = _dated_frame(nav_history, "nav")
    if "nav" not in data.columns:
        raise ValueError("净值数据必须包含 nav 列。")
    nav = pd.to_numeric(data["nav"], errors="coerce")
    values = nav.dropna().to_numpy(dtype=float)
    if len(values) != len(nav) or not all(math.isfinite(float(v)) and v > 0 for v in values):
        raise ValueError("nav 必须全部为有限正数。")
    if len(nav) < 2:
        raise ValueError("至少需要两个净值观察点才能计算回撤。")
    peak = nav.cummax()
    drawdown = (nav / peak - 1.0) * 100.0
    max_drawdown_pct = float(drawdown.min())
    current_drawdown_pct = float(drawdown.iloc[-1])
    peak_date = nav.index[int(nav.to_numpy().argmax())]
    alerts = []
    if abs(current_drawdown_pct) >= warning_drawdown_pct:
        alerts.append(
            f"当前回撤 {abs(current_drawdown_pct):.2f}% 达到/超过预警阈值 {warning_drawdown_pct:.2f}%。"
        )
    return {
        "history": pd.DataFrame({
            "nav": nav,
            "running_peak": peak,
            "drawdown_pct": drawdown,
        }),
        "max_drawdown_pct": max_drawdown_pct,
        "current_drawdown_pct": current_drawdown_pct,
        "peak_nav": float(peak.max()),
        "latest_nav": float(nav.iloc[-1]),
        "peak_date": peak_date,
        "alerts": alerts,
        "warning_drawdown_pct": float(warning_drawdown_pct),
    }

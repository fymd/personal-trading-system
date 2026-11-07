"""Portfolio analytics: drawdown, return correlation and risk contribution."""

from __future__ import annotations

import math
from datetime import date

import pandas as pd


def _finite_positive(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("{} must be a finite positive number.".format(label))
    if not math.isfinite(number) or number <= 0:
        raise ValueError("{} must be a finite positive number.".format(label))
    return number


def analyze_drawdown(equity_curve):
    """Calculate peak-to-trough drawdowns from date/equity observations.

    Returns a dict with the sorted curve, maximum/current drawdown and peak/trough
    dates. Drawdown values are positive percentages (e.g. 12 means -12%).
    """
    required = {"date", "equity"}
    if not isinstance(equity_curve, pd.DataFrame):
        equity_curve = pd.DataFrame(equity_curve)
    missing = required.difference(equity_curve.columns)
    if missing:
        raise ValueError("Missing equity curve fields: {}".format(", ".join(sorted(missing))))
    frame = equity_curve[["date", "equity"]].copy()
    if frame.empty:
        raise ValueError("Equity curve must contain at least one observation.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["equity"] = pd.to_numeric(frame["equity"], errors="coerce")
    if frame["date"].isna().any():
        raise ValueError("Equity curve contains invalid dates.")
    values = frame["equity"].astype(float).tolist()
    if any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("Equity values must be finite and greater than zero.")
    if frame["date"].duplicated().any():
        raise ValueError("Equity curve dates must be unique.")
    frame = frame.sort_values("date").reset_index(drop=True)
    frame["peak_equity"] = frame["equity"].cummax()
    frame["drawdown_pct"] = (1 - frame["equity"] / frame["peak_equity"]) * 100
    trough_idx = int(frame["drawdown_pct"].idxmax())
    peak_equity = float(frame.loc[trough_idx, "peak_equity"])
    peak_candidates = frame.loc[:trough_idx]
    peak_idx = int(peak_candidates.loc[peak_candidates["equity"] == peak_equity].index[-1])
    max_dd = float(frame.loc[trough_idx, "drawdown_pct"])
    current_dd = float(frame.iloc[-1]["drawdown_pct"])
    return {
        "curve": frame,
        "max_drawdown_pct": max_dd,
        "current_drawdown_pct": current_dd,
        "peak_date": frame.loc[peak_idx, "date"].date().isoformat(),
        "trough_date": frame.loc[trough_idx, "date"].date().isoformat(),
        "latest_date": frame.iloc[-1]["date"].date().isoformat(),
        "latest_equity": float(frame.iloc[-1]["equity"]),
    }


def analyze_return_correlations(returns, min_periods=20, warning_threshold=0.80):
    """Calculate pairwise Pearson correlations from daily returns, not prices."""
    if not isinstance(returns, pd.DataFrame):
        returns = pd.DataFrame(returns)
    if "date" not in returns.columns:
        raise ValueError("Returns data must include a date column.")
    frame = returns.copy()
    if frame.empty:
        raise ValueError("Returns data must contain at least one observation.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    if frame["date"].isna().any():
        raise ValueError("Returns data contains invalid dates.")
    if frame["date"].duplicated().any():
        raise ValueError("Returns data dates must be unique.")
    frame = frame.sort_values("date").drop(columns=["date"]).reset_index(drop=True)
    if len(frame.columns) < 2:
        raise ValueError("At least two symbol return columns are required.")
    if len(set(map(str, frame.columns))) != len(frame.columns):
        raise ValueError("Return columns must have unique symbol names.")
    try:
        min_periods = int(min_periods)
    except (TypeError, ValueError):
        raise ValueError("min_periods must be an integer of at least 2.")
    if min_periods < 2:
        raise ValueError("min_periods must be an integer of at least 2.")
    try:
        threshold = float(warning_threshold)
    except (TypeError, ValueError):
        raise ValueError("warning_threshold must be between -1 and 1.")
    if not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise ValueError("warning_threshold must be between -1 and 1.")
    for column in frame.columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame[column] = frame[column].replace([float("inf"), float("-inf")], float("nan"))
    correlation = frame.corr(method="pearson", min_periods=min_periods)
    counts = frame.notna().astype(int).T.dot(frame.notna().astype(int))
    pairs = []
    symbols = list(frame.columns)
    for i, left in enumerate(symbols):
        for right in symbols[i + 1:]:
            value = correlation.loc[left, right]
            n = int(counts.loc[left, right])
            if pd.notna(value):
                pairs.append({
                    "symbol_a": str(left), "symbol_b": str(right),
                    "correlation": float(value), "observations": n,
                    "high_correlation": bool(value >= threshold),
                })
    pairs.sort(key=lambda item: item["correlation"], reverse=True)
    return {
        "correlation": correlation,
        "observations": counts,
        "pairs": pd.DataFrame(pairs, columns=[
            "symbol_a", "symbol_b", "correlation", "observations", "high_correlation"
        ]),
        "warning_threshold": threshold,
        "warnings": [
            "{} / {} correlation {:.2f} ({} observations)".format(
                p["symbol_a"], p["symbol_b"], p["correlation"], p["observations"]
            )
            for p in pairs if p["high_correlation"]
        ],
    }


def analyze_sector_risk_contribution(positions):
    """Aggregate stop-risk contribution by sector."""
    if not isinstance(positions, pd.DataFrame):
        positions = pd.DataFrame(positions)
    required = {"sector", "risk_amount"}
    missing = required.difference(positions.columns)
    if missing:
        raise ValueError("Missing position fields: {}".format(", ".join(sorted(missing))))
    frame = positions[["sector", "risk_amount"]].copy()
    frame["sector"] = frame["sector"].astype("string").str.strip()
    frame["risk_amount"] = pd.to_numeric(frame["risk_amount"], errors="coerce")
    if frame.empty or frame["sector"].isna().any() or frame["sector"].eq("").any():
        raise ValueError("Positions must contain non-empty sector values.")
    values = frame["risk_amount"].astype(float).tolist()
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("risk_amount values must be finite and non-negative.")
    result = frame.groupby("sector", as_index=False)["risk_amount"].sum()
    total = float(result["risk_amount"].sum())
    result["risk_contribution_pct"] = (
        result["risk_amount"] / total * 100 if total > 0 else 0.0
    )
    return result.sort_values("risk_amount", ascending=False).reset_index(drop=True)


def build_daily_risk_report(portfolio_report, drawdown_report=None,
                            correlation_report=None, report_date=None,
                            sector_risk=None):
    """Build a serializable end-of-day risk snapshot from calculated analyses."""
    report_date = report_date or date.today().isoformat()
    if not isinstance(report_date, str) or pd.isna(pd.to_datetime(report_date, errors="coerce")):
        raise ValueError("report_date must be a valid date string.")
    alerts = list(portfolio_report.get("alerts", []))
    if drawdown_report and drawdown_report.get("max_drawdown_pct", 0) > 0:
        alerts.append("Historical maximum drawdown: {:.2f}%".format(
            drawdown_report["max_drawdown_pct"]
        ))
    if correlation_report:
        alerts.extend(correlation_report.get("warnings", []))
    return {
        "date": report_date,
        "total_market_value": float(portfolio_report.get("total_market_value", 0)),
        "gross_exposure_pct": float(portfolio_report.get("gross_exposure_pct", 0)),
        "total_risk": float(portfolio_report.get("total_risk", 0)),
        "total_risk_pct": float(portfolio_report.get("total_risk_pct", 0)),
        "max_drawdown_pct": (
            float(drawdown_report["max_drawdown_pct"]) if drawdown_report else None
        ),
        "current_drawdown_pct": (
            float(drawdown_report["current_drawdown_pct"]) if drawdown_report else None
        ),
        "high_correlation_pairs": (
            int(correlation_report["pairs"]["high_correlation"].sum())
            if correlation_report and not correlation_report["pairs"].empty else 0
        ),
        "sector_risk": (
            sector_risk.to_dict(orient="records")
            if isinstance(sector_risk, pd.DataFrame) else (sector_risk or [])
        ),
        "alerts": alerts,
    }

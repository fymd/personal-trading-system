"""Portfolio-level exposure and stop-risk controls.

Inputs are user-supplied position snapshots; this module does not connect to a broker.
"""
from __future__ import annotations

import math
import pandas as pd

REQUIRED_COLUMNS = ["symbol", "sector", "market_value", "risk_amount"]


def analyze_portfolio(
    positions: pd.DataFrame,
    capital: float,
    max_total_risk_pct: float = 3.0,
    max_gross_exposure_pct: float = 100.0,
    max_sector_exposure_pct: float = 35.0,
    max_symbol_exposure_pct: float = 20.0,
) -> dict:
    """Aggregate position market values and stop-risk, then report limit breaches.

    risk_amount must represent estimated loss at the position's stop, in account
    currency, and should include estimated fees/slippage where possible.
    """
    limits = {
        "max_total_risk_pct": max_total_risk_pct,
        "max_gross_exposure_pct": max_gross_exposure_pct,
        "max_sector_exposure_pct": max_sector_exposure_pct,
        "max_symbol_exposure_pct": max_symbol_exposure_pct,
    }
    if not math.isfinite(float(capital)) or capital <= 0:
        raise ValueError("账户净值必须为有限正数。")
    for name, value in limits.items():
        if not math.isfinite(float(value)) or not 0 < value <= 500:
            raise ValueError(f"{name} 必须是大于 0 且不超过 500 的有限数值。")
    if positions is None or positions.empty:
        raise ValueError("请至少提供一条持仓记录。")
    missing = [column for column in REQUIRED_COLUMNS if column not in positions.columns]
    if missing:
        raise ValueError("持仓数据缺少字段：" + ", ".join(missing))

    data = positions[REQUIRED_COLUMNS].copy()
    for column in ("symbol", "sector"):
        data[column] = data[column].astype("string").str.strip()
        if data[column].isna().any() or data[column].eq("").any():
            raise ValueError("标的代码和所属行业不能为空。")
    for column in ("market_value", "risk_amount"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
        values = data[column].to_numpy(dtype=float)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError(f"{column} 必须为有限数值。")
        if (data[column] < 0).any():
            raise ValueError(f"{column} 不能为负数。")

    total_market_value = float(data["market_value"].sum())
    total_risk = float(data["risk_amount"].sum())
    gross_exposure_pct = total_market_value / capital * 100
    total_risk_pct = total_risk / capital * 100

    sector = (
        data.groupby("sector", as_index=False)["market_value"].sum()
        .sort_values("market_value", ascending=False)
    )
    sector["exposure_pct"] = sector["market_value"] / capital * 100
    sector["limit_pct"] = float(max_sector_exposure_pct)
    sector["status"] = sector["exposure_pct"].apply(
        lambda value: "超限" if value > max_sector_exposure_pct else "正常"
    )

    symbol = (
        data.groupby("symbol", as_index=False)["market_value"].sum()
        .sort_values("market_value", ascending=False)
    )
    symbol["exposure_pct"] = symbol["market_value"] / capital * 100
    symbol["limit_pct"] = float(max_symbol_exposure_pct)
    symbol["status"] = symbol["exposure_pct"].apply(
        lambda value: "超限" if value > max_symbol_exposure_pct else "正常"
    )

    alerts = []
    if total_risk_pct > max_total_risk_pct:
        alerts.append(
            f"组合止损风险 {total_risk_pct:.2f}% 超过上限 {max_total_risk_pct:.2f}%。"
        )
    if gross_exposure_pct > max_gross_exposure_pct:
        alerts.append(
            f"组合总仓位 {gross_exposure_pct:.2f}% 超过上限 {max_gross_exposure_pct:.2f}%。"
        )
    for row in sector[sector["status"] == "超限"].itertuples():
        alerts.append(
            f"行业集中度超限：{row.sector} 占净值 {row.exposure_pct:.2f}%，"
            f"上限 {max_sector_exposure_pct:.2f}%。"
        )
    for row in symbol[symbol["status"] == "超限"].itertuples():
        alerts.append(
            f"单标的集中度超限：{row.symbol} 占净值 {row.exposure_pct:.2f}%，"
            f"上限 {max_symbol_exposure_pct:.2f}%。"
        )

    return {
        "capital": float(capital),
        "total_market_value": total_market_value,
        "gross_exposure_pct": gross_exposure_pct,
        "total_risk": total_risk,
        "total_risk_pct": total_risk_pct,
        "sector_exposure": sector.reset_index(drop=True),
        "symbol_exposure": symbol.reset_index(drop=True),
        "alerts": alerts,
        "within_limits": not alerts,
    }

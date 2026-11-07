import pandas as pd
import pytest

from services.portfolio_risk import analyze_portfolio


def sample_positions():
    return pd.DataFrame([
        {"symbol": "ETF-A", "sector": "半导体", "market_value": 150_000, "risk_amount": 7_500},
        {"symbol": "STOCK-A", "sector": "半导体", "market_value": 80_000, "risk_amount": 5_200},
        {"symbol": "ETF-B", "sector": "宽基指数", "market_value": 180_000, "risk_amount": 3_600},
    ])


def test_portfolio_aggregates_risk_and_exposure():
    report = analyze_portfolio(sample_positions(), 1_000_000)

    assert report["total_market_value"] == 410_000
    assert report["gross_exposure_pct"] == pytest.approx(41.0)
    assert report["total_risk"] == 16_300
    assert report["total_risk_pct"] == pytest.approx(1.63)
    assert report["within_limits"] is True
    sector = report["sector_exposure"].set_index("sector")
    assert sector.loc["半导体", "exposure_pct"] == pytest.approx(23.0)


def test_portfolio_reports_total_risk_gross_and_concentration_breaches():
    report = analyze_portfolio(
        sample_positions(),
        1_000_000,
        max_total_risk_pct=1.0,
        max_gross_exposure_pct=30.0,
        max_sector_exposure_pct=20.0,
        max_symbol_exposure_pct=10.0,
    )

    assert report["within_limits"] is False
    assert any("组合止损风险" in alert for alert in report["alerts"])
    assert any("组合总仓位" in alert for alert in report["alerts"])
    assert any("行业集中度超限" in alert for alert in report["alerts"])
    assert any("单标的集中度超限" in alert for alert in report["alerts"])


def test_duplicate_symbol_rows_are_aggregated_for_symbol_concentration():
    positions = pd.DataFrame([
        {"symbol": "ETF-A", "sector": "科技", "market_value": 70_000, "risk_amount": 1_000},
        {"symbol": "ETF-A", "sector": "科技", "market_value": 60_000, "risk_amount": 1_000},
    ])
    report = analyze_portfolio(positions, 1_000_000, max_symbol_exposure_pct=10.0)
    row = report["symbol_exposure"].iloc[0]
    assert row["market_value"] == 130_000
    assert row["status"] == "超限"


@pytest.mark.parametrize("bad_value", [-1, float("inf"), "not-a-number"])
def test_invalid_position_values_are_rejected(bad_value):
    positions = sample_positions()
    positions.loc[0, "risk_amount"] = bad_value
    with pytest.raises(ValueError):
        analyze_portfolio(positions, 1_000_000)


def test_missing_columns_and_invalid_capital_are_rejected():
    with pytest.raises(ValueError, match="缺少字段"):
        analyze_portfolio(pd.DataFrame([{"symbol": "A"}]), 1_000_000)
    with pytest.raises(ValueError, match="账户净值"):
        analyze_portfolio(sample_positions(), 0)

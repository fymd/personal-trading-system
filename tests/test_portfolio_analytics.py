import pandas as pd
import pytest

from services.portfolio_analytics import (
    analyze_drawdown,
    analyze_return_correlations,
    analyze_sector_risk_contribution,
    build_daily_risk_report,
)


def test_drawdown_sorts_dates_and_finds_peak_trough_and_current():
    result = analyze_drawdown(pd.DataFrame([
        {"date": "2024-01-03", "equity": 90},
        {"date": "2024-01-01", "equity": 100},
        {"date": "2024-01-02", "equity": 80},
    ]))
    assert result["max_drawdown_pct"] == pytest.approx(20)
    assert result["current_drawdown_pct"] == pytest.approx(10)
    assert result["peak_date"] == "2024-01-01"
    assert result["trough_date"] == "2024-01-02"
    assert list(result["curve"]["equity"]) == [100, 80, 90]


@pytest.mark.parametrize("rows", [
    [{"date": "bad", "equity": 100}],
    [{"date": "2024-01-01", "equity": 0}],
    [{"date": "2024-01-01", "equity": float("inf")}],
    [{"date": "2024-01-01", "equity": 100},
     {"date": "2024-01-01", "equity": 101}],
    [],
])
def test_drawdown_rejects_invalid_input(rows):
    with pytest.raises(ValueError):
        analyze_drawdown(pd.DataFrame(rows, columns=["date", "equity"]))


def test_correlation_uses_pairwise_valid_observations_and_flags_high_pairs():
    returns = pd.DataFrame({
        "A": [i / 1000 for i in range(25)],
        "B": [i / 500 for i in range(25)],
        "C": [(-1) ** i / 100 for i in range(25)],
    })
    result = analyze_return_correlations(returns, min_periods=20)
    pair = result["pairs"].query("symbol_a == 'A' and symbol_b == 'B'").iloc[0]
    assert pair["correlation"] == pytest.approx(1.0)
    assert pair["observations"] == 25
    assert bool(pair["high_correlation"])
    assert len(result["warnings"]) >= 1


def test_correlation_skips_insufficient_and_constant_series():
    result = analyze_return_correlations(pd.DataFrame({
        "A": [1, 1, 1, 1], "B": [2, 3, 4, 5], "C": [1, None, None, None]
    }), min_periods=3)
    assert result["pairs"].empty


def test_correlation_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        analyze_return_correlations(pd.DataFrame({"A": [1], "B": [2]}), min_periods=1)


def test_sector_risk_contribution_aggregates_and_handles_zero_total():
    result = analyze_sector_risk_contribution(pd.DataFrame([
        {"sector": "Tech", "risk_amount": 20},
        {"sector": " Tech ", "risk_amount": 30},
        {"sector": "Banks", "risk_amount": 50},
    ]))
    tech = result.set_index("sector").loc["Tech"]
    assert tech["risk_amount"] == 50
    assert tech["risk_contribution_pct"] == pytest.approx(50)
    zero = analyze_sector_risk_contribution(pd.DataFrame([
        {"sector": "Tech", "risk_amount": 0}
    ]))
    assert zero.iloc[0]["risk_contribution_pct"] == 0


def test_sector_risk_rejects_negative_and_missing_sector():
    with pytest.raises(ValueError):
        analyze_sector_risk_contribution(pd.DataFrame([
            {"sector": "Tech", "risk_amount": -1}
        ]))
    with pytest.raises(ValueError):
        analyze_sector_risk_contribution(pd.DataFrame([
            {"sector": "", "risk_amount": 1}
        ]))


def test_daily_report_combines_metrics_and_alerts():
    portfolio = {
        "total_market_value": 1000, "gross_exposure_pct": 50,
        "total_risk": 20, "total_risk_pct": 2, "alerts": ["risk limit"],
    }
    dd = {"max_drawdown_pct": 10, "current_drawdown_pct": 3}
    corr = {"pairs": pd.DataFrame([{"high_correlation": True}]),
            "warnings": ["A / B high correlation"]}
    report = build_daily_risk_report(portfolio, dd, corr, "2024-01-02",
                                     [{"sector": "Tech", "risk_contribution_pct": 100}])
    assert report["max_drawdown_pct"] == 10
    assert report["high_correlation_pairs"] == 1
    assert len(report["alerts"]) == 3

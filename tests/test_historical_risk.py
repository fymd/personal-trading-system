import pandas as pd
import pytest

from services.historical_risk import analyze_return_correlation, analyze_drawdown


def test_correlation_uses_daily_returns_and_pairwise_observations():
    prices = pd.DataFrame({
        "date": ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"],
        "ETF_A": [100, 101, 99, 102, 103],
        "ETF_B": [50, 50.5, 49.5, 51, 51.5],
    })
    report = analyze_return_correlation(prices, min_observations=3)

    assert report["correlation"].loc["ETF_A", "ETF_B"] == pytest.approx(1.0)
    assert report["observation_counts"].loc["ETF_A", "ETF_B"] == 4


def test_correlation_marks_insufficient_common_history_as_nan():
    prices = pd.DataFrame({
        "date": ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"],
        "ETF_A": [100, 101, 102, 103],
        "ETF_B": [None, 50, None, 52],
    })
    report = analyze_return_correlation(prices, min_observations=3)
    assert pd.isna(report["correlation"].loc["ETF_A", "ETF_B"])


def test_correlation_rejects_duplicate_dates_and_nonpositive_prices():
    duplicate_dates = pd.DataFrame({
        "date": ["2026-01-05", "2026-01-05"],
        "ETF_A": [100, 101], "ETF_B": [50, 51],
    })
    with pytest.raises(ValueError, match="重复"):
        analyze_return_correlation(duplicate_dates)

    invalid_prices = pd.DataFrame({
        "date": ["2026-01-05", "2026-01-06"],
        "ETF_A": [100, 0], "ETF_B": [50, 51],
    })
    with pytest.raises(ValueError, match="正数"):
        analyze_return_correlation(invalid_prices)


def test_drawdown_calculates_peak_to_trough_and_current_drawdown():
    nav = pd.DataFrame({
        "date": ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"],
        "nav": [100, 110, 99, 104.5],
    })
    report = analyze_drawdown(nav, warning_drawdown_pct=8)

    assert report["max_drawdown_pct"] == pytest.approx(-10.0)
    assert report["current_drawdown_pct"] == pytest.approx(-5.0)
    assert report["peak_nav"] == pytest.approx(110)
    assert report["alerts"] == []


def test_drawdown_alerts_when_current_drawdown_reaches_threshold():
    nav = pd.DataFrame({
        "date": ["2026-01-05", "2026-01-06", "2026-01-07"],
        "nav": [100, 120, 108],
    })
    report = analyze_drawdown(nav, warning_drawdown_pct=10)
    assert report["current_drawdown_pct"] == pytest.approx(-10)
    assert len(report["alerts"]) == 1


def test_drawdown_rejects_invalid_nav_and_insufficient_history():
    with pytest.raises(ValueError, match="正数"):
        analyze_drawdown(pd.DataFrame({
            "date": ["2026-01-05", "2026-01-06"], "nav": [100, 0],
        }))
    with pytest.raises(ValueError, match="两个"):
        analyze_drawdown(pd.DataFrame({
            "date": ["2026-01-05"], "nav": [100],
        }))

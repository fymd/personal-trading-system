import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("trading_app", Path(__file__).parents[1] / "app.py")
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


def test_position_calculation_respects_risk_and_exposure_caps():
    result = app.calc_position(1_000_000, 1.0, 50, 47, 0.2, 0.7, 30)
    assert result["quantity"] == 2257
    assert result["planned_loss"] <= 10_000
    assert result["exposure_pct"] <= 30


def test_zero_multiplier_means_no_position():
    result = app.calc_position(1_000_000, 1.0, 50, 47, 0.2, 0.0, 30)
    assert result["quantity"] == 0


def test_invalid_equal_entry_and_stop_is_rejected():
    try:
        app.calc_position(100_000, 1.0, 10, 10, 0.1, 1.0, 20)
    except ValueError:
        return
    raise AssertionError("Expected ValueError")


def test_short_position_requires_stop_above_entry():
    result = app.calc_position(100_000, 1.0, 50, 53, 0.2, 1.0, 30, "空")
    assert result["quantity"] > 0
    try:
        app.calc_position(100_000, 1.0, 50, 47, 0.2, 1.0, 30, "空")
    except ValueError:
        return
    raise AssertionError("Expected short stop validation")


def test_position_rejects_out_of_range_multiplier_and_cost():
    for args in [
        (100_000, 1.0, 50, 47, 0.2, 1.5, 30),
        (100_000, 1.0, 50, 47, -0.1, 1.0, 30),
        (100_000, 1.0, 50, 47, 0.2, 1.0, 120),
    ]:
        try:
            app.calc_position(*args)
        except ValueError:
            continue
        raise AssertionError("Expected invalid position parameters to be rejected")


def test_market_data_rejects_duplicate_dates_and_invalid_prices():
    import pandas as pd

    base = {
        "sector": ["半导体", "半导体"],
        "ret3_pct": [1.0, 1.0], "ret5_pct": [2.0, 2.0],
        "rs3_pct": [1.0, 1.0], "rs5_pct": [2.0, 2.0],
        "amount_ratio": [1.2, 1.2], "close": [100.0, 101.0],
        "ma5": [99.0, 100.0], "date": ["2026-01-01", "2026-01-01"],
    }
    try:
        app.classify_table(pd.DataFrame(base))
    except ValueError as exc:
        assert "重复交易日期" in str(exc)
    else:
        raise AssertionError("Expected duplicate date validation")

    base["date"] = ["2026-01-01", "2026-01-02"]
    base["close"] = [100.0, float("inf")]
    try:
        app.classify_table(pd.DataFrame(base))
    except ValueError as exc:
        assert "有限数值" in str(exc)
    else:
        raise AssertionError("Expected non-finite market data validation")


def _main_stage_row(sector, day):
    return {
        "sector": sector, "ret3_pct": 1.5, "ret5_pct": 3.0,
        "rs3_pct": 1.2, "rs5_pct": 2.5, "amount_ratio": 1.3,
        "close": 105.0, "ma5": 100.0, "date": day,
    }


def test_main_stage_confirms_on_adjacent_dataset_sessions():
    import pandas as pd

    result = app.classify_table(pd.DataFrame([
        _main_stage_row("半导体", "2026-01-05"),
        _main_stage_row("半导体", "2026-01-06"),
    ]))
    latest = result[result["date"] == pd.Timestamp("2026-01-06")].iloc[0]
    assert latest["初步阶段"] == "主升"
    assert latest["最终阶段"] == "主升"
    assert latest["确认说明"] == "已连续确认/极端信号"


def test_main_stage_does_not_confirm_when_sector_skips_a_session():
    import pandas as pd

    bank = _main_stage_row("银行", "2026-01-06")
    bank.update({
        "ret3_pct": 0.1, "ret5_pct": 0.1, "rs3_pct": 0.1,
        "rs5_pct": 0.1, "amount_ratio": 1.0,
    })
    result = app.classify_table(pd.DataFrame([
        _main_stage_row("半导体", "2026-01-05"),
        bank,
        _main_stage_row("半导体", "2026-01-07"),
    ]))
    latest = result[
        (result["sector"] == "半导体")
        & (result["date"] == pd.Timestamp("2026-01-07"))
    ].iloc[0]
    assert latest["初步阶段"] == "主升"
    assert latest["最终阶段"] == "观察"
    assert "缺少上一交易日" in latest["确认说明"]

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("trading_app", Path(__file__).parents[1] / "app.py")
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


def test_position_calculation_respects_risk_and_exposure_caps():
    result = app.calc_position(1_000_000, 1.0, 50, 47, 0.2, 0.7, 30)
    assert result["quantity"] == 2258
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

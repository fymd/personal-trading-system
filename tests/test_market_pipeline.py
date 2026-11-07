import pandas as pd

from data.market_store import MarketStore
from services.sector_engine import calculate_indicators, classify_indicators


def test_store_upserts_are_idempotent(tmp_path):
    store = MarketStore(tmp_path / "market.sqlite3")
    bars = pd.DataFrame([{"date": "2026-01-02", "close": 101.0, "amount": 1000.0}])
    store.upsert_sector_bars("测试行业", bars)
    store.upsert_sector_bars("测试行业", bars.assign(close=102.0))
    loaded = store.load_sector_history("测试行业")
    assert len(loaded) == 1
    assert loaded.iloc[0]["close"] == 102.0


def test_indicators_align_on_common_trading_dates():
    dates = pd.bdate_range("2026-01-01", periods=15).strftime("%Y-%m-%d")
    sector = pd.DataFrame({"date": dates, "close": [100+i for i in range(15)],
                           "amount": [1000.0]*15})
    benchmark = pd.DataFrame({"date": dates, "close": [100+i*0.5 for i in range(15)]})
    result = calculate_indicators(sector, benchmark, "测试行业")
    assert len(result) == 6
    assert result.iloc[-1]["ret3_pct"] > result.iloc[-1]["benchmark_ret3_pct"]
    assert result.iloc[-1]["rs3_pct"] > 0
    assert result.iloc[-1]["amount_ratio"] == 1.0


def test_missing_sector_session_does_not_compress_trading_day_windows():
    dates = pd.bdate_range("2026-01-01", periods=35).strftime("%Y-%m-%d")
    closes = [100.0 + i for i in range(35)]
    sector = pd.DataFrame({"date": dates, "close": closes, "amount": [1000.0] * 35})
    benchmark = pd.DataFrame({"date": dates, "close": [100.0 + i * 0.5 for i in range(35)]})
    missing_date = dates[22]
    sector = sector.drop(index=22).reset_index(drop=True)

    result = calculate_indicators(sector, benchmark, "测试行业")
    missing = result[result["date"] == missing_date].iloc[0]
    assert pd.isna(missing["close"])
    assert pd.isna(missing["ret3_pct"])
    assert len(result) == 35 - 9


def test_missing_sector_session_resets_consecutive_stage_confirmation():
    rows = []
    for day, stage_data in [
        ("2026-01-01", True),
        ("2026-01-02", True),
        ("2026-01-05", False),
        ("2026-01-06", True),
        ("2026-01-07", True),
    ]:
        values = {"sector": "测试行业", "date": day}
        if stage_data:
            values.update({"ret3_pct": 2, "ret5_pct": 3, "rs3_pct": 1.5,
                           "rs5_pct": 2.5, "amount_ratio": 1.3, "close": 105, "ma5": 100})
        else:
            values.update({"ret3_pct": float("nan"), "ret5_pct": float("nan"),
                           "rs3_pct": float("nan"), "rs5_pct": float("nan"),
                           "amount_ratio": float("nan"), "close": float("nan"),
                           "ma5": float("nan")})
        rows.append(values)

    out = classify_indicators(pd.DataFrame(rows))
    assert out["初步阶段"].tolist() == ["主升", "主升", "数据缺失", "主升", "主升"]
    assert out["最终阶段"].tolist() == ["观察", "主升", "数据缺失", "观察", "主升"]


def test_classification_marks_first_main_stage_as_observation():
    rows = pd.DataFrame([
        {"sector":"测试行业","date":"2026-01-01","ret3_pct":2,"ret5_pct":3,
         "rs3_pct":1.5,"rs5_pct":2.5,"amount_ratio":1.3,"close":105,"ma5":100},
        {"sector":"测试行业","date":"2026-01-02","ret3_pct":2,"ret5_pct":3,
         "rs3_pct":1.5,"rs5_pct":2.5,"amount_ratio":1.3,"close":106,"ma5":101},
    ])
    out = classify_indicators(rows)
    assert out["初步阶段"].tolist() == ["主升", "主升"]
    assert out["最终阶段"].tolist() == ["观察", "主升"]

import pandas as pd
import pytest

from data.akshare_provider import AkShareProvider


class FakeAkShare:
    def stock_board_industry_name_em(self):
        return pd.DataFrame([{"板块名称": "银行", "板块代码": "BK0475"}])

    def stock_board_industry_hist_em(self, **kwargs):
        assert kwargs["period"] == "日k"
        return pd.DataFrame([
            {"日期": "2026-11-06", "收盘": "1200", "成交额": "1000000"}
        ])

    def stock_zh_index_daily_em(self, **kwargs):
        assert kwargs["symbol"] == "csi000300"
        return pd.DataFrame([
            {"date": "2026-11-06", "close": "4500.5", "amount": "250000000"}
        ])


class BrokenPrimaryWithFallback:
    def stock_zh_index_daily_em(self, **kwargs):
        raise TypeError("'NoneType' object is not subscriptable")

    def index_zh_a_hist(self, **kwargs):
        assert kwargs == {
            "symbol": "000300",
            "period": "daily",
            "start_date": "20261101",
            "end_date": "20261107",
        }
        return pd.DataFrame([
            {"日期": "2026-11-06", "收盘": "4501.25", "成交金额": "123456789"}
        ])


class EmptyPrimaryWithFallback:
    def stock_zh_index_daily_em(self, **kwargs):
        return pd.DataFrame()

    def index_zh_a_hist(self, **kwargs):
        return pd.DataFrame([
            {"日期": "2026-11-06", "收盘": "4502.0", "成交额": "1000"}
        ])


def test_provider_normalizes_chinese_industry_history():
    provider = AkShareProvider(FakeAkShare())
    sectors = provider.industry_list()
    history = provider.industry_history("银行", "20261101", "20261107")

    assert sectors.loc[0, "sector"] == "银行"
    assert history.loc[0, "date"] == "2026-11-06"
    assert history.loc[0, "close"] == 1200.0
    assert history.loc[0, "amount"] == 1_000_000.0


def test_provider_normalizes_english_benchmark_history():
    provider = AkShareProvider(FakeAkShare())
    history = provider.benchmark_history("20261101", "20261107")

    assert history.loc[0, "date"] == "2026-11-06"
    assert history.loc[0, "close"] == 4500.5
    assert history.loc[0, "amount"] == 250_000_000.0


def test_benchmark_falls_back_when_eastmoney_endpoint_raises():
    provider = AkShareProvider(BrokenPrimaryWithFallback(), retry_attempts=1)
    history = provider.benchmark_history("20261101", "20261107")

    assert history.loc[0, "date"] == "2026-11-06"
    assert history.loc[0, "close"] == 4501.25
    assert history.loc[0, "amount"] == 123_456_789.0


def test_benchmark_falls_back_when_primary_endpoint_is_empty():
    provider = AkShareProvider(EmptyPrimaryWithFallback(), retry_attempts=1)
    history = provider.benchmark_history("20261101", "20261107")

    assert history.loc[0, "close"] == 4502.0


def test_benchmark_fails_loudly_when_both_endpoints_are_unavailable():
    class NoBenchmark:
        def stock_zh_index_daily_em(self, **kwargs):
            raise TypeError("upstream null payload")

        def index_zh_a_hist(self, **kwargs):
            return pd.DataFrame()

    provider = AkShareProvider(NoBenchmark(), retry_attempts=1)
    with pytest.raises(RuntimeError, match="both stock_zh_index_daily_em and index_zh_a_hist failed"):
        provider.benchmark_history("20261101", "20261107")

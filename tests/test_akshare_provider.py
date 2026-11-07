import pandas as pd

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

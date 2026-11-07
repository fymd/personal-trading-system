"""Idempotent daily market-data synchronization orchestration."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable

import pandas as pd

from data.akshare_provider import AkShareProvider
from data.market_store import MarketStore
from services.sector_engine import calculate_indicators, classify_indicators


class MarketSync:
    def __init__(self, provider=None, store=None, benchmark_symbol="csi000300",
                 today: Callable[[], date] = date.today):
        self.provider = provider or AkShareProvider()
        self.store = store or MarketStore("market_data.sqlite3")
        self.benchmark_symbol = benchmark_symbol
        self.today = today

    def run(self, lookback_days: int = 90) -> dict:
        end = self.today()
        start = end - timedelta(days=lookback_days)
        start_text, end_text = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
        started = datetime.now().isoformat(timespec="seconds")
        sectors = self.provider.industry_list()
        if sectors.empty or "sector" not in sectors.columns:
            raise ValueError("AKShare 未返回有效行业板块列表，停止分析以避免生成空结果")
        run_id = self.store.start_run(started, len(sectors))
        errors, ok = [], 0
        try:
            benchmark = self.provider.benchmark_history(start_text, end_text, self.benchmark_symbol)
            if benchmark.empty or len(benchmark) < 11:
                raise ValueError("沪深300基准行情不足 11 个交易日，无法计算 10 日成交额均值")
            self.store.upsert_benchmark(self.benchmark_symbol, benchmark)
            for sector in sectors["sector"].tolist():
                try:
                    history = self.provider.industry_history(sector, start_text, end_text)
                    if history.empty:
                        raise ValueError("接口返回空行情")
                    self.store.upsert_sector_bars(sector, history)
                    all_history = self.store.load_sector_history(sector)
                    base_history = self.store.load_benchmark_history(self.benchmark_symbol)
                    indicators = calculate_indicators(all_history, base_history, sector)
                    if indicators.empty:
                        raise ValueError("有效重叠行情不足以计算指标（至少需要 11 个交易日）")
                    classified = classify_indicators(indicators)
                    self.store.save_indicators(classified)
                    ok += 1
                except Exception as exc:
                    errors.append(f"{sector}: {type(exc).__name__}: {exc}")
            failed = len(errors)
            status = "success" if failed == 0 else ("partial" if ok else "failed")
            self.store.finish_run(run_id, datetime.now().isoformat(timespec="seconds"),
                                  status, ok, failed, errors)
            return {"run_id": run_id, "status": status, "sectors_total": len(sectors),
                    "sectors_ok": ok, "sectors_failed": failed, "errors": errors,
                    "indicators": self.store.latest_indicators()}
        except Exception as exc:
            self.store.finish_run(run_id, datetime.now().isoformat(timespec="seconds"),
                                  "failed", ok, len(sectors) - ok,
                                  errors + [f"pipeline: {type(exc).__name__}: {exc}"])
            raise

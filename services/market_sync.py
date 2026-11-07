"""Idempotent daily market-data synchronization orchestration."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable
import logging
import time

import pandas as pd

from data.akshare_provider import AkShareProvider
from data.market_store import MarketStore
from services.sector_engine import calculate_indicators, classify_indicators

logger = logging.getLogger(__name__)


class MarketSync:
    def __init__(self, provider=None, store=None, benchmark_symbol="csi000300",
                 today: Callable[[], date] = date.today):
        self.provider = provider or AkShareProvider()
        self.store = store or MarketStore("market_data.sqlite3")
        self.benchmark_symbol = benchmark_symbol
        self.today = today

    def run(self, lookback_days: int = 90) -> dict:
        if not isinstance(lookback_days, int) or isinstance(lookback_days, bool) or lookback_days < 20:
            raise ValueError("lookback_days must be an integer of at least 20")

        end = self.today()
        start = end - timedelta(days=lookback_days)
        start_text, end_text = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
        started = datetime.now().isoformat(timespec="seconds")
        logger.info("Market sync started", extra={"status": "running"})

        # Create the audit record before any upstream request so even a failed
        # industry-list or benchmark request is recorded as a completed failure.
        run_id = self.store.start_run(started, 0)
        sectors = []
        errors = []
        ok = 0
        try:
            sector_frame = self.provider.industry_list()
            if sector_frame.empty or "sector" not in sector_frame.columns:
                raise ValueError("AKShare 未返回有效行业板块列表，停止分析以避免生成空结果")
            sectors = sector_frame["sector"].dropna().astype(str).tolist()
            self.store.set_run_total(run_id, len(sectors))

            benchmark = self.provider.benchmark_history(start_text, end_text, self.benchmark_symbol)
            if benchmark.empty or len(benchmark) < 11:
                raise ValueError("沪深300基准行情不足 11 个交易日，无法计算 10 日成交额均值")
            self.store.upsert_benchmark(self.benchmark_symbol, benchmark)

            for sector in sectors:
                sector_started = time.monotonic()
                try:
                    history = self.provider.industry_history(sector, start_text, end_text)
                    if history.empty:
                        raise ValueError("接口返回空行情")
                    self.store.upsert_sector_bars(sector, history)
                    all_history = self.store.load_sector_history(sector)
                    base_history = self.store.load_benchmark_history(self.benchmark_symbol)
                    indicators = calculate_indicators(all_history, base_history, sector)
                    if indicators.empty or indicators.dropna(
                        subset=["ret3_pct", "ret5_pct", "rs3_pct", "rs5_pct", "ma5", "amount_ratio"]
                    ).empty:
                        raise ValueError("有效重叠行情不足以计算指标（至少需要 10 个连续有效交易日）")
                    classified = classify_indicators(indicators)
                    self.store.save_indicators(classified)
                    latest = classified.iloc[-1]
                    if latest["最终阶段"] == "数据缺失":
                        raise ValueError(
                            f"最新基准交易日 {latest['date']} 缺少有效板块行情或指标窗口不完整"
                        )
                    ok += 1
                    logger.info(
                        "Sector synchronized",
                        extra={"sector": sector, "status": "success",
                               "elapsed_ms": round((time.monotonic() - sector_started) * 1000)},
                    )
                except Exception as exc:
                    errors.append(f"{sector}: {type(exc).__name__}: {exc}")
                    logger.exception(
                        "Sector synchronization failed",
                        extra={"sector": sector, "status": "failed",
                               "elapsed_ms": round((time.monotonic() - sector_started) * 1000)},
                    )

            failed = len(sectors) - ok
            status = "success" if failed == 0 else ("partial" if ok else "failed")
            self.store.finish_run(
                run_id, datetime.now().isoformat(timespec="seconds"),
                status, ok, failed, errors,
            )
            logger.info("Market sync finished", extra={"run_id": run_id, "status": status})
            return {
                "run_id": run_id, "status": status, "sectors_total": len(sectors),
                "sectors_ok": ok, "sectors_failed": failed, "errors": errors,
                "indicators": self.store.latest_indicators(),
            }
        except Exception as exc:
            logger.exception(
                "Market sync pipeline failed",
                extra={"run_id": run_id, "status": "failed"},
            )
            errors.append(f"pipeline: {type(exc).__name__}: {exc}")
            self.store.finish_run(
                run_id, datetime.now().isoformat(timespec="seconds"),
                "failed", ok, max(len(sectors) - ok, 0), errors,
            )
            raise

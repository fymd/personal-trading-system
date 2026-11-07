"""AKShare adapter: normalize provider-specific frames into stable internal schemas."""
from __future__ import annotations

import logging
import os

import pandas as pd

from services.reliability import retry_call

logger = logging.getLogger(__name__)


class AkShareProvider:
    def __init__(self, ak_module=None, retry_attempts: int | None = None):
        if ak_module is None:
            try:
                import akshare as ak_module
            except ImportError as exc:
                raise RuntimeError("AKShare 未安装，请先执行 pip install -r requirements.txt") from exc
        self.ak = ak_module
        self.retry_attempts = retry_attempts or int(os.getenv('AKSHARE_RETRY_ATTEMPTS', '3'))

    def _request(self, operation, action):
        retryable = (ConnectionError, TimeoutError, OSError)
        try:
            import requests
            retryable = retryable + (requests.exceptions.RequestException,)
        except ImportError:
            pass
        return retry_call(operation, action, attempts=self.retry_attempts, logger=logger,
                          retry_exceptions=retryable)

    @staticmethod
    def _rename(frame: pd.DataFrame, mapping: dict[str, str], required: tuple[str, ...]) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame(columns=list(required))
        out = frame.rename(columns=mapping).copy()
        missing = [name for name in required if name not in out.columns]
        if missing:
            raise ValueError(f"AKShare 返回字段不符合预期，缺少: {', '.join(missing)}")
        return out

    def industry_list(self) -> pd.DataFrame:
        raw = self._request('AKShare industry list', self.ak.stock_board_industry_name_em)
        out = self._rename(
            raw,
            {"板块名称": "sector", "板块代码": "sector_code", "代码": "sector_code",
             "name": "sector", "code": "sector_code", "最新价": "close",
             "close": "close", "涨跌幅": "pct_change", "pct_change": "pct_change",
             "成交额": "amount", "amount": "amount"},
            ("sector",),
        )
        out["sector"] = out["sector"].astype(str).str.strip()
        out = out[out["sector"].ne("")].drop_duplicates("sector")
        return out.reset_index(drop=True)

    def industry_history(self, sector: str, start_date: str, end_date: str) -> pd.DataFrame:
        raw = self._request(
            f"AKShare industry history: {sector}",
            lambda: self.ak.stock_board_industry_hist_em(
                symbol=sector, period="日k", start_date=start_date,
                end_date=end_date, adjust=""
            ),
        )
        out = self._rename(
            raw,
            {"日期": "date", "date": "date", "开盘": "open", "open": "open",
             "收盘": "close", "close": "close", "最高": "high", "high": "high",
             "最低": "low", "low": "low", "成交量": "volume", "volume": "volume",
             "成交额": "amount", "amount": "amount", "涨跌幅": "pct_change",
             "pct_change": "pct_change"},
            ("date", "close", "amount"),
        )
        return self._clean_history(out)

    def benchmark_history(self, start_date: str, end_date: str, symbol: str = "csi000300") -> pd.DataFrame:
        """Load CSI 300 history, falling back to AKShare's generic index-history API."""
        primary_error = None
        try:
            raw = self._request(
                f"AKShare benchmark history: {symbol}",
                lambda: self.ak.stock_zh_index_daily_em(
                    symbol=symbol, start_date=start_date, end_date=end_date
                ),
            )
            out = self._normalize_benchmark(raw)
            if not out.empty:
                return out
            logger.warning("Primary benchmark endpoint returned no rows; trying generic index history")
        except Exception as exc:
            primary_error = exc
            logger.warning(
                "Primary benchmark endpoint failed (%s); trying generic index history",
                exc, exc_info=True,
            )

        fallback = getattr(self.ak, "index_zh_a_hist", None)
        if fallback is None:
            raise RuntimeError(
                "CSI 300 benchmark unavailable: primary endpoint failed and "
                "AKShare index_zh_a_hist fallback is not available"
            ) from primary_error

        try:
            raw = self._request(
                "AKShare CSI 300 fallback history",
                lambda: fallback(
                    symbol="000300", period="daily",
                    start_date=start_date, end_date=end_date,
                ),
            )
            out = self._normalize_benchmark(raw)
            if out.empty:
                raise RuntimeError("AKShare index_zh_a_hist returned no CSI 300 rows")
            logger.info("Loaded CSI 300 benchmark through index_zh_a_hist fallback")
            return out
        except Exception as fallback_error:
            raise RuntimeError(
                "CSI 300 benchmark unavailable: both stock_zh_index_daily_em "
                f"and index_zh_a_hist failed; fallback error: {fallback_error}"
            ) from fallback_error

    @classmethod
    def _normalize_benchmark(cls, raw: pd.DataFrame) -> pd.DataFrame:
        out = cls._rename(
            raw,
            {"日期": "date", "date": "date", "收盘": "close", "close": "close",
             "成交额": "amount", "成交金额": "amount", "amount": "amount"},
            ("date", "close"),
        )
        if "amount" not in out.columns:
            out["amount"] = None
        return cls._clean_history(out)

    @staticmethod
    def _clean_history(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        for col in ("open", "close", "high", "low", "volume", "amount", "pct_change"):
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        out = out.dropna(subset=["date", "close"])
        out = out[out["close"] > 0].drop_duplicates("date", keep="last")
        return out.sort_values("date").reset_index(drop=True)

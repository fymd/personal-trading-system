"""Small live connectivity check for the two AKShare data endpoints used by the app."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.akshare_provider import AkShareProvider


def retry(label, action, attempts=3):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt * 3)
    raise RuntimeError(f"{label} failed after {attempts} attempts: {last_error}") from last_error


def main():
    end = date.today()
    start = end - timedelta(days=60)
    start_text, end_text = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    provider = AkShareProvider()
    sectors = retry("industry list", provider.industry_list)
    if sectors.empty:
        raise RuntimeError("AKShare returned an empty industry list")
    sector = str(sectors.iloc[0]["sector"])
    sector_bars = retry(
        f"industry history ({sector})",
        lambda: provider.industry_history(sector, start_text, end_text),
    )
    benchmark = retry(
        "CSI 300 history",
        lambda: provider.benchmark_history(start_text, end_text, "csi000300"),
    )
    if sector_bars.empty:
        raise RuntimeError(f"No daily bars returned for industry: {sector}")
    if len(benchmark) < 11:
        raise RuntimeError(f"CSI 300 history too short: {len(benchmark)} rows")
    print(f"Industry list: {len(sectors)} sectors")
    print(f"Sample industry: {sector}, {len(sector_bars)} daily rows")
    print(f"CSI 300: {len(benchmark)} daily rows")
    print(f"Latest industry date: {sector_bars.iloc[-1]['date']}")
    print(f"Latest CSI 300 date: {benchmark.iloc[-1]['date']}")


if __name__ == "__main__":
    main()

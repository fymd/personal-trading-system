"""CLI entry point intended for Windows Task Scheduler / cron after market close."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from data.market_store import MarketStore
from services.market_sync import MarketSync
from services.reliability import configure_logging
import logging


def main():
    parser = argparse.ArgumentParser(description="Sync daily sector and CSI 300 market data")
    parser.add_argument("--db", default="market_data.sqlite3", help="SQLite database path")
    parser.add_argument("--lookback-days", type=int, default=90)
    parser.add_argument("--benchmark", default="csi000300")
    parser.add_argument('--log-dir', default='logs', help='Directory for rotating JSONL logs')
    args = parser.parse_args()
    configure_logging(args.log_dir)
    logger = logging.getLogger(__name__)
    if args.lookback_days < 20:
        parser.error("--lookback-days 至少为 20，以覆盖滚动指标窗口和节假日")
    store = MarketStore(Path(args.db))
    logger.info('Daily market job started')
    try:
        result = MarketSync(store=store, benchmark_symbol=args.benchmark).run(args.lookback_days)
    except Exception:
        logger.exception('Daily market job terminated with an error')
        raise
    print(json.dumps({k: v for k, v in result.items() if k != "indicators"},
                     ensure_ascii=False, indent=2))
    if result["status"] != "success":
        logger.error('Daily market job completed with status %s', result['status'])
        raise SystemExit(1)
    logger.info('Daily market job completed successfully')


if __name__ == "__main__":
    main()

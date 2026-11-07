"""Data freshness checks and optional webhook alert delivery."""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def check_data_freshness(store, benchmark_symbol: str, *, today: date | None = None,
                         max_age_days: int = 5) -> dict:
    """Compare latest stored benchmark session with calendar-day freshness threshold."""
    today = today or date.today()
    frame = store.load_benchmark_history(benchmark_symbol)
    if frame.empty:
        return {"status": "stale", "latest_trade_date": None, "age_days": None,
                "message": "基准行情为空，无法确认数据新鲜度"}
    latest = date.fromisoformat(str(frame.iloc[-1]["date"])[:10])
    age = (today - latest).days
    status = "fresh" if 0 <= age <= max_age_days else "stale"
    message = (f"最新基准交易日 {latest.isoformat()}，距今天历日 {age} 天"
               if status == "fresh" else
               f"基准行情可能过期：最新交易日 {latest.isoformat()}，距今天历日 {age} 天")
    return {"status": status, "latest_trade_date": latest.isoformat(),
            "age_days": age, "message": message}


def send_webhook_alert(message: str, *, url: str | None = None,
                       timeout: float = 8.0) -> bool:
    """Send a generic JSON text payload to a configured webhook endpoint."""
    endpoint = url or os.getenv("TRADING_ALERT_WEBHOOK_URL")
    if not endpoint:
        logger.info("Alert webhook not configured; alert remains in job output")
        return False
    payload = json.dumps({"text": message}, ensure_ascii=False).encode("utf-8")
    request = Request(endpoint, data=payload,
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"Webhook returned HTTP {response.status}")
        logger.info("Alert webhook delivered")
        return True
    except Exception:
        logger.exception("Alert webhook delivery failed")
        return False


def build_alert_message(result: dict, freshness: dict) -> str:
    return (
        "个人交易系统：每日行情同步告警\n"
        f"同步状态：{result.get('status')}\n"
        f"板块成功：{result.get('sectors_ok', 0)} / {result.get('sectors_total', 0)}\n"
        f"板块失败：{result.get('sectors_failed', 0)}\n"
        f"数据新鲜度：{freshness.get('status')}（{freshness.get('message')}）\n"
        f"运行编号：{result.get('run_id')}\n"
        f"错误摘要：{'；'.join(result.get('errors', []))[:1500]}"
    )

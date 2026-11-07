from datetime import date

import pandas as pd

from services.monitoring import build_alert_message, check_data_freshness


class FakeStore:
    def __init__(self, dates):
        self.dates = dates

    def load_benchmark_history(self, symbol):
        return pd.DataFrame({"date": self.dates, "close": [100.0] * len(self.dates)})


def test_freshness_accepts_recent_latest_benchmark_session():
    result = check_data_freshness(
        FakeStore(["2026-11-03", "2026-11-06"]), "csi000300",
        today=date(2026, 11, 7), max_age_days=5,
    )
    assert result["status"] == "fresh"
    assert result["latest_trade_date"] == "2026-11-06"
    assert result["age_days"] == 1


def test_freshness_flags_old_or_empty_benchmark_data():
    stale = check_data_freshness(
        FakeStore(["2026-10-20"]), "csi000300",
        today=date(2026, 11, 7), max_age_days=5,
    )
    empty = check_data_freshness(
        FakeStore([]), "csi000300", today=date(2026, 11, 7),
    )
    assert stale["status"] == "stale"
    assert empty["status"] == "stale"
    assert empty["latest_trade_date"] is None


def test_alert_message_contains_run_and_freshness_status():
    message = build_alert_message(
        {"status": "partial", "run_id": 42, "sectors_ok": 8,
         "sectors_total": 10, "sectors_failed": 2, "errors": ["板块A: timeout"]},
        {"status": "stale", "message": "latest data too old"},
    )
    assert "42" in message
    assert "partial" in message
    assert "stale" in message
    assert "板块A" in message



def test_webhook_sends_json_payload_when_configured(monkeypatch):
    import json
    from services import monitoring

    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"errcode":0,"errmsg":"ok"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(monitoring, "urlopen", fake_urlopen)
    assert monitoring.send_webhook_alert("test alert", url="https://example.invalid/hook")
    assert captured["url"] == "https://example.invalid/hook"
    assert captured["body"] == {
        "msgtype": "text",
        "text": {"content": "test alert"},
    }
    assert captured["timeout"] == 8.0


def test_webhook_without_configuration_is_not_sent(monkeypatch):
    from services import monitoring

    monkeypatch.delenv("TRADING_ALERT_WEBHOOK_URL", raising=False)
    assert monitoring.send_webhook_alert("test alert") is False



def test_wecom_webhook_api_error_is_reported(monkeypatch):
    from services import monitoring

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"errcode":93000,"errmsg":"invalid webhook"}'

    monkeypatch.setattr(monitoring, "urlopen", lambda request, timeout: FakeResponse())
    assert monitoring.send_webhook_alert("test alert", url="https://example.invalid/hook") is False

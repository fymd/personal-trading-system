import logging

import pytest

from services.reliability import retry_call


def test_retry_call_recovers_after_transient_error():
    calls = {"count": 0}
    delays = []

    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise ConnectionError("temporary upstream outage")
        return "ok"

    result = retry_call(
        "test endpoint", flaky, attempts=3, base_delay=0.1,
        sleep=delays.append, jitter=lambda: 0.5,
        logger=logging.getLogger("test.retry"),
    )

    assert result == "ok"
    assert calls["count"] == 3
    assert delays == [0.1, 0.2]


def test_retry_call_raises_after_max_attempts():
    calls = {"count": 0}

    def always_fails():
        calls["count"] += 1
        raise TimeoutError("upstream timeout")

    with pytest.raises(TimeoutError):
        retry_call(
            "test endpoint", always_fails, attempts=2,
            sleep=lambda _: None, jitter=lambda: 0.5,
        )

    assert calls["count"] == 2


def test_retry_call_rejects_invalid_attempt_count():
    with pytest.raises(ValueError):
        retry_call("test endpoint", lambda: None, attempts=0)

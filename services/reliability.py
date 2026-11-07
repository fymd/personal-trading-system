"""Shared retry and structured rotating-log utilities for scheduled market jobs."""
from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")


def configure_logging(log_dir: str | Path = "logs", level: str | None = None) -> None:
    """Configure console + rotating UTF-8 JSON-lines logs; safe to call repeatedly."""
    root = logging.getLogger()
    if getattr(root, "_trading_logging_configured", False):
        return
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    resolved_level = (level or os.getenv("TRADING_LOG_LEVEL", "INFO")).upper()
    root.setLevel(getattr(logging, resolved_level, logging.INFO))

    class JsonFormatter(logging.Formatter):
        def format(self, record):
            payload = {
                "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                payload["exception"] = self.formatException(record.exc_info)
            for key in ("run_id", "sector", "attempt", "max_attempts", "elapsed_ms", "status"):
                if hasattr(record, key):
                    payload[key] = getattr(record, key)
            return json.dumps(payload, ensure_ascii=False)

    file_handler = RotatingFileHandler(
        Path(log_dir) / "market_sync.jsonl", maxBytes=5 * 1024 * 1024,
        backupCount=5, encoding="utf-8",
    )
    file_handler.setFormatter(JsonFormatter())
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s - %(message)s"
    ))
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    root._trading_logging_configured = True


def retry_call(
    operation: str,
    action: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 12.0,
    retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
    logger: logging.Logger | None = None,
) -> T:
    """Retry transient provider calls with capped exponential backoff and jitter."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    log = logger or logging.getLogger(__name__)
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            result = action()
            elapsed = round((time.monotonic() - started) * 1000)
            if attempt > 1:
                log.info("%s recovered after retry", operation,
                         extra={"attempt": attempt, "max_attempts": attempts,
                                "elapsed_ms": elapsed, "status": "success"})
            return result
        except retry_exceptions:
            elapsed = round((time.monotonic() - started) * 1000)
            if attempt >= attempts:
                log.exception("%s failed after %s attempts", operation, attempts,
                              extra={"attempt": attempt, "max_attempts": attempts,
                                     "elapsed_ms": elapsed, "status": "failed"})
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay *= 0.75 + 0.5 * jitter()
            log.warning("%s failed; retrying in %.2fs", operation, delay,
                        extra={"attempt": attempt, "max_attempts": attempts,
                               "elapsed_ms": elapsed, "status": "retry"})
            sleep(delay)

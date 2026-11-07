"""SQLite persistence for raw market bars, derived indicators, and sync audit records."""
from __future__ import annotations

import sqlite3
from pathlib import Path
import pandas as pd


SCHEMA = """
CREATE TABLE IF NOT EXISTS sector_daily (
  sector TEXT NOT NULL, trade_date TEXT NOT NULL, open REAL, close REAL NOT NULL,
  high REAL, low REAL, volume REAL, amount REAL, pct_change REAL,
  PRIMARY KEY (sector, trade_date)
);
CREATE TABLE IF NOT EXISTS benchmark_daily (
  symbol TEXT NOT NULL, trade_date TEXT NOT NULL, close REAL NOT NULL, amount REAL,
  PRIMARY KEY (symbol, trade_date)
);
CREATE TABLE IF NOT EXISTS sector_indicators (
  sector TEXT NOT NULL, trade_date TEXT NOT NULL, ret3_pct REAL, ret5_pct REAL,
  rs3_pct REAL, rs5_pct REAL, amount_ratio REAL, close REAL, ma5 REAL,
  initial_stage TEXT, final_stage TEXT, reason TEXT,
  PRIMARY KEY (sector, trade_date)
);
CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
  finished_at TEXT, status TEXT NOT NULL, sectors_total INTEGER DEFAULT 0,
  sectors_ok INTEGER DEFAULT 0, sectors_failed INTEGER DEFAULT 0,
  error_summary TEXT
);
"""


class MarketStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self):
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def start_run(self, started_at: str, sectors_total: int) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO sync_runs(started_at,status,sectors_total) VALUES(?,?,?)",
                (started_at, "running", sectors_total),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, finished_at: str, status: str,
                   sectors_ok: int, sectors_failed: int, errors: list[str]):
        with self.connect() as conn:
            conn.execute(
                """UPDATE sync_runs SET finished_at=?,status=?,sectors_ok=?,
                   sectors_failed=?,error_summary=? WHERE id=?""",
                (finished_at, status, sectors_ok, sectors_failed,
                 "\n".join(errors)[:8000], run_id),
            )

    def upsert_sector_bars(self, sector: str, frame: pd.DataFrame):
        rows = []
        for row in frame.to_dict("records"):
            rows.append((sector, row["date"], row.get("open"), row["close"],
                         row.get("high"), row.get("low"), row.get("volume"),
                         row.get("amount"), row.get("pct_change")))
        with self.connect() as conn:
            conn.executemany(
                """INSERT INTO sector_daily
                (sector,trade_date,open,close,high,low,volume,amount,pct_change)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(sector,trade_date) DO UPDATE SET
                open=excluded.open,close=excluded.close,high=excluded.high,low=excluded.low,
                volume=excluded.volume,amount=excluded.amount,pct_change=excluded.pct_change""",
                rows,
            )

    def upsert_benchmark(self, symbol: str, frame: pd.DataFrame):
        rows = [(symbol, r["date"], r["close"], r.get("amount"))
                for r in frame.to_dict("records")]
        with self.connect() as conn:
            conn.executemany(
                """INSERT INTO benchmark_daily(symbol,trade_date,close,amount)
                VALUES(?,?,?,?) ON CONFLICT(symbol,trade_date) DO UPDATE SET
                close=excluded.close,amount=excluded.amount""", rows,
            )

    def load_sector_history(self, sector: str) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(
                "SELECT trade_date AS date,open,close,high,low,volume,amount,pct_change "
                "FROM sector_daily WHERE sector=? ORDER BY trade_date", conn, params=(sector,)
            )

    def load_benchmark_history(self, symbol: str) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(
                "SELECT trade_date AS date,close,amount FROM benchmark_daily "
                "WHERE symbol=? ORDER BY trade_date", conn, params=(symbol,)
            )

    def save_indicators(self, frame: pd.DataFrame):
        if frame.empty:
            return
        cols = ["sector", "date", "ret3_pct", "ret5_pct", "rs3_pct", "rs5_pct",
                "amount_ratio", "close", "ma5", "初步阶段", "最终阶段", "判定依据"]
        rows = [tuple(r.get(c) for c in cols) for r in frame.to_dict("records")]
        with self.connect() as conn:
            conn.executemany(
                """INSERT INTO sector_indicators
                (sector,trade_date,ret3_pct,ret5_pct,rs3_pct,rs5_pct,amount_ratio,
                 close,ma5,initial_stage,final_stage,reason)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(sector,trade_date) DO UPDATE SET
                ret3_pct=excluded.ret3_pct,ret5_pct=excluded.ret5_pct,
                rs3_pct=excluded.rs3_pct,rs5_pct=excluded.rs5_pct,
                amount_ratio=excluded.amount_ratio,close=excluded.close,ma5=excluded.ma5,
                initial_stage=excluded.initial_stage,final_stage=excluded.final_stage,
                reason=excluded.reason""", rows,
            )

    def latest_indicators(self) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(
                """SELECT i.* FROM sector_indicators i
                JOIN (SELECT sector,MAX(trade_date) AS d FROM sector_indicators GROUP BY sector) x
                ON i.sector=x.sector AND i.trade_date=x.d ORDER BY i.sector""", conn
            )

    def latest_run(self):
        with self.connect() as conn:
            return conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()

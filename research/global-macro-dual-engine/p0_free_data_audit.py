#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0 A-share data-source audit. Diagnostic only; not production ETL/backtest."""
from __future__ import annotations
import hashlib, json, time, traceback, sys
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import pandas as pd

VERSION = "1.3"
START, END = "2019-01-01", "2019-12-31"
RECENT_START, RECENT_END = "2026-10-01", "2026-11-10"
OUT = Path("p0_free_data_audit")
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN_OUT = OUT / "runs" / RUN_ID
RAW, NORM = RUN_OUT / "raw", RUN_OUT / "normalized"
for p in (RAW, NORM):
    p.mkdir(parents=True, exist_ok=True)

STOCKS = [
    ("浦发银行", "600000", "sh.600000"),
    ("平安银行", "000001", "sz.000001"),
    ("宁德时代", "300750", "sz.300750"),
    ("中芯国际", "688981", "sh.688981"),
    ("ST大控(退市样本)", "600747", "sh.600747"),
]
INDICES = [("上证指数", "sh.000001", "sh000001"), ("深证成指", "sz.399001", "sz399001")]
BS_STOCK_FIELDS = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST"
BS_INDEX_FIELDS = "date,code,open,high,low,close,preclose,volume,amount,adjustflag"
PERIODS = [("2019", START, END), ("recent", RECENT_START, RECENT_END)]

def save(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")

def norm_bs(df, code, name):
    if df.empty:
        return df
    x = df.copy()
    for c in ("open", "high", "low", "close", "preclose", "volume", "amount", "turn", "pctChg"):
        if c in x:
            x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.rename(columns={"volume": "volume_shares", "amount": "amount_cny",
                          "tradestatus": "trade_status", "pctChg": "pct_change_pct"})
    x["date"] = pd.to_datetime(x["date"], errors="coerce")
    x["source"] = "baostock"
    x["security_code"] = code
    x["security_name"] = name
    return x

def norm_ak(df, code, name):
    if df.empty:
        return df
    x = df.copy()
    x = x.rename(columns={"日期": "date", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close",
                          "成交量": "volume_source_raw", "成交额": "amount_cny", "涨跌幅": "pct_change_pct",
                          "换手率": "turnover_pct", "volume": "volume_source_raw", "amount": "amount_cny"})
    x["date"] = pd.to_datetime(x["date"], errors="coerce")
    for c in ("open", "high", "low", "close", "volume_source_raw", "amount_cny", "pct_change_pct", "turnover_pct"):
        if c in x:
            x[c] = pd.to_numeric(x[c], errors="coerce")
    x["source"] = "akshare"
    x["security_code"] = code
    x["security_name"] = name
    return x

def bs_fetch():
    import baostock as bs
    out = {"login": None, "downloads": []}
    lg = bs.login()
    out["login"] = {"error_code": lg.error_code, "error_msg": lg.error_msg}
    if lg.error_code != "0":
        return out
    try:
        out["universe_snapshots"] = []
        for day in ("2019-12-31", "2021-12-31"):
            try:
                rs = bs.query_all_stock(day=day)
                rows = []
                while rs.error_code == "0" and rs.next():
                    rows.append(rs.get_row_data())
                df = pd.DataFrame(rows, columns=rs.fields)
                save(df, RAW / f"bs_universe_{day}.csv")
                out["universe_snapshots"].append({"date": day, "error_code": rs.error_code, "rows": len(df),
                    "contains_600747": bool(not df.empty and (df["code"] == "sh.600747").any())})
            except Exception as e:
                out["universe_snapshots"].append({"date": day, "error": repr(e)})
        samples = [(n, c, b, False) for n, c, b in STOCKS] + [(n, c, c, True) for n, c, _ in INDICES]
        for name, code, bs_code, is_index in samples:
            for tag, start, end in PERIODS:
                item = {"code": code, "period": tag, "start_date": start, "end_date": end}
                try:
                    rs = bs.query_history_k_data_plus(bs_code, BS_INDEX_FIELDS if is_index else BS_STOCK_FIELDS,
                        start_date=start, end_date=end, frequency="d", adjustflag="3")
                    rows = []
                    while rs.error_code == "0" and rs.next():
                        rows.append(rs.get_row_data())
                    df = pd.DataFrame(rows, columns=rs.fields)
                    item.update({"error_code": rs.error_code, "error_msg": rs.error_msg, "rows": len(df)})
                    raw_path = RAW / f"baostock_{bs_code.replace('.', '_')}_{tag}.csv"
                    save(df, raw_path)
                    if not df.empty:
                        save(norm_bs(df, code, name), NORM / raw_path.name)
                except Exception as e:
                    item["error"] = repr(e)
                out["downloads"].append(item)
                time.sleep(0.3)
    finally:
        lo = bs.logout()
        out["logout"] = {"error_code": lo.error_code, "error_msg": lo.error_msg}
    return out

def ak_fetch():
    import akshare as ak
    out = {"downloads": []}
    for name, code, _ in STOCKS:
        for tag, start, end in PERIODS:
            item = {"code": code, "period": tag, "start_date": start, "end_date": end}
            try:
                df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start.replace("-", ""),
                                        end_date=end.replace("-", ""), adjust="")
                raw_path = RAW / f"akshare_{code}_{tag}.csv"
                save(df, raw_path)
                item["rows"] = len(df)
                if not df.empty:
                    save(norm_ak(df, code, name), NORM / raw_path.name)
            except Exception as e:
                item["error"] = repr(e)
            out["downloads"].append(item)
            time.sleep(0.5)
    for name, code, symbol in INDICES:
        for tag, start, end in PERIODS:
            item = {"code": code, "period": tag, "start_date": start, "end_date": end}
            try:
                df = ak.stock_zh_index_daily_em(symbol=symbol, start_date=start.replace("-", ""),
                                                end_date=end.replace("-", ""))
                raw_path = RAW / f"akshare_index_{symbol}_{tag}.csv"
                save(df, raw_path)
                item["rows"] = len(df)
                if not df.empty:
                    save(norm_ak(df, code, name), NORM / raw_path.name)
            except Exception as e:
                item["error"] = repr(e)
            out["downloads"].append(item)
            time.sleep(0.5)
    return out

def compare(a_path, b_path, code, period):
    base = {"code": code, "period": period}
    if not a_path.exists() or not b_path.exists():
        return {**base, "status": "MISSING_FILE"}
    a, b = pd.read_csv(a_path), pd.read_csv(b_path)
    if a.empty or b.empty:
        return {**base, "status": "EMPTY_SOURCE", "a_rows": len(a), "b_rows": len(b)}
    required = ["date", "open", "high", "low", "close", "amount_cny"]
    missing_a = [c for c in required if c not in a.columns]
    missing_b = [c for c in required if c not in b.columns]
    if missing_a or missing_b:
        return {**base, "status": "MISSING_REQUIRED_COLUMNS", "missing_baostock": missing_a,
                "missing_akshare": missing_b}
    a["date"] = pd.to_datetime(a["date"], errors="coerce")
    b["date"] = pd.to_datetime(b["date"], errors="coerce")
    if a["date"].duplicated().any() or b["date"].duplicated().any():
        return {**base, "status": "DUPLICATE_DATES", "a_duplicate_dates": int(a["date"].duplicated().sum()),
                "b_duplicate_dates": int(b["date"].duplicated().sum())}
    m = a[required].merge(b[required], on="date", how="outer", suffixes=("_bs", "_ak"), indicator=True)
    c = m[m["_merge"] == "both"]
    result = {**base, "status": "COMPARED", "baostock_rows": len(a), "akshare_rows": len(b),
              "common_dates": len(c), "baostock_only_dates": int((m["_merge"] == "left_only").sum()),
              "akshare_only_dates": int((m["_merge"] == "right_only").sum())}
    for field in ("open", "high", "low", "close", "amount_cny"):
        delta = (pd.to_numeric(c[field + "_bs"], errors="coerce") -
                 pd.to_numeric(c[field + "_ak"], errors="coerce")).abs()
        result[field + "_median_abs_diff"] = float(delta.median()) if len(delta.dropna()) else None
        result[field + "_max_abs_diff"] = float(delta.max()) if len(delta.dropna()) else None
        result[field + "_nonzero_diff_count"] = int((delta > 1e-6).sum())
    return result

def quality_checks():
    results = []
    for path in sorted(NORM.glob("*.csv")):
        try:
            d = pd.read_csv(path)
            dates = pd.to_datetime(d["date"], errors="coerce") if "date" in d else pd.Series(dtype="datetime64[ns]")
            q = {"file": str(path.relative_to(RUN_OUT)), "rows": len(d),
                 "duplicate_dates": int(dates.duplicated().sum()), "invalid_dates": int(dates.isna().sum()),
                 "date_out_of_order": not dates.dropna().is_monotonic_increasing}
            for field in ("open", "high", "low", "close", "amount_cny"):
                if field in d:
                    d[field] = pd.to_numeric(d[field], errors="coerce")
            q["null_ohlc_rows"] = int(d[["open", "high", "low", "close"]].isna().any(axis=1).sum()) if all(
                f in d for f in ("open", "high", "low", "close")) else None
            q["nonpositive_ohlc_values"] = int((d[["open", "high", "low", "close"]] <= 0).sum().sum()) if all(
                f in d for f in ("open", "high", "low", "close")) else None
            if all(f in d for f in ("open", "high", "low", "close")):
                q["ohlc_logic_errors"] = int(((d.high < d[["open", "close", "low"]].max(axis=1)) |
                    (d.low > d[["open", "close", "high"]].min(axis=1))).sum())
            else:
                q["ohlc_logic_errors"] = None
            q["null_amount_rows"] = int(d["amount_cny"].isna().sum()) if "amount_cny" in d else None
            results.append(q)
        except Exception as e:
            results.append({"file": str(path.relative_to(RUN_OUT)), "status": "READ_ERROR", "error": repr(e)})
    return results

def inventory():
    rows = []
    for folder in (RAW, NORM):
        for path in sorted(folder.glob("*.csv")):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append({"file": str(path.relative_to(RUN_OUT)), "bytes": path.stat().st_size, "sha256": digest})
    return rows

def main():
    manifest = {"script_version": VERSION, "run_id": RUN_ID, "run_directory": str(RUN_OUT),
        "run_started_utc": datetime.now(timezone.utc).isoformat(), "python_version": sys.version,
        "dependency_versions": {}, "sample_periods": PERIODS, "stocks": STOCKS, "indices": INDICES,
        "results": {}, "limitations": ["No transaction-calendar completeness adjudication",
        "No official-source OHLC cross-check", "No volume-unit cross-source comparison",
        "No authorization/legal review", "No production/backtest approval"]}
    for pkg in ("pandas", "baostock", "akshare"):
        try:
            manifest["dependency_versions"][pkg] = version(pkg)
        except PackageNotFoundError:
            manifest["dependency_versions"][pkg] = "NOT_INSTALLED"
    try:
        manifest["results"]["baostock"] = bs_fetch()
    except Exception:
        manifest["results"]["baostock_fatal"] = traceback.format_exc()
    try:
        manifest["results"]["akshare"] = ak_fetch()
    except Exception:
        manifest["results"]["akshare_fatal"] = traceback.format_exc()
    pairs = []
    for _, code, bs_code in STOCKS:
        for tag, _, _ in PERIODS:
            pairs.append(compare(NORM / f"baostock_{bs_code.replace('.', '_')}_{tag}.csv",
                                 NORM / f"akshare_{code}_{tag}.csv", code, tag))
    for _, code, symbol in INDICES:
        for tag, _, _ in PERIODS:
            pairs.append(compare(NORM / f"baostock_{code.replace('.', '_')}_{tag}.csv",
                                 NORM / f"akshare_index_{symbol}_{tag}.csv", code, tag))
    manifest["comparisons"] = pairs
    manifest["normalized_file_quality_checks"] = quality_checks()
    manifest["file_inventory"] = inventory()
    manifest["run_finished_utc"] = datetime.now(timezone.utc).isoformat()
    (RUN_OUT / "manifest_and_results.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                                        encoding="utf-8")
    pd.DataFrame(pairs).to_csv(RUN_OUT / "comparison_summary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(manifest["normalized_file_quality_checks"]).to_csv(
        RUN_OUT / "data_quality_checks.csv", index=False, encoding="utf-8-sig")
    print(f"Audit complete. Run ID: {RUN_ID}")
    print(f"Reports: {RUN_OUT}")
    print("Review manifest_and_results.json, comparison_summary.csv and data_quality_checks.csv.")

if __name__ == "__main__":
    main()

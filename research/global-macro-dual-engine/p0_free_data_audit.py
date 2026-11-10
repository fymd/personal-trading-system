#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0 A-share data-source audit. Diagnostic only; not production ETL/backtest."""
from __future__ import annotations
import json, time, traceback, sys
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import pandas as pd

VERSION="1.2"
START, END="2019-01-01","2019-12-31"
RECENT_START, RECENT_END="2026-10-01","2026-11-10"
OUT=Path("p0_free_data_audit"); RAW=OUT/"raw"; NORM=OUT/"normalized"
for p in (RAW,NORM): p.mkdir(parents=True,exist_ok=True)
STOCKS=[
 ("浦发银行","600000","sh.600000"),("平安银行","000001","sz.000001"),
 ("宁德时代","300750","sz.300750"),("中芯国际","688981","sh.688981"),
 ("ST大控(退市样本)","600747","sh.600747")]
INDICES=[("上证指数","sh.000001","sh000001"),("深证成指","sz.399001","sz399001")]
BS_STOCK_FIELDS="date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST"
BS_INDEX_FIELDS="date,code,open,high,low,close,preclose,volume,amount,adjustflag"
PERIODS=[("2019",START,END),("recent",RECENT_START,RECENT_END)]

def save(df,path): df.to_csv(path,index=False,encoding="utf-8-sig")
def norm_bs(df,code,name):
    if df.empty:return df
    x=df.copy()
    for c in ("open","high","low","close","preclose","volume","amount","turn","pctChg"):
        if c in x:x[c]=pd.to_numeric(x[c],errors="coerce")
    x=x.rename(columns={"volume":"volume_shares","amount":"amount_cny","tradestatus":"trade_status","pctChg":"pct_change_pct"})
    x["date"]=pd.to_datetime(x["date"],errors="coerce"); x["source"]="baostock"; x["security_code"]=code; x["security_name"]=name
    return x
def norm_ak(df,code,name,index=False):
    if df.empty:return df
    x=df.copy()
    x=x.rename(columns={"日期":"date","开盘":"open","最高":"high","最低":"low","收盘":"close",
                        "成交量":"volume_source_raw","成交额":"amount_cny","涨跌幅":"pct_change_pct","换手率":"turnover_pct",
                        "volume":"volume_source_raw","amount":"amount_cny"})
    x["date"]=pd.to_datetime(x["date"],errors="coerce")
    for c in ("open","high","low","close","volume_source_raw","amount_cny","pct_change_pct","turnover_pct"):
        if c in x:x[c]=pd.to_numeric(x[c],errors="coerce")
    x["source"]="akshare"; x["security_code"]=code; x["security_name"]=name
    return x
def bs_fetch():
    import baostock as bs
    out={"login":None,"downloads":[]}
    lg=bs.login(); out["login"]={"error_code":lg.error_code,"error_msg":lg.error_msg}
    if lg.error_code!="0":return out
    try:
        out["universe_snapshots"]=[]
        for day in ("2019-12-31","2021-12-31"):
            try:
                rs=bs.query_all_stock(day=day); rows=[]
                while rs.error_code=="0" and rs.next():rows.append(rs.get_row_data())
                df=pd.DataFrame(rows,columns=rs.fields); save(df,RAW/f"bs_universe_{day}.csv")
                out["universe_snapshots"].append({"date":day,"error_code":rs.error_code,"rows":len(df),
                    "contains_600747":bool(not df.empty and (df["code"]=="sh.600747").any())})
            except Exception as e:out["universe_snapshots"].append({"date":day,"error":repr(e)})
        samples=[(n,c,b,False) for n,c,b in STOCKS]+[(n,c,c,True) for n,c,_ in INDICES]
        for name,code,bs_code,is_index in samples:
            for tag,start,end in PERIODS:
                item={"code":code,"period":tag}
                try:
                    rs=bs.query_history_k_data_plus(bs_code,BS_INDEX_FIELDS if is_index else BS_STOCK_FIELDS,
                        start_date=start,end_date=end,frequency="d",adjustflag="3")
                    rows=[]
                    while rs.error_code=="0" and rs.next():rows.append(rs.get_row_data())
                    df=pd.DataFrame(rows,columns=rs.fields); item.update({"error_code":rs.error_code,"error_msg":rs.error_msg,"rows":len(df)})
                    save(df,RAW/f"baostock_{bs_code.replace('.','_')}_{tag}.csv")
                    if not df.empty:save(norm_bs(df,code,name),NORM/f"baostock_{bs_code.replace('.','_')}_{tag}.csv")
                except Exception as e:item["error"]=repr(e)
                out["downloads"].append(item); time.sleep(.3)
    finally:
        lo=bs.logout(); out["logout"]={"error_code":lo.error_code,"error_msg":lo.error_msg}
    return out
def ak_fetch():
    import akshare as ak
    out={"downloads":[]}
    for name,code,_ in STOCKS:
        for tag,start,end in PERIODS:
            item={"code":code,"period":tag}
            try:
                df=ak.stock_zh_a_hist(symbol=code,period="daily",start_date=start.replace("-",""),end_date=end.replace("-",""),adjust="")
                save(df,RAW/f"akshare_{code}_{tag}.csv"); item["rows"]=len(df)
                if not df.empty:save(norm_ak(df,code,name),NORM/f"akshare_{code}_{tag}.csv")
            except Exception as e:item["error"]=repr(e)
            out["downloads"].append(item);time.sleep(.5)
    for name,code,symbol in INDICES:
        for tag,start,end in PERIODS:
            item={"code":code,"period":tag}
            try:
                df=ak.stock_zh_index_daily_em(symbol=symbol,start_date=start.replace("-",""),end_date=end.replace("-",""))
                save(df,RAW/f"akshare_index_{symbol}_{tag}.csv");item["rows"]=len(df)
                if not df.empty:save(norm_ak(df,code,name,True),NORM/f"akshare_index_{symbol}_{tag}.csv")
            except Exception as e:item["error"]=repr(e)
            out["downloads"].append(item);time.sleep(.5)
    return out
def compare(a_path,b_path,code,period):
    if not a_path.exists() or not b_path.exists():return {"code":code,"period":period,"status":"MISSING_FILE"}
    a,b=pd.read_csv(a_path),pd.read_csv(b_path)
    if a.empty or b.empty:return {"code":code,"period":period,"status":"EMPTY_SOURCE","a_rows":len(a),"b_rows":len(b)}
    for x in (a,b):x["date"]=pd.to_datetime(x["date"],errors="coerce")
    m=a[["date","open","high","low","close","amount_cny"]].merge(
      b[["date","open","high","low","close","amount_cny"]],on="date",how="outer",suffixes=("_bs","_ak"),indicator=True)
    c=m[m["_merge"]=="both"];r={"code":code,"period":period,"status":"COMPARED","baostock_rows":len(a),"akshare_rows":len(b),
      "common_dates":len(c),"baostock_only_dates":int((m["_merge"]=="left_only").sum()),"akshare_only_dates":int((m["_merge"]=="right_only").sum())}
    for f in ("open","high","low","close","amount_cny"):
        delta=(pd.to_numeric(c[f+"_bs"],errors="coerce")-pd.to_numeric(c[f+"_ak"],errors="coerce")).abs()
        r[f+"_median_abs_diff"]=float(delta.median()) if len(delta.dropna()) else None
        r[f+"_max_abs_diff"]=float(delta.max()) if len(delta.dropna()) else None
        r[f+"_nonzero_diff_count"]=int((delta>1e-6).sum())
    return r
def quality_checks():
    out=[]
    for p in sorted(NORM.glob("*.csv")):
        try:
            d=pd.read_csv(p); dates=pd.to_datetime(d.get("date"),errors="coerce")
            q={"file":str(p),"rows":len(d),"duplicate_dates":int(dates.duplicated().sum()),
               "invalid_dates":int(dates.isna().sum()),"date_out_of_order":not dates.dropna().is_monotonic_increasing}
            for f in ("open","high","low","close"):
                if f in d:d[f]=pd.to_numeric(d[f],errors="coerce")
            q["null_close"]=int(d["close"].isna().sum()) if "close" in d else None
            q["nonpositive_close"]=int((d["close"]<=0).sum()) if "close" in d else None
            if all(f in d for f in ("open","high","low","close")):
                q["ohlc_logic_errors"]=int(((d.high<d[["open","close","low"]].max(axis=1))|(d.low>d[["open","close","high"]].min(axis=1))).sum())
            else:q["ohlc_logic_errors"]=None
            q["status"]="CHECKED";out.append(q)
        except Exception as e:out.append({"file":str(p),"status":"READ_ERROR","error":repr(e)})
    return out
def main():
    manifest={"script_version":VERSION,"run_started_utc":datetime.now(timezone.utc).isoformat(),
      "python_version":sys.version,"dependency_versions":{},"sample_periods":PERIODS,
      "stocks":STOCKS,"indices":INDICES,"results":{}}
    for pkg in ("pandas","baostock","akshare"):
        try:manifest["dependency_versions"][pkg]=version(pkg)
        except PackageNotFoundError:manifest["dependency_versions"][pkg]="NOT_INSTALLED"
    try:manifest["results"]["baostock"]=bs_fetch()
    except Exception:manifest["results"]["baostock_fatal"]=traceback.format_exc()
    try:manifest["results"]["akshare"]=ak_fetch()
    except Exception:manifest["results"]["akshare_fatal"]=traceback.format_exc()
    pairs=[]
    for name,code,bs_code in STOCKS:
        for tag,_,_ in PERIODS:pairs.append(compare(NORM/f"baostock_{bs_code.replace('.','_')}_{tag}.csv",NORM/f"akshare_{code}_{tag}.csv",code,tag))
    for name,code,symbol in INDICES:
        for tag,_,_ in PERIODS:pairs.append(compare(NORM/f"baostock_{code.replace('.','_')}_{tag}.csv",NORM/f"akshare_index_{symbol}_{tag}.csv",code,tag))
    manifest["comparisons"]=pairs;manifest["normalized_file_quality_checks"]=quality_checks()
    manifest["run_finished_utc"]=datetime.now(timezone.utc).isoformat()
    (OUT/"manifest_and_results.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    pd.DataFrame(pairs).to_csv(OUT/"comparison_summary.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(manifest["normalized_file_quality_checks"]).to_csv(OUT/"data_quality_checks.csv",index=False,encoding="utf-8-sig")
    print("Audit complete. Review manifest, comparison_summary.csv and data_quality_checks.csv.")
if __name__=="__main__":main()

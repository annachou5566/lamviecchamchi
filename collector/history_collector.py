from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from collector.asxn_browser import AsxnBrowserSession, AsxnBrowserError
from collector.asxn_schema import SEAM_DATE, AsxnSchemaError, apply_hourly_reconciliation, finalize_without_hourly, normalize_daily_rows
from collector.delivery import DeliveryError, build_ingest_body, deliver

REVISION_DAYS = 7
MAX_SEED_DAYS = 31

def _date(value: str):
    try: return datetime.strptime(value,"%Y-%m-%d").date()
    except ValueError as error: raise ValueError("DATE_INVALID") from error

def _bounds(mode: str, seed_from: str|None, seed_to: str|None) -> tuple[str,str,int]:
    today = datetime.now(timezone.utc).date()
    if mode == "rolling":
        start = max(today-timedelta(days=REVISION_DAYS-1), _date(SEAM_DATE))
        return start.isoformat(),today.isoformat(),REVISION_DAYS
    if not seed_from or not seed_to: raise ValueError("SEED_RANGE_REQUIRED")
    start,end,seam = _date(seed_from),_date(seed_to),_date(SEAM_DATE)
    if start<seam or end<start or end>today: raise ValueError("SEED_RANGE_INVALID")
    span=(end-start).days+1
    if span>MAX_SEED_DAYS: raise ValueError("SEED_RANGE_TOO_WIDE")
    fetch_days=(today-start).days+1
    if fetch_days>MAX_SEED_DAYS: raise ValueError("SEED_FETCH_WINDOW_TOO_WIDE")
    return start.isoformat(),end.isoformat(),fetch_days

def run(mode: str, seed_from: str|None, seed_to: str|None) -> None:
    from_date,to_date,fetch_days = _bounds(mode,seed_from,seed_to)
    observed_at_ms = int(time.time()*1000)
    current_date = datetime.now(timezone.utc).date().isoformat()
    with AsxnBrowserSession() as session:
        rows = normalize_daily_rows(session.fetch_daily(fetch_days),observed_at_ms=observed_at_ms,from_date=from_date,to_date=to_date)
        if not rows: raise AsxnSchemaError("DAILY_ROWS_EMPTY")
        try:
            rows = apply_hourly_reconciliation(rows,session.fetch_hourly(min(fetch_days*24,MAX_SEED_DAYS*24)),current_date=current_date)
        except AsxnBrowserError:
            rows = finalize_without_hourly(rows)
    if mode == "seed":
        expected=(_date(to_date)-_date(from_date)).days+1
        if len(rows)!=expected: raise AsxnSchemaError("SEED_ROWS_INCOMPLETE")
    body = build_ingest_body(rows,mode=mode,revision_days=REVISION_DAYS,seed_from=from_date if mode=="seed" else None,seed_to=to_date if mode=="seed" else None)
    ingest_origin = str(os.getenv("HL_HISTORY_INGEST_ORIGIN","")).strip()
    if not ingest_origin: raise DeliveryError("INGEST_ORIGIN_MISSING")
    result=deliver(body,ingest_origin=ingest_origin)
    print(f"HL_HISTORY_DELIVERY_OK applied={str(result['applied']).lower()} rows={len(rows)}")

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--mode",choices=("rolling","seed"),default="rolling"); parser.add_argument("--seed-from"); parser.add_argument("--seed-to"); args=parser.parse_args()
    try: run(args.mode,args.seed_from,args.seed_to); return 0
    except (AsxnBrowserError,AsxnSchemaError,DeliveryError,ValueError) as error:
        print(f"HL_HISTORY_FAIL code={str(error)}",file=sys.stderr); return 1

if __name__ == "__main__": raise SystemExit(main())

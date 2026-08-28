from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

SEAM_DATE = "2026-08-25"
CENT = Decimal("0.01")
MAX_SAFE_INTEGER = 9_007_199_254_740_991
_MONEY_ALIASES = {
    "long": ("long_notional", "long_notional_usd", "long_usd"),
    "short": ("short_notional", "short_notional_usd", "short_usd"),
    "total": ("total_notional_usd", "total_notional", "total_notional_volume"),
}
_COUNT_ALIASES = {
    "long": ("long_liquidations", "long_count"),
    "short": ("short_liquidations", "short_count"),
    "total": ("total_liquidations", "count"),
}
_TIME_ALIASES = ("hour", "hour_start", "timestamp", "time", "date")

class AsxnSchemaError(ValueError):
    pass

def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "stats", "items", "rows", "chart_data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []

def _first(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None

def _decimal(value: Any, code: str) -> Decimal:
    if value is None or value == "" or isinstance(value, bool):
        raise AsxnSchemaError(code)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise AsxnSchemaError(code) from error
    if not number.is_finite() or number < 0:
        raise AsxnSchemaError(code)
    return number

def _usd_cents(value: Any, code: str) -> int:
    number = _decimal(value, code)
    cents = int((number / CENT).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if cents < 0 or cents > MAX_SAFE_INTEGER:
        raise AsxnSchemaError(code)
    return cents

def _count(value: Any, code: str) -> int:
    number = _decimal(value, code)
    integral = number.to_integral_value()
    if number != integral:
        raise AsxnSchemaError(code)
    result = int(integral)
    if result < 0 or result > MAX_SAFE_INTEGER:
        raise AsxnSchemaError(code)
    return result

def _parse_time(value: Any) -> datetime:
    if value is None or value == "":
        raise AsxnSchemaError("TIME_MISSING")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        raw = float(value)
        if raw > 1e12:
            raw /= 1000.0
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise AsxnSchemaError("TIME_INVALID") from error
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise AsxnSchemaError("TIME_INVALID") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def _money(row: dict[str, Any], side: str) -> int:
    return _usd_cents(_first(row, _MONEY_ALIASES[side]), f"{side.upper()}_MONEY_INVALID")

def _counts(row: dict[str, Any], side: str) -> int:
    return _count(_first(row, _COUNT_ALIASES[side]), f"{side.upper()}_COUNT_INVALID")

def _base_daily(row: dict[str, Any], observed_at_ms: int) -> dict[str, Any]:
    date = _parse_time(_first(row, _TIME_ALIASES)).date().isoformat()
    if date < SEAM_DATE:
        raise AsxnSchemaError("DATE_BEFORE_SEAM")
    long_cents, short_cents, total_cents = _money(row,"long"), _money(row,"short"), _money(row,"total")
    if abs(long_cents + short_cents - total_cents) > 1:
        raise AsxnSchemaError("TOTAL_MONEY_MISMATCH")
    long_count, short_count, total_count = _counts(row,"long"), _counts(row,"short"), _counts(row,"total")
    if long_count + short_count != total_count:
        raise AsxnSchemaError("TOTAL_COUNT_MISMATCH")
    if not isinstance(observed_at_ms, int) or observed_at_ms <= 0:
        raise AsxnSchemaError("OBSERVED_AT_INVALID")
    return {"date":date,"longCents":long_cents,"shortCents":short_cents,"totalCents":total_cents,"longCount":long_count,"shortCount":short_count,"count":total_count,"observedAtMs":observed_at_ms,"provisional":True,"reconciliationStatus":"not-proven"}

def _digest(row: dict[str, Any]) -> str:
    canonical = {key: row[key] for key in ("date","longCents","shortCents","totalCents","longCount","shortCount","count","provisional","reconciliationStatus")}
    if row["reconciliationStatus"] != "not-proven":
        canonical["hourlyBucketCount"] = row["hourlyBucketCount"]
        canonical["hourlyScopeMatch"] = row["hourlyScopeMatch"]
    return hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def normalize_daily_rows(payload: Any, *, observed_at_ms: int, from_date: str, to_date: str) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for raw in rows_from_payload(payload):
        raw_date = _parse_time(_first(raw, _TIME_ALIASES)).date().isoformat()
        if raw_date < from_date or raw_date > to_date:
            continue
        row = _base_daily(raw, observed_at_ms)
        if row["date"] in selected:
            raise AsxnSchemaError("DUPLICATE_DAILY_DATE")
        selected[row["date"]] = row
    return [selected[date] for date in sorted(selected)]

def _hour_row(row: dict[str, Any]) -> tuple[str,str,tuple[int,int,int,int,int,int]]:
    dt = _parse_time(_first(row, _TIME_ALIASES))
    hour_key = dt.replace(minute=0,second=0,microsecond=0).isoformat()
    long_cents, short_cents, total_cents = _money(row,"long"), _money(row,"short"), _money(row,"total")
    long_count, short_count, total_count = _counts(row,"long"), _counts(row,"short"), _counts(row,"total")
    if abs(long_cents + short_cents - total_cents) > 1:
        raise AsxnSchemaError("HOURLY_TOTAL_MONEY_MISMATCH")
    if long_count + short_count != total_count:
        raise AsxnSchemaError("HOURLY_TOTAL_COUNT_MISMATCH")
    return dt.date().isoformat(), hour_key, (long_cents,short_cents,total_cents,long_count,short_count,total_count)

def apply_hourly_reconciliation(daily_rows: list[dict[str, Any]], hourly_payload: Any, *, current_date: str) -> list[dict[str, Any]]:
    grouped: dict[str,dict[str,tuple[int,int,int,int,int,int]]] = {}
    for raw in rows_from_payload(hourly_payload):
        try:
            day,hour,values = _hour_row(raw)
        except AsxnSchemaError:
            continue
        bucket = grouped.setdefault(day,{})
        bucket[hour] = () if hour in bucket else values
    for row in daily_rows:
        if row["date"] >= current_date:
            row["payloadDigest"] = _digest(row); continue
        hours = grouped.get(row["date"],{})
        if len(hours) != 24 or any(len(values) != 6 for values in hours.values()):
            row["payloadDigest"] = _digest(row); continue
        sums = tuple(sum(values[i] for values in hours.values()) for i in range(6))
        daily = (row["longCents"],row["shortCents"],row["totalCents"],row["longCount"],row["shortCount"],row["count"])
        money_match = all(abs(sums[i]-daily[i]) <= 1 for i in range(3))
        count_match = all(sums[i] == daily[i] for i in range(3,6))
        row["reconciliationStatus"] = "match" if money_match and count_match else "mismatch"
        row["hourlyBucketCount"] = 24
        row["hourlyScopeMatch"] = True
        row["payloadDigest"] = _digest(row)
    return daily_rows

def finalize_without_hourly(daily_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in daily_rows:
        row["payloadDigest"] = _digest(row)
    return daily_rows

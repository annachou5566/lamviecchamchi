from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from typing import Any

from collector.asxn_browser import AsxnBrowserError, AsxnBrowserSession
from collector.asxn_schema import AsxnSchemaError, _hour_row, normalize_daily_rows, rows_from_payload

TARGET_FROM = "2026-08-26"
TARGET_TO = "2026-08-27"
MAX_FETCH_DAYS = 31


def _date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise ValueError("DATE_INVALID") from error


def _fetch_window(today: str) -> tuple[int, int]:
    start = _date(TARGET_FROM)
    end = _date(TARGET_TO)
    current = _date(today)
    if current < end:
        raise ValueError("FORENSIC_TARGET_NOT_CLOSED")
    fetch_days = (current - start).days + 1
    if fetch_days < 1 or fetch_days > MAX_FETCH_DAYS:
        raise ValueError("FORENSIC_FETCH_WINDOW_OUT_OF_BOUNDS")
    return fetch_days, fetch_days * 24


def reconciliation_diagnostics(
    daily_payload: Any,
    hourly_payload: Any,
    *,
    observed_at_ms: int,
    current_date: str,
) -> list[dict[str, Any]]:
    rows = normalize_daily_rows(
        daily_payload,
        observed_at_ms=observed_at_ms,
        from_date=TARGET_FROM,
        to_date=TARGET_TO,
    )
    expected = [TARGET_FROM, TARGET_TO]
    if [row["date"] for row in rows] != expected:
        raise AsxnSchemaError("FORENSIC_DAILY_ROWS_INCOMPLETE")

    grouped: dict[str, dict[str, tuple[int, int, int, int, int, int]]] = {}
    for raw in rows_from_payload(hourly_payload):
        try:
            day, hour, values = _hour_row(raw)
        except AsxnSchemaError:
            continue
        if day < TARGET_FROM or day > TARGET_TO:
            continue
        bucket = grouped.setdefault(day, {})
        bucket[hour] = () if hour in bucket else values

    diagnostics: list[dict[str, Any]] = []
    for row in rows:
        date = row["date"]
        hours = grouped.get(date, {})
        valid_24 = len(hours) == 24 and all(len(values) == 6 for values in hours.values())
        daily = (
            row["longCents"], row["shortCents"], row["totalCents"],
            row["longCount"], row["shortCount"], row["count"],
        )
        if not valid_24:
            diagnostics.append({
                "date": date,
                "status": "not-proven",
                "hourlyBucketCount": len(hours),
                "daily": daily,
                "hourly": None,
                "delta": None,
            })
            continue

        hourly = tuple(sum(values[index] for values in hours.values()) for index in range(6))
        delta = tuple(daily[index] - hourly[index] for index in range(6))
        money_match = all(abs(delta[index]) <= 1 for index in range(3))
        count_match = all(delta[index] == 0 for index in range(3, 6))
        diagnostics.append({
            "date": date,
            "status": "match" if money_match and count_match else "mismatch",
            "hourlyBucketCount": 24,
            "daily": daily,
            "hourly": hourly,
            "delta": delta,
        })
    return diagnostics


def _format_triplet(values: tuple[int, int, int] | None) -> str:
    if values is None:
        return "UNAVAILABLE"
    return f"L={values[0]} S={values[1]} T={values[2]}"


def _format_counts(values: tuple[int, int, int] | None) -> str:
    if values is None:
        return "UNAVAILABLE"
    return f"L={values[0]} S={values[1]} T={values[2]}"


def run() -> None:
    current_date = datetime.now(timezone.utc).date().isoformat()
    fetch_days, fetch_hours = _fetch_window(current_date)
    observed_at_ms = int(time.time() * 1000)

    with AsxnBrowserSession() as session:
        daily_payload = session.fetch_daily(fetch_days)
        hourly_payload = session.fetch_hourly(fetch_hours)

    diagnostics = reconciliation_diagnostics(
        daily_payload,
        hourly_payload,
        observed_at_ms=observed_at_ms,
        current_date=current_date,
    )

    print("WAVE_ALPHA_HL_26_27_FORENSIC_V1")
    print("mode=READ_ONLY_EPHEMERAL_NO_DELIVERY")
    print(f"target={TARGET_FROM}..{TARGET_TO}")
    for item in diagnostics:
        daily = item["daily"]
        hourly = item["hourly"]
        delta = item["delta"]
        print(
            "FORENSIC | "
            f"{item['date']} status={item['status']} buckets={item['hourlyBucketCount']} "
            f"daily_money[{_format_triplet(daily[:3])}] "
            f"hourly_money[{_format_triplet(hourly[:3] if hourly else None)}] "
            f"delta_money[{_format_triplet(delta[:3] if delta else None)}] "
            f"daily_counts[{_format_counts(daily[3:])}] "
            f"hourly_counts[{_format_counts(hourly[3:] if hourly else None)}] "
            f"delta_counts[{_format_counts(delta[3:] if delta else None)}]"
        )
    mismatch_dates = [item["date"] for item in diagnostics if item["status"] == "mismatch"]
    not_proven_dates = [item["date"] for item in diagnostics if item["status"] == "not-proven"]
    print(f"mismatch_dates={mismatch_dates}")
    print(f"not_proven_dates={not_proven_dates}")
    print("delivery=DISABLED")
    print("summary=PASS")


def main() -> int:
    try:
        run()
        return 0
    except (AsxnBrowserError, AsxnSchemaError, ValueError) as error:
        print(f"WAVE_ALPHA_HL_26_27_FORENSIC_FAIL code={str(error)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path
import unittest

from collector.history_forensic import _fetch_window, reconciliation_diagnostics


def daily_row(date: str, long: int, short: int, long_count: int, short_count: int) -> dict:
    return {
        "date": f"{date}T00:00:00Z",
        "long_notional": long,
        "short_notional": short,
        "total_notional": long + short,
        "long_liquidations": long_count,
        "short_liquidations": short_count,
        "total_liquidations": long_count + short_count,
    }


def hourly_day(date: str, *, long: int, short: int, long_count: int, short_count: int) -> list[dict]:
    rows=[]
    for hour in range(24):
        is_last=hour == 23
        l=long if is_last else 0
        s=short if is_last else 0
        lc=long_count if is_last else 0
        sc=short_count if is_last else 0
        rows.append({
            "hour": f"{date}T{hour:02d}:00:00Z",
            "long_notional": l,
            "short_notional": s,
            "total_notional": l + s,
            "long_liquidations": lc,
            "short_liquidations": sc,
            "total_liquidations": lc + sc,
        })
    return rows


class ForensicTests(unittest.TestCase):
    def test_exact_target_window_is_bounded(self):
        self.assertEqual(_fetch_window("2026-08-31"),(6,144))

    def test_exact_daily_vs_hourly_delta_reports_mismatch_and_match(self):
        daily=[
            daily_row("2026-08-26",100,200,1,2),
            daily_row("2026-08-27",50,70,2,3),
        ]
        hourly=(
            hourly_day("2026-08-26",long=90,short=210,long_count=1,short_count=2)
            + hourly_day("2026-08-27",long=50,short=70,long_count=2,short_count=3)
        )
        result=reconciliation_diagnostics(
            daily,
            hourly,
            observed_at_ms=1_788_000_000_000,
            current_date="2026-08-31",
        )
        self.assertEqual([item["date"] for item in result],["2026-08-26","2026-08-27"])
        self.assertEqual(result[0]["status"],"mismatch")
        self.assertEqual(result[0]["hourlyBucketCount"],24)
        self.assertEqual(result[0]["delta"],(1000,-1000,0,0,0,0))
        self.assertEqual(result[1]["status"],"match")
        self.assertEqual(result[1]["delta"],(0,0,0,0,0,0))

    def test_forensic_module_has_no_delivery_path(self):
        text=Path("collector/history_forensic.py").read_text()
        self.assertNotIn("collector.delivery",text)
        self.assertNotIn("deliver(",text)
        self.assertNotIn("HL_HISTORY_INGEST_ORIGIN",text)
        self.assertIn("READ_ONLY_EPHEMERAL_NO_DELIVERY",text)


if __name__ == "__main__":
    unittest.main()

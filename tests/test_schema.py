from __future__ import annotations
import unittest
from datetime import datetime,timedelta
from collector.asxn_schema import AsxnSchemaError,apply_hourly_reconciliation,normalize_daily_rows

class SchemaTests(unittest.TestCase):
    def _daily(self,date="2026-08-27",long="10.00",short="20.00",total="30.00"):
        return {"date":date,"long_notional":long,"short_notional":short,"total_notional":total,"long_liquidations":2,"short_liquidations":3,"total_liquidations":5}
    def _hourly(self,date="2026-08-27",long_delta="0.00"):
        base=datetime.fromisoformat(date+"T00:00:00+00:00"); rows=[]
        delta=float(long_delta)
        for i in range(24):
            long_value=1.0 if i<10 else 0.0; short_value=1.0 if i<20 else 0.0
            if i==0: long_value+=delta
            rows.append({"hour":(base+timedelta(hours=i)).isoformat().replace("+00:00","Z"),"long_notional":f"{long_value:.2f}","short_notional":f"{short_value:.2f}","total_notional":f"{long_value+short_value:.2f}","long_liquidations":1 if i<2 else 0,"short_liquidations":1 if 2<=i<5 else 0,"total_liquidations":1 if i<5 else 0})
        return rows
    def test_missing_money_is_not_zero(self):
        row=self._daily(); del row["long_notional"]
        with self.assertRaisesRegex(AsxnSchemaError,"LONG_MONEY_INVALID"): normalize_daily_rows([row],observed_at_ms=1,from_date="2026-08-25",to_date="2026-08-27")
    def test_total_mismatch_rejected(self):
        with self.assertRaisesRegex(AsxnSchemaError,"TOTAL_MONEY_MISMATCH"): normalize_daily_rows([self._daily(total="99")],observed_at_ms=1,from_date="2026-08-25",to_date="2026-08-27")
    def test_pre_seam_filtered_before_normalization(self):
        pre=self._daily(date="2026-08-24"); del pre["long_notional"]
        rows=normalize_daily_rows([pre,self._daily(date="2026-08-25")],observed_at_ms=1,from_date="2026-08-25",to_date="2026-08-25")
        self.assertEqual([r["date"] for r in rows],["2026-08-25"])
    def test_exact_24_hour_reconciliation_matches(self):
        daily=normalize_daily_rows([self._daily()],observed_at_ms=123,from_date="2026-08-27",to_date="2026-08-27")
        out=apply_hourly_reconciliation(daily,self._hourly(),current_date="2026-08-28")
        self.assertEqual(out[0]["reconciliationStatus"],"match"); self.assertEqual(out[0]["hourlyBucketCount"],24)
    def test_ten_dollar_reconciliation_delta_matches(self):
        daily=normalize_daily_rows([self._daily()],observed_at_ms=123,from_date="2026-08-27",to_date="2026-08-27")
        out=apply_hourly_reconciliation(daily,self._hourly(long_delta="10.00"),current_date="2026-08-28")
        self.assertEqual(out[0]["reconciliationStatus"],"match")
    def test_ten_dollars_and_one_cent_reconciliation_delta_mismatches(self):
        daily=normalize_daily_rows([self._daily()],observed_at_ms=123,from_date="2026-08-27",to_date="2026-08-27")
        out=apply_hourly_reconciliation(daily,self._hourly(long_delta="10.01"),current_date="2026-08-28")
        self.assertEqual(out[0]["reconciliationStatus"],"mismatch")
    def test_incomplete_hourly_stays_not_proven(self):
        daily=normalize_daily_rows([self._daily()],observed_at_ms=123,from_date="2026-08-27",to_date="2026-08-27")
        out=apply_hourly_reconciliation(daily,self._hourly()[:23],current_date="2026-08-28")
        self.assertEqual(out[0]["reconciliationStatus"],"not-proven")
    def test_count_mismatch_still_marks_mismatch(self):
        daily=normalize_daily_rows([self._daily()],observed_at_ms=123,from_date="2026-08-27",to_date="2026-08-27")
        hourly=self._hourly(); hourly[0]["long_liquidations"]=2; hourly[0]["total_liquidations"]=2
        out=apply_hourly_reconciliation(daily,hourly,current_date="2026-08-28")
        self.assertEqual(out[0]["reconciliationStatus"],"mismatch")
    def test_valid_hourly_large_money_mismatch_marks_mismatch(self):
        daily=normalize_daily_rows([self._daily()],observed_at_ms=123,from_date="2026-08-27",to_date="2026-08-27")
        out=apply_hourly_reconciliation(daily,self._hourly(long_delta="11.00"),current_date="2026-08-28")
        self.assertEqual(out[0]["reconciliationStatus"],"mismatch")
    def test_malformed_hourly_is_not_proven(self):
        daily=normalize_daily_rows([self._daily()],observed_at_ms=123,from_date="2026-08-27",to_date="2026-08-27"); hourly=self._hourly(); hourly[0]["total_notional"]="99.00"
        out=apply_hourly_reconciliation(daily,hourly,current_date="2026-08-28")
        self.assertEqual(out[0]["reconciliationStatus"],"not-proven")

if __name__ == "__main__": unittest.main()

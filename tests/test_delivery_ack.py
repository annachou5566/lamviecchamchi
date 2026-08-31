from __future__ import annotations

import unittest

from collector.delivery import normalize_delivery_ack


class DeliveryAckTests(unittest.TestCase):
    def test_dated_ack_preserves_per_row_reason(self):
        result=normalize_delivery_ack({
            "ok":True,
            "applied":True,
            "rows":[
                {"date":"2026-08-25","applied":True,"canonicalChanged":True,"reason":"inserted"},
                {"date":"2026-08-26","applied":False,"canonicalChanged":False,"reason":"closed-day-reconciliation-mismatch"},
            ],
            "reconciliationRejectedDates":["2026-08-26"],
        })
        self.assertTrue(result["ackDated"])
        self.assertEqual(result["reconciliationRejectedDates"],["2026-08-26"])
        self.assertEqual(result["rows"][1]["reason"],"closed-day-reconciliation-mismatch")

    def test_legacy_undated_ack_is_explicitly_not_dated(self):
        result=normalize_delivery_ack({
            "ok":True,
            "applied":True,
            "rows":[{"applied":True,"reason":"inserted"}],
        })
        self.assertTrue(result["applied"])
        self.assertFalse(result["ackDated"])
        self.assertEqual(result["rows"],[])
        self.assertEqual(result["reconciliationRejectedDates"],[])


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import unittest


class ForensicWorkflowTests(unittest.TestCase):
    def test_forensic_job_is_exact_branch_read_only_and_no_delivery(self):
        text=Path(".github/workflows/hyperliquid-asxn-history-collector.yml").read_text()
        marker="  forensic-26-27:\n"
        self.assertIn(marker,text)
        forensic=text.split(marker,1)[1]
        self.assertIn("refs/heads/chatgpt/hyperliquid-26-27-forensic-2026-08-31",forensic)
        self.assertIn("inputs.mode == 'oidc-qualification'",forensic)
        self.assertIn("permissions:\n      contents: read",forensic)
        self.assertIn("python -m collector.history_forensic",forensic)
        self.assertNotIn("HL_HISTORY_INGEST_ORIGIN",forensic)
        self.assertNotIn("collector.history_collector",forensic)
        self.assertNotIn("oidc_qualification.py",forensic)

    def test_production_collect_and_oidc_jobs_remain_main_only(self):
        text=Path(".github/workflows/hyperliquid-asxn-history-collector.yml").read_text()
        self.assertIn("github.ref == 'refs/heads/main' && inputs.mode != 'oidc-qualification'",text)
        self.assertIn("github.ref == 'refs/heads/main' && inputs.mode == 'oidc-qualification'",text)
        self.assertNotIn("push:",text)
        self.assertNotIn("schedule:",text)


if __name__ == "__main__":
    unittest.main()

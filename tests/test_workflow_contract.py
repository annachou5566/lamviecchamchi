from pathlib import Path
import unittest

class WorkflowContractTests(unittest.TestCase):
    def test_dispatch_only_and_inert_by_default(self):
        text=Path(".github/workflows/hyperliquid-asxn-history-collector.yml").read_text()
        self.assertIn("workflow_dispatch:",text); self.assertNotIn("schedule:",text); self.assertNotIn("push:",text); self.assertNotIn("pull_request_target:",text)
        self.assertIn("id-token: write",text); self.assertIn("vars.HL_HISTORY_EXECUTION_ENABLED == 'true'",text); self.assertNotIn("upload-artifact",text)

if __name__ == "__main__": unittest.main()

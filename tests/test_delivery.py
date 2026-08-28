from __future__ import annotations
import os,unittest
from unittest.mock import patch
from collector.delivery import DeliveryError,build_ingest_body,validate_ingest_origin

class DeliveryTests(unittest.TestCase):
    def test_origin_allowlist(self):
        self.assertEqual(validate_ingest_origin("https://wave-alpha-liquidation-coordinator.owner-subdomain.workers.dev"),"https://wave-alpha-liquidation-coordinator.owner-subdomain.workers.dev")
        for value in ("http://wave-alpha-liquidation-coordinator.x.workers.dev","https://evil.example.com","https://wave-alpha-liquidation-coordinator.x.workers.dev/other","https://wave-alpha-liquidation-coordinator.x.workers.dev?token=1"):
            with self.assertRaises(DeliveryError): validate_ingest_origin(value)
    def test_body_binds_github_identity(self):
        env={"GITHUB_RUN_ID":"123","GITHUB_RUN_ATTEMPT":"2","GITHUB_SHA":"a"*40,"GITHUB_REF":"refs/heads/main"}
        with patch.dict(os.environ,env,clear=False): body=build_ingest_body([],mode="rolling",revision_days=7)
        self.assertEqual((body["runId"],body["runAttempt"],body["workflowSha"]),("123","2","a"*40))
    def test_non_main_ref_fails_closed(self):
        env={"GITHUB_RUN_ID":"123","GITHUB_RUN_ATTEMPT":"1","GITHUB_SHA":"b"*40,"GITHUB_REF":"refs/heads/other"}
        with patch.dict(os.environ,env,clear=False):
            with self.assertRaisesRegex(DeliveryError,"GITHUB_REF_NOT_MAIN"): build_ingest_body([],mode="rolling",revision_days=7)

if __name__ == "__main__": unittest.main()

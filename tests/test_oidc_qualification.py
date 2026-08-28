from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from collector.oidc_qualification import OidcQualificationError, qualify, validate_qualification_origin


class _Response:
    status = 200
    def __init__(self, body: dict):
        self._raw = json.dumps(body).encode()
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self, _size: int):
        return self._raw


class OidcQualificationTests(unittest.TestCase):
    def test_origin_is_exact_test_worker_https_only(self):
        valid = "https://wave-alpha-hyperliquid-oidc-qualification.owner-subdomain.workers.dev"
        self.assertEqual(validate_qualification_origin(valid), valid)
        for value in (
            "http://wave-alpha-hyperliquid-oidc-qualification.x.workers.dev",
            "https://evil.example.com",
            "https://wave-alpha-hyperliquid-oidc-qualification.x.workers.dev/other",
            "https://wave-alpha-hyperliquid-oidc-qualification.x.workers.dev:8443",
        ):
            with self.assertRaises(OidcQualificationError):
                validate_qualification_origin(value)

    def test_result_is_bound_to_current_github_run(self):
        sha = "a" * 40
        body = {
            "ok": True,
            "contract": "HYPERLIQUID_HISTORY_OIDC_QUALIFICATION_V1",
            "wallMs": 4.25,
            "repositoryId": "1348466140",
            "repositoryOwnerId": "248262459",
            "refProtected": True,
            "workflowSha": sha,
            "runId": "123",
            "runAttempt": "2",
            "eventName": "workflow_dispatch",
            "runnerEnvironment": "github-hosted",
        }
        env = {"GITHUB_SHA": sha, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2"}
        with patch.dict(os.environ, env, clear=False), \
             patch("collector.oidc_qualification.request_oidc_token", return_value="secret-token"), \
             patch("collector.oidc_qualification.urlopen", return_value=_Response(body)):
            result = qualify("https://wave-alpha-hyperliquid-oidc-qualification.x.workers.dev")
        self.assertEqual(result["wallLe5Ms"], True)
        self.assertEqual(result["workflowSha"], sha)

    def test_ref_protection_false_fails_closed(self):
        sha = "b" * 40
        body = {
            "ok": True,
            "contract": "HYPERLIQUID_HISTORY_OIDC_QUALIFICATION_V1",
            "wallMs": 1.0,
            "repositoryId": "1348466140",
            "repositoryOwnerId": "248262459",
            "refProtected": False,
            "workflowSha": sha,
            "runId": "7",
            "runAttempt": "1",
            "eventName": "workflow_dispatch",
            "runnerEnvironment": "github-hosted",
        }
        env = {"GITHUB_SHA": sha, "GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "1"}
        with patch.dict(os.environ, env, clear=False), \
             patch("collector.oidc_qualification.request_oidc_token", return_value="secret-token"), \
             patch("collector.oidc_qualification.urlopen", return_value=_Response(body)):
            with self.assertRaisesRegex(OidcQualificationError, "QUALIFICATION_REF_NOT_PROTECTED"):
                qualify("https://wave-alpha-hyperliquid-oidc-qualification.x.workers.dev")


if __name__ == "__main__":
    unittest.main()

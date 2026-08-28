from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

OIDC_AUDIENCE = "urn:wave-alpha:liquidation:hyperliquid-history-ingest:v1"
QUALIFICATION_PATH = "/qualify"
QUALIFICATION_HEADER = "hyperliquid-oidc-v1"
MAX_RESPONSE_BYTES = 16 * 1024
_QUALIFICATION_HOST = re.compile(r"^wave-alpha-hyperliquid-oidc-qualification\.[a-z0-9-]+\.workers\.dev$")


class OidcQualificationError(RuntimeError):
    pass


def validate_qualification_origin(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise OidcQualificationError("QUALIFICATION_ORIGIN_INVALID")
    if parsed.path not in ("", "/") or parsed.params or parsed.query or parsed.fragment:
        raise OidcQualificationError("QUALIFICATION_ORIGIN_INVALID")
    try:
        port = parsed.port
    except ValueError as error:
        raise OidcQualificationError("QUALIFICATION_ORIGIN_INVALID") from error
    if port not in (None, 443):
        raise OidcQualificationError("QUALIFICATION_ORIGIN_PORT_INVALID")
    if not _QUALIFICATION_HOST.fullmatch(parsed.hostname.lower()):
        raise OidcQualificationError("QUALIFICATION_ORIGIN_NOT_ALLOWLISTED")
    return f"https://{parsed.hostname.lower()}"


def request_oidc_token() -> str:
    base = str(os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL", "")).strip()
    bearer = str(os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")).strip()
    if not base or not bearer:
        raise OidcQualificationError("OIDC_ENV_MISSING")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise OidcQualificationError("OIDC_REQUEST_URL_INVALID")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["audience"] = OIDC_AUDIENCE
    url = urlunparse(parsed._replace(query=urlencode(query)))
    request = Request(url, headers={"Authorization": f"Bearer {bearer}", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        raise OidcQualificationError("OIDC_TOKEN_REQUEST_FAILED") from error
    if len(raw) > MAX_RESPONSE_BYTES:
        raise OidcQualificationError("OIDC_TOKEN_RESPONSE_TOO_LARGE")
    try:
        token = str(json.loads(raw).get("value") or "").strip()
    except (json.JSONDecodeError, AttributeError) as error:
        raise OidcQualificationError("OIDC_TOKEN_RESPONSE_INVALID") from error
    if not token:
        raise OidcQualificationError("OIDC_TOKEN_MISSING")
    return token


def qualify(origin: str) -> dict:
    endpoint = validate_qualification_origin(origin) + QUALIFICATION_PATH
    token = request_oidc_token()
    request = Request(
        endpoint,
        data=b"",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Wave-Qualification": QUALIFICATION_HEADER,
            "Accept": "application/json",
            "Cache-Control": "no-store",
            "User-Agent": "wave-alpha-hyperliquid-oidc-qualification/1",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            status = int(response.status)
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        raise OidcQualificationError(f"QUALIFICATION_HTTP_{int(error.code)}") from error
    except (URLError, TimeoutError) as error:
        raise OidcQualificationError("QUALIFICATION_REQUEST_FAILED") from error
    if len(raw) > MAX_RESPONSE_BYTES:
        raise OidcQualificationError("QUALIFICATION_RESPONSE_TOO_LARGE")
    if status != 200:
        raise OidcQualificationError(f"QUALIFICATION_HTTP_{status}")
    try:
        result = json.loads(raw or b"{}")
    except json.JSONDecodeError as error:
        raise OidcQualificationError("QUALIFICATION_RESPONSE_INVALID") from error
    expected_sha = str(os.getenv("GITHUB_SHA", "")).strip().lower()
    expected_run = str(os.getenv("GITHUB_RUN_ID", "")).strip()
    expected_attempt = str(os.getenv("GITHUB_RUN_ATTEMPT", "")).strip()
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise OidcQualificationError("QUALIFICATION_REJECTED")
    if result.get("contract") != "HYPERLIQUID_HISTORY_OIDC_QUALIFICATION_V1":
        raise OidcQualificationError("QUALIFICATION_CONTRACT_MISMATCH")
    if str(result.get("repositoryId") or "") != "1348466140":
        raise OidcQualificationError("QUALIFICATION_REPOSITORY_ID_MISMATCH")
    if str(result.get("repositoryOwnerId") or "") != "248262459":
        raise OidcQualificationError("QUALIFICATION_OWNER_ID_MISMATCH")
    if result.get("refProtected") is not True:
        raise OidcQualificationError("QUALIFICATION_REF_NOT_PROTECTED")
    if str(result.get("workflowSha") or "").lower() != expected_sha:
        raise OidcQualificationError("QUALIFICATION_WORKFLOW_SHA_MISMATCH")
    if str(result.get("runId") or "") != expected_run:
        raise OidcQualificationError("QUALIFICATION_RUN_ID_MISMATCH")
    if str(result.get("runAttempt") or "") != expected_attempt:
        raise OidcQualificationError("QUALIFICATION_RUN_ATTEMPT_MISMATCH")
    if result.get("eventName") != "workflow_dispatch":
        raise OidcQualificationError("QUALIFICATION_EVENT_MISMATCH")
    if result.get("runnerEnvironment") != "github-hosted":
        raise OidcQualificationError("QUALIFICATION_RUNNER_MISMATCH")
    wall_ms = result.get("wallMs")
    if not isinstance(wall_ms, (int, float)) or wall_ms < 0:
        raise OidcQualificationError("QUALIFICATION_TIMING_INVALID")
    return {
        "ok": True,
        "wallMs": float(wall_ms),
        "wallLe5Ms": float(wall_ms) <= 5.0,
        "workflowSha": expected_sha,
        "runId": expected_run,
        "runAttempt": expected_attempt,
    }


def main() -> int:
    origin = str(os.getenv("HL_OIDC_QUALIFICATION_ORIGIN", "")).strip()
    if not origin:
        raise SystemExit("HL_OIDC_QUALIFICATION_ORIGIN_MISSING")
    try:
        result = qualify(origin)
    except OidcQualificationError as error:
        raise SystemExit(f"HL_OIDC_QUALIFICATION_FAIL code={error}") from error
    print(
        "HL_OIDC_QUALIFICATION_OK "
        f"wall_ms={result['wallMs']:.3f} wall_le_5ms={str(result['wallLe5Ms']).lower()} "
        f"run_id={result['runId']} run_attempt={result['runAttempt']} workflow_sha={result['workflowSha']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

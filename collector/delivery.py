from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

OIDC_AUDIENCE = "urn:wave-alpha:liquidation:hyperliquid-history-ingest:v1"
INGEST_PATH = "/ingest/hyperliquid-history"
MAX_RESPONSE_BYTES = 16 * 1024
_WORKER_HOST = re.compile(r"^wave-alpha-liquidation-coordinator\.[a-z0-9-]+\.workers\.dev$")

class DeliveryError(RuntimeError):
    pass

def validate_ingest_origin(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise DeliveryError("INGEST_ORIGIN_INVALID")
    if parsed.path not in ("", "/") or parsed.params or parsed.query or parsed.fragment:
        raise DeliveryError("INGEST_ORIGIN_INVALID")
    if not _WORKER_HOST.fullmatch(parsed.hostname.lower()):
        raise DeliveryError("INGEST_ORIGIN_NOT_ALLOWLISTED")
    port = f":{parsed.port}" if parsed.port else ""
    return f"https://{parsed.hostname.lower()}{port}"

def _github_identity() -> tuple[str,str,str]:
    run_id = str(os.getenv("GITHUB_RUN_ID","")).strip()
    run_attempt = str(os.getenv("GITHUB_RUN_ATTEMPT","")).strip()
    workflow_sha = str(os.getenv("GITHUB_SHA","")).strip().lower()
    ref = str(os.getenv("GITHUB_REF","")).strip()
    if not run_id.isdigit() or int(run_id) <= 0: raise DeliveryError("GITHUB_RUN_ID_INVALID")
    if not run_attempt.isdigit() or int(run_attempt) <= 0: raise DeliveryError("GITHUB_RUN_ATTEMPT_INVALID")
    if not re.fullmatch(r"[a-f0-9]{40}", workflow_sha): raise DeliveryError("GITHUB_SHA_INVALID")
    if ref != "refs/heads/main": raise DeliveryError("GITHUB_REF_NOT_MAIN")
    return run_id,run_attempt,workflow_sha

def build_ingest_body(rows: list[dict[str,Any]], *, mode: str, revision_days: int, seed_from: str|None=None, seed_to: str|None=None) -> dict[str,Any]:
    run_id,run_attempt,workflow_sha = _github_identity()
    body = {"mode":mode,"revisionDays":revision_days,"rows":rows,"runId":run_id,"runAttempt":run_attempt,"workflowSha":workflow_sha}
    if mode == "seed":
        body["seedFrom"] = str(seed_from or ""); body["seedTo"] = str(seed_to or "")
    return body

def _oidc_token() -> str:
    base = str(os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL","")).strip()
    bearer = str(os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN","")).strip()
    if not base or not bearer: raise DeliveryError("OIDC_ENV_MISSING")
    parsed = urlparse(base); query = dict(parse_qsl(parsed.query,keep_blank_values=True)); query["audience"] = OIDC_AUDIENCE
    url = urlunparse(parsed._replace(query=urlencode(query)))
    request = Request(url,headers={"Authorization":f"Bearer {bearer}","Accept":"application/json"})
    try:
        with urlopen(request,timeout=10) as response: raw = response.read(MAX_RESPONSE_BYTES+1)
    except (HTTPError,URLError,TimeoutError) as error: raise DeliveryError("OIDC_TOKEN_REQUEST_FAILED") from error
    if len(raw) > MAX_RESPONSE_BYTES: raise DeliveryError("OIDC_RESPONSE_TOO_LARGE")
    try: token = str(json.loads(raw).get("value") or "").strip()
    except (json.JSONDecodeError,AttributeError) as error: raise DeliveryError("OIDC_RESPONSE_INVALID") from error
    if not token: raise DeliveryError("OIDC_TOKEN_MISSING")
    return token

def deliver(body: dict[str,Any], *, ingest_origin: str) -> dict[str,Any]:
    origin = validate_ingest_origin(ingest_origin)
    payload = json.dumps(body,separators=(",",":"),sort_keys=True).encode()
    if len(payload) > 64*1024: raise DeliveryError("INGEST_BODY_TOO_LARGE")
    token = _oidc_token()
    request = Request(origin+INGEST_PATH,data=payload,method="POST",headers={"Authorization":f"Bearer {token}","Content-Type":"application/json","Accept":"application/json","Cache-Control":"no-store","User-Agent":"wave-alpha-hyperliquid-history/1"})
    try:
        with urlopen(request,timeout=15) as response:
            status = int(response.status); raw = response.read(MAX_RESPONSE_BYTES+1)
    except HTTPError as error: raise DeliveryError(f"INGEST_HTTP_{int(error.code)}") from error
    except (URLError,TimeoutError) as error: raise DeliveryError("INGEST_REQUEST_FAILED") from error
    if len(raw)>MAX_RESPONSE_BYTES: raise DeliveryError("INGEST_RESPONSE_TOO_LARGE")
    if status != 200: raise DeliveryError(f"INGEST_HTTP_{status}")
    try: result = json.loads(raw or b"{}")
    except json.JSONDecodeError as error: raise DeliveryError("INGEST_RESPONSE_INVALID") from error
    if not isinstance(result,dict) or result.get("ok") is not True: raise DeliveryError("INGEST_REJECTED")
    return {"ok":True,"applied":bool(result.get("applied"))}

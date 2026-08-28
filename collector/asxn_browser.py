from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright

HOME_URL = "https://hyperscreener.asxn.xyz/"
API_BASE = "https://api-hyperliquid.asxn.xyz/api"
FETCH_TIMEOUT_MS = 20_000
VERIFY_ATTEMPTS = 20
VERIFY_WAIT_MS = 1_500
MAX_JSON_BYTES = 2_000_000

_FETCH_JS = r"""
async ({url, timeoutMs}) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      credentials: 'include',
      cache: 'no-store',
      signal: controller.signal,
    });
    const text = await response.text();
    return {status: response.status, text};
  } catch (_) {
    return {status: 0, text: ''};
  } finally {
    clearTimeout(timer);
  }
}
"""


class AsxnBrowserError(RuntimeError):
    pass


class AsxnBrowserSession:
    """Ephemeral ASXN browser session. Nothing is persisted after context exit."""

    def __init__(self) -> None:
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._profile: Path | None = None

    def __enter__(self) -> "AsxnBrowserSession":
        chrome = (
            shutil.which("google-chrome")
            or shutil.which("chromium")
            or shutil.which("chromium-browser")
        )
        if not chrome:
            raise AsxnBrowserError("CHROMIUM_NOT_FOUND")
        self._profile = Path(tempfile.mkdtemp(prefix="wa-asxn-history-"))
        os.chmod(self._profile, 0o700)
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._profile),
            executable_path=chrome,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._verify()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._context is not None:
                self._context.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()
            if self._profile is not None:
                shutil.rmtree(self._profile, ignore_errors=True)
        self._context = None
        self._playwright = None
        self._page = None
        self._profile = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise AsxnBrowserError("BROWSER_NOT_READY")
        return self._page

    def _evaluate_fetch(self, url: str) -> tuple[int, Any]:
        result = self.page.evaluate(_FETCH_JS, {"url": url, "timeoutMs": FETCH_TIMEOUT_MS})
        if not isinstance(result, dict):
            raise AsxnBrowserError("ASXN_FETCH_INVALID_RESULT")
        status = int(result.get("status") or 0)
        text = str(result.get("text") or "")
        if len(text.encode("utf-8")) > MAX_JSON_BYTES:
            raise AsxnBrowserError("ASXN_RESPONSE_TOO_LARGE")
        if status != 200:
            raise AsxnBrowserError(f"ASXN_HTTP_{status}")
        try:
            return status, json.loads(text)
        except json.JSONDecodeError as error:
            raise AsxnBrowserError("ASXN_JSON_INVALID") from error

    def _verify(self) -> None:
        self.page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45_000)
        probe = f"{API_BASE}/node/liquidations/daily/stats?days=2"
        last_error = "ASXN_VERIFICATION_FAILED"
        for _ in range(VERIFY_ATTEMPTS):
            try:
                _, data = self._evaluate_fetch(probe)
                if rows_from_payload(data):
                    return
                last_error = "ASXN_VERIFICATION_EMPTY"
            except AsxnBrowserError as error:
                last_error = str(error)
                if last_error == "ASXN_HTTP_429":
                    break
            time.sleep(VERIFY_WAIT_MS / 1000)
        raise AsxnBrowserError(last_error)

    def fetch_daily(self, days: int) -> Any:
        if not isinstance(days, int) or days < 1 or days > 31:
            raise AsxnBrowserError("DAILY_DAYS_OUT_OF_BOUNDS")
        return self._evaluate_fetch(f"{API_BASE}/node/liquidations/daily/stats?days={days}")[1]

    def fetch_hourly(self, hours: int) -> Any:
        if not isinstance(hours, int) or hours < 1 or hours > 31 * 24:
            raise AsxnBrowserError("HOURLY_HOURS_OUT_OF_BOUNDS")
        return self._evaluate_fetch(f"{API_BASE}/node/liquidations/hourly/stats?hours={hours}")[1]


def rows_from_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("data", "stats", "items", "rows", "chart_data"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []

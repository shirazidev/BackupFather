"""Shared client for Telegram-compatible Bot APIs (sendDocument).

Telegram and Bale expose the same ``/bot<token>/sendDocument`` surface, so the
HTTP mechanics live here once. Provider-specific quirks (base URL, size limits,
captions) stay in the respective destination modules so they don't leak.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from backupfather.errors import DeliveryError
from backupfather.utils.logger import get_logger
from backupfather.utils.retry import with_retry

log = get_logger(__name__)


class BotApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        chat_id: str,
        timeout: float = 120.0,
        attempts: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self.chat_id = chat_id
        self.timeout = timeout
        self.attempts = attempts

    def _endpoint(self, method: str) -> str:
        return f"{self._base_url}/bot{self._token}/{method}"

    def send_document(self, file_path: Path, caption: str = "") -> dict[str, Any]:
        """Upload one document. Retries transient failures; raises on hard fail.

        The token is embedded in the URL, so error handling never echoes the URL.
        """

        @with_retry(attempts=self.attempts, exceptions=(requests.RequestException, DeliveryError))
        def _do() -> dict[str, Any]:
            data = {"chat_id": self.chat_id}
            if caption:
                data["caption"] = caption[:1024]  # bot API caption limit
            with open(file_path, "rb") as fh:
                files = {"document": (file_path.name, fh)}
                try:
                    resp = requests.post(
                        self._endpoint("sendDocument"),
                        data=data,
                        files=files,
                        timeout=self.timeout,
                    )
                except requests.RequestException as exc:
                    raise DeliveryError(f"bot API request failed: {exc}") from exc
            return self._parse(resp)

        return _do()

    def send_message(self, text: str) -> dict[str, Any]:
        """Send a short text message (used by notifiers, not for file delivery)."""

        @with_retry(attempts=self.attempts, exceptions=(requests.RequestException, DeliveryError))
        def _do() -> dict[str, Any]:
            try:
                resp = requests.post(
                    self._endpoint("sendMessage"),
                    data={"chat_id": self.chat_id, "text": text[:4096]},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise DeliveryError(f"bot API request failed: {exc}") from exc
            return self._parse(resp)

        return _do()

    @staticmethod
    def _parse(resp: requests.Response) -> dict[str, Any]:
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code != 200 or not payload.get("ok", False):
            desc = payload.get("description", resp.text[:200])
            raise DeliveryError(f"bot API error {resp.status_code}: {desc}")
        return payload

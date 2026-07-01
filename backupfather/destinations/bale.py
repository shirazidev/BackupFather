"""Bale destination — Bale Messenger exposes a Telegram-compatible Bot API.

Kept as its own module (not a Telegram subclass) so Bale-specific quirks stay
isolated:

* Base URL is ``https://tapi.bale.ai`` (not api.telegram.org).
* File-size limits are typically LOWER than Telegram's ~50 MB — verify current
  Bale docs before raising ``BALE_MAX_UPLOAD_MB``. Default is conservative.

The genuinely-shared HTTP mechanics come from :class:`BotApiClient`; the
chunking behaviour mirrors Telegram's but is re-expressed here rather than
inherited so a future Bale API divergence only touches this file.
"""

from __future__ import annotations

from backupfather.destinations.base import BackupDestination
from backupfather.destinations.bot_api import BotApiClient
from backupfather.models import BackupArtifact, DeliveryResult
from backupfather.utils.chunking import needs_split, split_file
from backupfather.utils.logger import get_logger

log = get_logger(__name__)

BALE_BASE_URL = "https://tapi.bale.ai"


class BaleDestination(BackupDestination):
    name = "bale"

    def __init__(
        self,
        *,
        token: str,
        chat_id: str,
        max_upload_mb: int = 50,
        base_url: str = BALE_BASE_URL,
    ) -> None:
        self._client = BotApiClient(base_url=base_url, token=token, chat_id=chat_id)
        self.max_upload_bytes = max_upload_mb * 1024 * 1024

    def deliver(self, artifact: BackupArtifact, caption: str) -> DeliveryResult:
        if needs_split(artifact.size_bytes, self.max_upload_bytes):
            return self._deliver_chunked(artifact, caption)
        self._client.send_document(artifact.path, caption)
        log.info("%s: sent %s", self.name, artifact.path.name)
        return DeliveryResult(destination=self.name, ok=True, detail="sent")

    def _deliver_chunked(self, artifact: BackupArtifact, caption: str) -> DeliveryResult:
        log.warning(
            "%s: %s is %.1f MB > %d MB limit; splitting into parts",
            self.name,
            artifact.path.name,
            artifact.size_mb,
            self.max_upload_bytes // (1024 * 1024),
        )
        sent = 0
        for part in split_file(artifact.path, self.max_upload_bytes):
            try:
                self._client.send_document(part.path, f"{caption}\npart {part.index}/{part.total}")
                sent += 1
            finally:
                part.path.unlink(missing_ok=True)
        log.info("%s: sent %d parts for %s", self.name, sent, artifact.path.name)
        return DeliveryResult(destination=self.name, ok=True, detail=f"sent in {sent} parts")

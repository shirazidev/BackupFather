"""Abstract backup destination interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backupfather.models import BackupArtifact, DeliveryResult


class BackupDestination(ABC):
    """Delivers a finished artifact somewhere (chat, mailbox, disk, ...).

    Implementations should raise :class:`~backupfather.errors.DeliveryError` on
    hard failures; the runner records the outcome as a :class:`DeliveryResult`
    and continues with the remaining destinations.
    """

    #: Stable identifier used in config (``DESTINATIONS=...``) and logs.
    name: str = "base"

    @abstractmethod
    def deliver(self, artifact: BackupArtifact, caption: str) -> DeliveryResult:
        """Deliver ``artifact``. ``caption`` is a short human-readable summary."""
        raise NotImplementedError

    def supports_remote_retention(self) -> bool:
        """Whether this destination can list/delete old backups remotely."""
        return False

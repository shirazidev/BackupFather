"""Abstract notifier interface (separate from delivery destinations)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backupfather.models import BackupResult


class Notifier(ABC):
    """Sends a short status message, independent of where the backup went."""

    name: str = "base"

    @abstractmethod
    def notify_success(self, result: BackupResult) -> None:
        raise NotImplementedError

    @abstractmethod
    def notify_failure(self, result: BackupResult) -> None:
        raise NotImplementedError

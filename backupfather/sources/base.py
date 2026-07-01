"""Abstract backup source interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from backupfather.models import BackupArtifact


class BackupSource(ABC):
    """Produces a raw backup artifact for a single logical dataset.

    Implementations must not swallow failures: a non-zero result from the
    underlying tool must raise (never return a partial/corrupt artifact).
    """

    #: File extension for the produced (uncompressed) artifact, incl. leading dot.
    extension: str = ".dump"

    @abstractmethod
    def dump(self, dest_dir: Path) -> BackupArtifact:
        """Produce the backup file inside ``dest_dir`` and return its metadata."""
        raise NotImplementedError

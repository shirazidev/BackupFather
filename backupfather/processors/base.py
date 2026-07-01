"""Abstract post-dump processor (compression, encryption, ...)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backupfather.models import BackupArtifact


class BackupProcessor(ABC):
    """Transforms an artifact into a new artifact (e.g. compress then encrypt).

    Processors are chained; each consumes the previous artifact and produces a
    new one. Implementations should remove their input file after a successful
    transform to avoid leaving intermediate copies on disk.
    """

    @abstractmethod
    def process(self, artifact: BackupArtifact) -> BackupArtifact:
        raise NotImplementedError

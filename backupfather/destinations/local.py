"""Local-disk destination — keeps the artifact in the backup directory.

Because sources already write into ``LOCAL_BACKUP_DIR``, this destination is a
no-op copy in the common case, but it lets "local" be treated uniformly as a
first-class destination (e.g. as an oversized-file fallback for chat channels).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from backupfather.destinations.base import BackupDestination
from backupfather.models import BackupArtifact, DeliveryResult
from backupfather.utils.logger import get_logger

log = get_logger(__name__)


class LocalDestination(BackupDestination):
    name = "local"

    def __init__(self, backup_dir: Path) -> None:
        self.backup_dir = backup_dir

    def deliver(self, artifact: BackupArtifact, caption: str) -> DeliveryResult:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        target = self.backup_dir / artifact.path.name
        if artifact.path.resolve() != target.resolve():
            shutil.copy2(artifact.path, target)
            log.info("copied backup to local dir %s", target)
        else:
            log.info("backup already in local dir %s", target)
        return DeliveryResult(destination=self.name, ok=True, detail=str(target))

    def supports_remote_retention(self) -> bool:
        # Local files are cleaned by the retention module directly.
        return False

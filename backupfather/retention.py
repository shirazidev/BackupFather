"""Local backup retention.

Applies age-based (``RETENTION_DAYS``) and/or count-based (``RETENTION_COUNT``)
cleanup to the local backup directory. Only files whose names match a known
database prefix are ever considered, so unrelated files are never deleted.

Remote destinations (Telegram/Bale/Email) do not expose a list/delete API, so
remote retention is out of scope — see the README's "Known limitations".
"""

from __future__ import annotations

import time
from pathlib import Path

from backupfather.utils.logger import get_logger
from backupfather.utils.naming import sanitize

log = get_logger(__name__)


def _backups_for(backup_dir: Path, db_name: str) -> list[Path]:
    prefix = f"{sanitize(db_name)}_"
    return sorted(
        (p for p in backup_dir.glob(f"{prefix}*") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )


def apply_retention(
    backup_dir: Path,
    db_name: str,
    *,
    retention_days: int | None,
    retention_count: int | None,
    now: float | None = None,
) -> list[Path]:
    """Delete stale local backups for ``db_name``; return the deleted paths.

    A file is deleted if it is older than ``retention_days`` OR falls outside the
    newest ``retention_count``. The newest backup is always kept regardless.
    """
    if not backup_dir.exists():
        return []
    now = now if now is not None else time.time()
    backups = _backups_for(backup_dir, db_name)
    if len(backups) <= 1:
        return []  # never delete the only/most-recent backup

    to_delete: set[Path] = set()

    if retention_days is not None and retention_days > 0:
        cutoff = now - retention_days * 86400
        to_delete.update(p for p in backups if p.stat().st_mtime < cutoff)

    if retention_count is not None and retention_count >= 1:
        # backups sorted oldest->newest; keep the last `retention_count`.
        to_delete.update(backups[:-retention_count])

    # Always retain the most recent backup even if a policy would remove it.
    to_delete.discard(backups[-1])

    deleted: list[Path] = []
    for path in sorted(to_delete):
        try:
            path.unlink()
            deleted.append(path)
            log.info("retention: deleted old backup %s", path.name)
        except OSError as exc:
            log.warning("retention: failed to delete %s: %s", path.name, exc)
    return deleted

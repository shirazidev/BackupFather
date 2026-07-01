"""Tests for local retention policy."""

from __future__ import annotations

import os
import time
from pathlib import Path

from backupfather.retention import apply_retention


def _make_backup(backup_dir: Path, name: str, age_days: float) -> Path:
    p = backup_dir / name
    p.write_bytes(b"x")
    mtime = time.time() - age_days * 86400
    os.utime(p, (mtime, mtime))
    return p


def test_age_based_deletes_old_keeps_new(tmp_path: Path) -> None:
    old = _make_backup(tmp_path, "main_2026-06-01T00-00-00Z.dump.gz", age_days=30)
    new = _make_backup(tmp_path, "main_2026-07-01T00-00-00Z.dump.gz", age_days=1)

    deleted = apply_retention(tmp_path, "main", retention_days=14, retention_count=None)

    assert deleted == [old]
    assert not old.exists()
    assert new.exists()


def test_count_based_keeps_newest_n(tmp_path: Path) -> None:
    files = [
        _make_backup(tmp_path, f"main_2026-06-0{i}T00-00-00Z.dump.gz", age_days=10 - i)
        for i in range(1, 6)
    ]
    deleted = apply_retention(tmp_path, "main", retention_days=None, retention_count=2)

    # 5 backups, keep newest 2 -> delete oldest 3.
    assert len(deleted) == 3
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == [files[3].name, files[4].name]


def test_never_deletes_only_backup(tmp_path: Path) -> None:
    _make_backup(tmp_path, "main_2026-01-01T00-00-00Z.dump.gz", age_days=999)
    deleted = apply_retention(tmp_path, "main", retention_days=1, retention_count=1)
    assert deleted == []
    assert len(list(tmp_path.iterdir())) == 1


def test_only_touches_matching_db_prefix(tmp_path: Path) -> None:
    keep = _make_backup(tmp_path, "other_2026-01-01T00-00-00Z.dump.gz", age_days=999)
    _make_backup(tmp_path, "main_2026-01-01T00-00-00Z.dump.gz", age_days=999)
    _make_backup(tmp_path, "main_2026-07-01T00-00-00Z.dump.gz", age_days=1)

    apply_retention(tmp_path, "main", retention_days=14, retention_count=None)
    assert keep.exists()  # unrelated db untouched

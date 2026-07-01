"""Tests for compression processors (real gzip, small payload)."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from backupfather.errors import ProcessorError
from backupfather.models import BackupArtifact
from backupfather.processors.compress import GzipCompressor


def _artifact(path: Path) -> BackupArtifact:
    return BackupArtifact(
        db_name="db", path=path, size_bytes=path.stat().st_size, created_at="2026-07-01T00:00:00Z"
    )


def test_gzip_roundtrip(tmp_path: Path) -> None:
    payload = b"the godfather offers your bytes a deal\n" * 100
    src = tmp_path / "db.dump"
    src.write_bytes(payload)

    out = GzipCompressor(level=6).process(_artifact(src))

    assert out.path.name == "db.dump.gz"
    assert out.path.exists()
    assert not src.exists()  # intermediate removed
    assert gzip.decompress(out.path.read_bytes()) == payload
    assert out.size_bytes == out.path.stat().st_size


def test_gzip_rejects_bad_level() -> None:
    with pytest.raises(ProcessorError):
        GzipCompressor(level=15)


def test_gzip_rejects_directory(tmp_path: Path) -> None:
    d = tmp_path / "db.dumpdir"
    d.mkdir()
    with pytest.raises(ProcessorError):
        GzipCompressor().process(_artifact(d))

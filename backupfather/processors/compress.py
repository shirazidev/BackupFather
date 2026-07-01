"""Compression processors (gzip built-in, zstd optional)."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

from backupfather.errors import ProcessorError
from backupfather.models import BackupArtifact
from backupfather.processors.base import BackupProcessor
from backupfather.utils.logger import get_logger

log = get_logger(__name__)

_CHUNK = 1024 * 1024  # 1 MiB streaming chunks — never load the dump into memory


class GzipCompressor(BackupProcessor):
    def __init__(self, level: int = 6) -> None:
        if not 1 <= level <= 9:
            raise ProcessorError("gzip level must be between 1 and 9")
        self.level = level

    def process(self, artifact: BackupArtifact) -> BackupArtifact:
        if artifact.path.is_dir():
            raise ProcessorError("gzip cannot compress a directory-format dump; use zstd/none")
        out_path = artifact.path.with_suffix(artifact.path.suffix + ".gz")
        log.info("gzip-compressing %s (level=%d)", artifact.path.name, self.level)
        try:
            with (
                open(artifact.path, "rb") as src,
                gzip.open(out_path, "wb", compresslevel=self.level) as dst,
            ):
                shutil.copyfileobj(src, dst, _CHUNK)
        except OSError as exc:
            _safe_unlink(out_path)
            raise ProcessorError(f"gzip compression failed: {exc}") from exc

        _safe_unlink(artifact.path)
        return _replace_file(artifact, out_path)


class ZstdCompressor(BackupProcessor):
    def __init__(self, level: int = 6) -> None:
        self.level = level

    def process(self, artifact: BackupArtifact) -> BackupArtifact:
        try:
            import zstandard  # noqa: PLC0415 - optional dependency, imported lazily
        except ImportError as exc:  # pragma: no cover - exercised only without extra
            raise ProcessorError(
                "zstd compression requires the 'zstandard' package (pip install backupfather[zstd])"
            ) from exc

        if artifact.path.is_dir():
            raise ProcessorError("zstd cannot compress a directory-format dump directly")
        out_path = artifact.path.with_suffix(artifact.path.suffix + ".zst")
        log.info("zstd-compressing %s (level=%d)", artifact.path.name, self.level)
        cctx = zstandard.ZstdCompressor(level=self.level)
        try:
            with open(artifact.path, "rb") as src, open(out_path, "wb") as dst:
                cctx.copy_stream(src, dst)
        except OSError as exc:
            _safe_unlink(out_path)
            raise ProcessorError(f"zstd compression failed: {exc}") from exc

        _safe_unlink(artifact.path)
        return _replace_file(artifact, out_path)


def _replace_file(artifact: BackupArtifact, new_path: Path) -> BackupArtifact:
    return BackupArtifact(
        db_name=artifact.db_name,
        path=new_path,
        size_bytes=new_path.stat().st_size,
        created_at=artifact.created_at,
    )


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        log.warning("failed to remove intermediate file %s", path)

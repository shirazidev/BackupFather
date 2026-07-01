"""PostgreSQL backup source wrapping ``pg_dump``."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from backupfather.config import DumpFormat
from backupfather.errors import SourceError
from backupfather.models import BackupArtifact
from backupfather.sources.base import BackupSource
from backupfather.utils.logger import get_logger
from backupfather.utils.naming import build_filename

log = get_logger(__name__)

# Map dump format -> (pg_dump flag, file extension). directory format is a dir.
_FORMAT_FLAGS: dict[DumpFormat, tuple[str, str]] = {
    DumpFormat.custom: ("-Fc", ".dump"),
    DumpFormat.plain: ("-Fp", ".sql"),
    DumpFormat.directory: ("-Fd", ".dumpdir"),
}


class PostgresSource(BackupSource):
    """Dump a single Postgres database via ``pg_dump``.

    The DSN is passed to pg_dump via ``--dbname`` and never logged.
    """

    def __init__(
        self,
        *,
        db_name: str,
        dsn: str,
        dump_format: DumpFormat = DumpFormat.custom,
        timeout_seconds: int = 3600,
        pg_dump_bin: str = "pg_dump",
    ) -> None:
        self.db_name = db_name
        self._dsn = dsn
        self.dump_format = dump_format
        self.timeout_seconds = timeout_seconds
        self.pg_dump_bin = pg_dump_bin
        _, self.extension = _FORMAT_FLAGS[dump_format]

    def _build_command(self, out_path: Path) -> list[str]:
        flag, _ = _FORMAT_FLAGS[self.dump_format]
        return [
            self.pg_dump_bin,
            flag,
            "--no-password",  # never prompt interactively
            "--file",
            str(out_path),
            "--dbname",
            self._dsn,
        ]

    def dump(self, dest_dir: Path) -> BackupArtifact:
        dest_dir.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now(tz=UTC)
        out_path = dest_dir / build_filename(self.db_name, self.extension, created_at)

        log.info("dumping database %s (format=%s)", self.db_name, self.dump_format.value)
        try:
            result = subprocess.run(  # noqa: S603 - trusted binary, args are not shell
                self._build_command(out_path),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise SourceError(f"pg_dump binary not found: {self.pg_dump_bin}") from exc
        except subprocess.TimeoutExpired as exc:
            self._cleanup(out_path)
            raise SourceError(
                f"pg_dump timed out after {self.timeout_seconds}s for {self.db_name}"
            ) from exc

        if result.returncode != 0:
            self._cleanup(out_path)
            stderr = (result.stderr or "").strip()
            log.error("pg_dump failed for %s: %s", self.db_name, stderr)
            raise SourceError(
                f"pg_dump exited {result.returncode} for {self.db_name}: {stderr[-500:]}"
            )

        if not out_path.exists():
            raise SourceError(f"pg_dump reported success but produced no file for {self.db_name}")

        size = self._path_size(out_path)
        log.info("dumped %s -> %s (%.2f MB)", self.db_name, out_path.name, size / (1024 * 1024))
        return BackupArtifact(
            db_name=self.db_name,
            path=out_path,
            size_bytes=size,
            created_at=created_at.isoformat(),
        )

    @staticmethod
    def _path_size(path: Path) -> int:
        if path.is_dir():
            return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        return path.stat().st_size

    @staticmethod
    def _cleanup(path: Path) -> None:
        try:
            if path.is_dir():
                for p in sorted(path.rglob("*"), reverse=True):
                    p.unlink() if p.is_file() else p.rmdir()
                path.rmdir()
            elif path.exists():
                path.unlink()
        except OSError:
            log.warning("failed to clean up partial dump at %s", path)

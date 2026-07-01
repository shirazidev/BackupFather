"""Optional encryption processors.

Both methods shell out to ``gpg`` so we never hand-roll cryptography:

* GPG public-key: ``gpg --encrypt --recipient <id>`` (asymmetric).
* AES-256: ``gpg --symmetric --cipher-algo AES256`` with a passphrase.

The passphrase is passed to gpg via a file descriptor, never on the command
line (which would leak it in the process list) and never logged.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from backupfather.errors import ProcessorError
from backupfather.models import BackupArtifact
from backupfather.processors.base import BackupProcessor
from backupfather.utils.logger import get_logger

log = get_logger(__name__)


class GpgPublicKeyEncryptor(BackupProcessor):
    def __init__(self, recipient: str, gpg_bin: str = "gpg") -> None:
        if not recipient:
            raise ProcessorError("GPG recipient is required for public-key encryption")
        self.recipient = recipient
        self.gpg_bin = gpg_bin

    def process(self, artifact: BackupArtifact) -> BackupArtifact:
        out_path = artifact.path.with_suffix(artifact.path.suffix + ".gpg")
        cmd = [
            self.gpg_bin,
            "--batch",
            "--yes",
            "--trust-model",
            "always",
            "--recipient",
            self.recipient,
            "--output",
            str(out_path),
            "--encrypt",
            str(artifact.path),
        ]
        log.info("gpg-encrypting %s for recipient %s", artifact.path.name, self.recipient)
        _run_gpg(cmd, out_path)
        _safe_unlink(artifact.path)
        return _replace_file(artifact, out_path)


class AesEncryptor(BackupProcessor):
    def __init__(self, passphrase: str, gpg_bin: str = "gpg") -> None:
        if not passphrase:
            raise ProcessorError("AES passphrase is required")
        self._passphrase = passphrase
        self.gpg_bin = gpg_bin

    def process(self, artifact: BackupArtifact) -> BackupArtifact:
        out_path = artifact.path.with_suffix(artifact.path.suffix + ".gpg")
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, self._passphrase.encode())
        finally:
            os.close(write_fd)
        cmd = [
            self.gpg_bin,
            "--batch",
            "--yes",
            "--symmetric",
            "--cipher-algo",
            "AES256",
            "--passphrase-fd",
            str(read_fd),
            "--output",
            str(out_path),
            str(artifact.path),
        ]
        log.info("aes-256-encrypting %s", artifact.path.name)
        try:
            _run_gpg(cmd, out_path, pass_fds=(read_fd,))
        finally:
            os.close(read_fd)
        _safe_unlink(artifact.path)
        return _replace_file(artifact, out_path)


def _run_gpg(cmd: list[str], out_path: Path, pass_fds: tuple[int, ...] = ()) -> None:
    try:
        result = subprocess.run(  # noqa: S603 - trusted binary, args not shell-parsed
            cmd,
            capture_output=True,
            text=True,
            check=False,
            pass_fds=pass_fds,
        )
    except FileNotFoundError as exc:
        raise ProcessorError("gpg binary not found; install gnupg to use encryption") from exc
    if result.returncode != 0:
        _safe_unlink(out_path)
        raise ProcessorError(f"gpg encryption failed: {(result.stderr or '').strip()[-500:]}")
    if not out_path.exists():
        raise ProcessorError("gpg reported success but produced no output file")


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

"""Tests for PostgresSource with pg_dump mocked (never hits a real DB)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backupfather.config import DumpFormat
from backupfather.errors import SourceError
from backupfather.sources.postgres import PostgresSource


def _make_source(**kw: object) -> PostgresSource:
    defaults: dict[str, object] = {
        "db_name": "main",
        "dsn": "postgres://u:p@h:5432/main",
        "dump_format": DumpFormat.custom,
    }
    defaults.update(kw)
    return PostgresSource(**defaults)  # type: ignore[arg-type]


def test_command_uses_dbname_not_shell(tmp_path: Path) -> None:
    src = _make_source()
    cmd = src._build_command(tmp_path / "out.dump")
    assert cmd[0] == "pg_dump"
    assert "-Fc" in cmd
    assert "--dbname" in cmd
    assert "postgres://u:p@h:5432/main" in cmd  # passed as arg, never via shell


def test_dump_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        # pg_dump writes the --file target; emulate it.
        out = Path(cmd[cmd.index("--file") + 1])
        out.write_bytes(b"PGDMP fake dump")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    artifact = _make_source().dump(tmp_path)

    assert artifact.db_name == "main"
    assert artifact.path.exists()
    assert artifact.path.suffix == ".dump"
    assert artifact.size_bytes == len(b"PGDMP fake dump")


def test_dump_nonzero_exit_raises_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        out = Path(cmd[cmd.index("--file") + 1])
        out.write_bytes(b"partial")  # partial file must be removed
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="FATAL: role does not exist")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SourceError, match="exited 1"):
        _make_source().dump(tmp_path)

    assert list(tmp_path.iterdir()) == []  # no partial/corrupt file left behind


def test_dump_missing_binary_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SourceError, match="not found"):
        _make_source().dump(tmp_path)


def test_dump_timeout_raises_and_cleans_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        out = Path(cmd[cmd.index("--file") + 1])
        out.write_bytes(b"partial")
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SourceError, match="timed out"):
        _make_source(timeout_seconds=1).dump(tmp_path)
    assert list(tmp_path.iterdir()) == []

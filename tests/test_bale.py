"""Tests for the Bale destination (HTTP mocked)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backupfather.destinations.bale import BALE_BASE_URL, BaleDestination
from backupfather.destinations.bot_api import BotApiClient
from backupfather.models import BackupArtifact


def _artifact(path: Path, size: int) -> BackupArtifact:
    return BackupArtifact(
        db_name="db", path=path, size_bytes=size, created_at="2026-07-01T00:00:00Z"
    )


def test_bale_uses_its_own_base_url() -> None:
    dest = BaleDestination(token="t", chat_id="1")
    assert dest._client._base_url == BALE_BASE_URL
    assert "bale.ai" in BALE_BASE_URL


def test_bale_small_file_single_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "db.dump.gz"
    f.write_bytes(b"x" * 10)
    calls: list[Path] = []
    monkeypatch.setattr(
        BotApiClient, "send_document", lambda self, path, caption="": calls.append(path)
    )
    result = BaleDestination(token="t", chat_id="1").deliver(_artifact(f, 10), "cap")
    assert result.ok
    assert calls == [f]


def test_bale_oversized_is_chunked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "db.dump.gz"
    f.write_bytes(b"z" * 2500)
    sent: list[str] = []
    monkeypatch.setattr(
        BotApiClient, "send_document", lambda self, path, caption="": sent.append(caption)
    )
    dest = BaleDestination(token="t", chat_id="1")
    dest.max_upload_bytes = 1000
    result = dest.deliver(_artifact(f, 2500), "cap")
    assert result.ok
    assert len(sent) == 3
    assert list(tmp_path.glob("*.part*")) == []

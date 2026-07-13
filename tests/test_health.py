"""Tests for the health state and HTTP endpoint."""

from __future__ import annotations

import json
from pathlib import Path

from backupfather.health import HealthState, render
from backupfather.models import BackupArtifact, BackupResult, Step


def _ok() -> BackupResult:
    art = BackupArtifact(
        db_name="main", path=Path("/x/m.gz"), size_bytes=1024 * 1024, created_at="t"
    )
    return BackupResult(db_name="main", ok=True, duration_seconds=2.0, artifact=art)


def _fail() -> BackupResult:
    return BackupResult(db_name="main", ok=False, duration_seconds=1.0, failed_step=Step.DUMP)


def test_snapshot_starting_before_first_run() -> None:
    # No backup has run yet -> "starting", not "degraded".
    snap = HealthState().snapshot()
    assert snap["status"] == "starting"
    assert snap["databases"] == {}


def test_render_starting_returns_200() -> None:
    code, body = render(HealthState(), "/healthz")
    assert code == 200
    assert json.loads(body)["status"] == "starting"


def test_snapshot_ok() -> None:
    state = HealthState()
    state.record(_ok())
    snap = state.snapshot()
    assert snap["status"] == "ok"
    assert snap["databases"]["main"]["ok"] is True


def test_snapshot_degraded_on_failure() -> None:
    state = HealthState()
    state.record(_fail())
    snap = state.snapshot()
    assert snap["status"] == "degraded"
    assert snap["databases"]["main"]["failed_step"] == "dump"


def test_render_healthz_ok() -> None:
    state = HealthState()
    state.record(_ok())
    code, body = render(state, "/healthz")
    assert code == 200
    assert json.loads(body)["status"] == "ok"


def test_render_healthz_degraded_returns_503() -> None:
    state = HealthState()
    state.record(_fail())
    code, _ = render(state, "/healthz")
    assert code == 503


def test_render_unknown_path_404() -> None:
    code, _ = render(HealthState(), "/nope")
    assert code == 404

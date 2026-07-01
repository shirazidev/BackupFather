"""Shared domain models passed between the pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Step(StrEnum):
    """Pipeline step, used for failure reporting."""

    CONFIG = "config"
    DUMP = "dump"
    COMPRESS = "compress"
    ENCRYPT = "encrypt"
    DELIVER = "deliver"
    RETENTION = "retention"
    NOTIFY = "notify"


@dataclass
class BackupArtifact:
    """A produced backup file on local disk, ready for delivery."""

    db_name: str
    path: Path
    size_bytes: int
    created_at: str  # ISO-8601 UTC string

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


@dataclass
class DeliveryResult:
    """Outcome of one destination delivering one artifact."""

    destination: str
    ok: bool
    detail: str = ""


@dataclass
class BackupResult:
    """Aggregate outcome of a single database's backup run."""

    db_name: str
    ok: bool
    duration_seconds: float
    artifact: BackupArtifact | None = None
    failed_step: Step | None = None
    error_summary: str = ""
    deliveries: list[DeliveryResult] = field(default_factory=list)

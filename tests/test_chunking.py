"""Tests for file splitting / size-limit logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from backupfather.utils.chunking import needs_split, part_count, split_file


def test_needs_split() -> None:
    assert needs_split(101, 100)
    assert not needs_split(100, 100)


@pytest.mark.parametrize(
    ("size", "limit", "expected"),
    [(0, 100, 1), (100, 100, 1), (101, 100, 2), (250, 100, 3), (300, 100, 3)],
)
def test_part_count(size: int, limit: int, expected: int) -> None:
    assert part_count(size, expected if False else limit) == expected


def test_split_file_reassembles(tmp_path: Path) -> None:
    payload = bytes(range(256)) * 20  # 5120 bytes
    src = tmp_path / "big.dump.gz"
    src.write_bytes(payload)

    parts = list(split_file(src, max_bytes=1000))

    assert len(parts) == 6  # ceil(5120/1000)
    assert [p.index for p in parts] == [1, 2, 3, 4, 5, 6]
    assert all(p.total == 6 for p in parts)
    for p in parts[:-1]:
        assert p.path.stat().st_size == 1000
    # Reassembly must equal the original.
    joined = b"".join(p.path.read_bytes() for p in parts)
    assert joined == payload


def test_split_rejects_bad_limit(tmp_path: Path) -> None:
    src = tmp_path / "x"
    src.write_bytes(b"abc")
    with pytest.raises(ValueError):
        list(split_file(src, max_bytes=0))

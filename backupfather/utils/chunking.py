"""Split oversized files into numbered parts for size-limited upload APIs."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_READ = 1024 * 1024  # 1 MiB streaming read


@dataclass(frozen=True)
class FilePart:
    path: Path
    index: int  # 1-based
    total: int


def needs_split(size_bytes: int, max_bytes: int) -> bool:
    return size_bytes > max_bytes


def part_count(size_bytes: int, max_bytes: int) -> int:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    # Ceiling division.
    return max(1, (size_bytes + max_bytes - 1) // max_bytes)


def split_file(path: Path, max_bytes: int) -> Iterator[FilePart]:
    """Yield numbered part files (``<name>.partNN`` of total M) no larger than
    ``max_bytes``. Parts are written next to the source; the caller is
    responsible for deleting them after use.
    """
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    total = part_count(path.stat().st_size, max_bytes)
    width = max(2, len(str(total)))

    with open(path, "rb") as src:
        for index in range(1, total + 1):
            part_path = path.with_name(f"{path.name}.part{index:0{width}d}of{total}")
            written = 0
            with open(part_path, "wb") as dst:
                while written < max_bytes:
                    chunk = src.read(min(_READ, max_bytes - written))
                    if not chunk:
                        break
                    dst.write(chunk)
                    written += len(chunk)
            yield FilePart(path=part_path, index=index, total=total)

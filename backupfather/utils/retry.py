"""Exponential-backoff retry decorator for flaky external calls."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import TypeVar

from backupfather.utils.logger import get_logger

log = get_logger(__name__)

T = TypeVar("T")


def with_retry(
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry ``func`` with exponential backoff.

    Raises the last exception if all attempts fail. ``attempts`` counts total
    tries (not extra retries), so ``attempts=1`` disables retrying.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: object, **kwargs: object) -> T:
            delay = base_delay
            last_exc: BaseException | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # noqa: PERF203 - retry needs the try in loop
                    last_exc = exc
                    if attempt >= attempts:
                        break
                    log.warning(
                        "%s failed (attempt %d/%d): %s; retrying in %.1fs",
                        getattr(func, "__name__", "call"),
                        attempt,
                        attempts,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)
            assert last_exc is not None  # loop always sets it before breaking
            raise last_exc

        return wrapper

    return decorator

"""
utils/retry.py
--------------
A single retry decorator so clarify.py, task decomposer, and any
future LLM-calling utility don't each duplicate try/sleep/raise logic.
"""

import time
import functools
from typing import Callable, TypeVar, Any
from utils.logger import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def with_retries(
    retries: int = 3,
    delay:   float = 2.0,
    exceptions: tuple = (Exception,),
    fallback: Any = None,
    raise_on_exhaustion: bool = True,
):
    """
    Decorator factory.

    Args:
        retries:              Maximum number of attempts (including the first).
        delay:                Seconds to wait between attempts.
        exceptions:           Exception types to catch and retry on.
        fallback:             Value to return if all attempts fail AND
                              raise_on_exhaustion is False.
        raise_on_exhaustion:  If True, re-raises the last exception after all
                              retries are exhausted.  If False, returns fallback.

    Usage:
        @with_retries(retries=3, delay=2.0, fallback=False)
        def is_goal_clear(goal: str) -> bool:
            ...
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Exception = RuntimeError("No attempts made")
            for attempt in range(1, retries + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    logger.warning(
                        "%s attempt %d/%d failed: %s",
                        fn.__qualname__, attempt, retries, exc,
                    )
                    if attempt < retries:
                        time.sleep(delay)

            if raise_on_exhaustion:
                raise RuntimeError(
                    f"{fn.__qualname__} failed after {retries} attempts. "
                    f"Last error: {last_exc}"
                ) from last_exc
            return fallback
        return wrapper  # type: ignore[return-value]
    return decorator
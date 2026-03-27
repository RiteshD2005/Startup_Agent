"""
utils/executor.py
-----------------
Runs a callable in a separate thread with a hard wall-clock timeout.
Used by the orchestrator so a hanging LLM call never freezes the pipeline.

Usage:
    from utils.executor import run_with_timeout

    result = run_with_timeout(
        agent.execute,
        timeout=240,           # seconds
        description=task.description,
        task_id=task.task_id,
        stage=task.stage,
        project_id=project_id,
    )
"""

import threading
from typing import Any, Callable
from utils.logger import get_logger

logger = get_logger(__name__)


def run_with_timeout(fn: Callable, timeout: float, *args, **kwargs) -> Any:
    """
    Call fn(*args, **kwargs) and return its result.
    Raises TimeoutError if it does not complete within `timeout` seconds.

    Implementation: runs fn in a daemon thread and joins with a timeout.
    The thread is NOT forcibly killed (Python can't do that safely), but
    the orchestrator will treat the task as failed and move on.
    """
    result_holder: list[Any]       = [None]
    error_holder:  list[Exception] = []

    def _target():
        try:
            result_holder[0] = fn(*args, **kwargs)
        except Exception as exc:
            error_holder.append(exc)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        logger.error(
            "run_with_timeout: '%s' did not complete within %ds — timing out.",
            getattr(fn, "__qualname__", str(fn)), timeout
        )
        raise TimeoutError(
            f"'{getattr(fn, '__qualname__', str(fn))}' timed out after {timeout}s"
        )

    if error_holder:
        raise error_holder[0]

    return result_holder[0]
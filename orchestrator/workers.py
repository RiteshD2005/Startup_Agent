"""
orchestrator/workers.py
------------------------
Manages one daemon thread per project.  Prevents duplicate threads from
being spawned when Streamlit re-runs the page script.
"""

import threading
from utils.logger import get_logger
from .master import orchestrate_project

logger = get_logger(__name__)

# project_id → Thread
_threads: dict[int, threading.Thread] = {}
_lock = threading.Lock()


def start_orchestration(project_id: int) -> bool:
    """
    Starts a background orchestration thread for the given project.
    Returns True if a new thread was started, False if one was already running.
    """
    with _lock:
        existing = _threads.get(project_id)
        if existing and existing.is_alive():
            logger.debug(
                "Orchestration already running for project_id=%d — skipped.", project_id
            )
            return False

        thread = threading.Thread(
            target=orchestrate_project,
            args=(project_id,),
            daemon=True,
            name=f"orchestrator-{project_id}",
        )
        thread.start()
        _threads[project_id] = thread
        logger.info("Orchestration thread started for project_id=%d", project_id)
        return True


def is_running(project_id: int) -> bool:
    """Returns True if an orchestration thread is alive for this project."""
    with _lock:
        t = _threads.get(project_id)
        return t is not None and t.is_alive()


def running_project_ids() -> list[int]:
    """Return ids of all currently-running orchestration threads."""
    with _lock:
        return [pid for pid, t in _threads.items() if t.is_alive()]
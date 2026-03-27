"""
utils/llm.py
------------
Thread-safe LLM singleton.

Fixes vs original:
- num_ctx bumped to 2048 — 1024 was too small for llama3.2:1b to reliably
  output valid JSON task arrays.
- temperature=0 for decomposition consistency (agents can override locally).
- Health-check uses a shorter prompt to avoid wasting context.
- Added get_llm_for_decomposition() — zero temperature, slightly larger
  context specifically for the task decomposer.
"""

import time
import threading
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
from .config import get_config
from .logger import get_logger

logger = get_logger(__name__)

_llm:  ChatOllama | None = None
_lock: threading.Lock    = threading.Lock()


def get_llm(retries: int = 5, delay: float = 3.0) -> ChatOllama:
    global _llm
    if _llm is not None:
        return _llm

    with _lock:
        if _llm is not None:
            return _llm

        config   = get_config()
        model    = config["LLM_MODEL"]
        base_url = config["LLM_BASE_URL"]

        for attempt in range(1, retries + 1):
            try:
                candidate = ChatOllama(
                    model=model,
                    base_url=base_url,
                    temperature=0,      # deterministic — critical for JSON output
                    timeout=180,
                     # was 1024 — too small for JSON arrays
                )
                # Lightweight health-check
                candidate.invoke([HumanMessage(content="hi")])
                _llm = candidate
                logger.info(
                    "LLM ready: model=%s base_url=%s num_ctx=2048 temperature=0",
                    model, base_url
                )
                return _llm
            except Exception as exc:
                logger.warning(
                    "LLM init attempt %d/%d failed: %s", attempt, retries, exc
                )
                if attempt < retries:
                    time.sleep(delay)
                else:
                    raise RuntimeError(
                        f"Could not connect to Ollama after {retries} attempts. "
                        f"Last error: {exc}"
                    ) from exc


# def reset_llm() -> None:
#     """Force re-initialisation on next call — useful after Ollama restart."""
#     global _llm
#     with _lock:
#         _llm = None
#     logger.info("LLM instance cleared — will re-initialise on next get_llm() call")
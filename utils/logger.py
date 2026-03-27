"""
utils/logger.py
---------------
Central logging setup.  Call get_logger(__name__) in every module.

Features over the original:
- Reads LOG_LEVEL from env so you can set DEBUG in .env during development
- Adds a file handler when LOG_FILE is set in .env
- Prevents duplicate handlers on repeated imports (Streamlit re-runs scripts)
- Consistent structured format: timestamp | level | module | message
"""

import logging
import sys
import os

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE   = "%Y-%m-%d %H:%M:%S"

# Root logger is configured once at module load
_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level      = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid double-adding handlers if the module is reloaded
    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
               for h in root.handlers):
        console   = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(_FORMAT, datefmt=_DATE)
        console.setFormatter(formatter)
        root.addHandler(console)

    # Optional file handler — set LOG_FILE=venture_agent.log in .env
    log_file = os.getenv("LOG_FILE")
    if log_file and not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE))
        root.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "watchdog"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Returns a named logger.  Call as: logger = get_logger(__name__)
    The root logger is configured on first call.
    """
    _configure_root()
    return logging.getLogger(name)
"""
agents/__init__.py
------------------
Agent registry.

Changes from original:
- Lazy initialisation — agents are created on first get_agent() call,
  not at import time.  This means an Ollama connection error during
  startup doesn't crash the whole app before the UI loads.
- Import errors for individual agents are caught and logged so a broken
  agent file doesn't take down the other four.
- get_agent() returns None with a log warning instead of silently
  returning None with no trace of what was requested.
"""

from utils.logger import get_logger

logger = get_logger(__name__)

_registry: dict | None = None


def _build_registry() -> dict:
    registry = {}
    agent_classes = {
        "strategy":    ("agents.strategy",    "StrategyAgent"),
        "marketing":   ("agents.marketing",   "MarketingAgent"),
        "legal":       ("agents.legal",       "LegalAgent"),
        "engineering": ("agents.engineering", "EngineeringAgent"),
        "finance":     ("agents.finance",     "FinanceAgent"),
    }
    for name, (module_path, class_name) in agent_classes.items():
        try:
            import importlib
            module = importlib.import_module(module_path)
            cls    = getattr(module, class_name)
            registry[name] = cls()
            logger.debug("Agent '%s' registered successfully.", name)
        except Exception as exc:
            logger.error(
                "Failed to register agent '%s' from %s: %s",
                name, module_path, exc, exc_info=True
            )
    return registry


def get_agent(name: str):
    """
    Returns the agent instance for the given name, or None if not found.

    Args:
        name: One of "strategy", "marketing", "legal", "engineering", "finance"
    """
    global _registry
    if _registry is None:
        _registry = _build_registry()

    agent = _registry.get(name)
    if agent is None:
        logger.warning(
            "get_agent('%s') returned None — agent not registered. "
            "Available: %s",
            name, list(_registry.keys())
        )
    return agent


def list_agents() -> list[str]:
    """Returns the names of all successfully registered agents."""
    global _registry
    if _registry is None:
        _registry = _build_registry()
    return list(_registry.keys())
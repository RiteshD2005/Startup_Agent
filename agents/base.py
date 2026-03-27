"""
agents/base.py
--------------
Abstract base class for all specialist agents.

Shared helpers available to every subclass:
  self._invoke_llm(prompt)        — calls Ollama with retry, returns str
  self._retrieve(domain, query)   — RAG lookup, returns list[Document]
  self._search(query)             — real web search, returns list[SearchResult]
  self._save_artifact(...)        — persists output to disk, returns path str
"""

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from utils.logger import get_logger
from utils.retry import with_retries


class BaseAgent(ABC):
    name:        str = "base"
    description: str = "Base agent"
    # Subclasses set their system persona here
    system_prompt: str = "You are a helpful AI specialist."

    def __init__(self):
        self.logger = get_logger(f"agents.{self.name}")

    # ── Public interface called by orchestrator ────────────────────────────

    def execute(self, description: str, **context: Any) -> dict:
        task_id = context.get("task_id", "unknown")
        self.logger.info(
            "Agent '%s' starting task '%s': %s",
            self.name, task_id, description[:120]
        )
        try:
            result = self._run(description, **context)
            self.logger.info("Agent '%s' completed task '%s'.", self.name, task_id)
            return {
                "output":   result.get("output", ""),
                "status":   "completed",
                "metadata": result.get("metadata", {}),
            }
        except Exception as exc:
            self.logger.error(
                "Agent '%s' FAILED task '%s': %s", self.name, task_id, exc,
                exc_info=True
            )
            return {"output": f"Agent error: {exc}", "status": "failed", "metadata": {}}

    # ── Shared helpers ─────────────────────────────────────────────────────

    @with_retries(retries=3, delay=2.0)
    def _invoke_llm(self, user_prompt: str) -> str:
        """Call the LLM with this agent's system persona. Returns response text."""
        from utils.llm import get_llm
        llm = get_llm()
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt),
        ]
        return llm.invoke(messages).content

    def _retrieve(self, domain: str, query: str, k: int = 4) -> list:
        """RAG lookup. Returns list of LangChain Documents (may be empty)."""
        try:
            from utils.retriever import get_retriever
            retriever = get_retriever(domain, k=k)
            if retriever is None:
                return []
            docs = retriever.invoke(query)
            self.logger.debug(
                "Agent '%s' retrieved %d docs from domain='%s'",
                self.name, len(docs), domain
            )
            return docs
        except Exception as exc:
            self.logger.warning("RAG retrieve failed for domain='%s': %s", domain, exc)
            return []

    def _search(self, query: str, num_results: int = 5) -> list:
        """Real web search. Returns list of SearchResult dicts."""
        try:
            from tools.web_search import web_search
            return web_search(query, num_results=num_results)
        except Exception as exc:
            self.logger.warning("Web search failed: %s", exc)
            return []

    def _save_artifact(
        self,
        project_id: int,
        task_id:    str,
        content:    str,
        extension:  str = "md",
    ) -> str | None:
        """Persist output to disk. Returns file path or None on failure."""
        try:
            from utils.artifact_store import save_artifact
            return save_artifact(
                project_id=project_id,
                task_id=task_id,
                content=content,
                extension=extension,
                agent=self.name,
            )
        except Exception as exc:
            self.logger.warning("Artifact save failed: %s", exc)
            return None

    @staticmethod
    def _docs_to_text(docs: list) -> str:
        """Format retrieved documents for injection into a prompt."""
        if not docs:
            return "No relevant internal knowledge found."
        return "\n\n---\n\n".join(
            getattr(d, "page_content", str(d)) for d in docs
        )

    @staticmethod
    def _search_to_text(results: list) -> str:
        """Format web search results for injection into a prompt."""
        if not results:
            return "No web search results available."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r.get('title', '')}")
            lines.append(f"    {r.get('url', '')}")
            lines.append(f"    {r.get('snippet', '')}")
        return "\n".join(lines)

    # ── Subclass contract ──────────────────────────────────────────────────

    @abstractmethod
    def _run(self, description: str, **context: Any) -> dict:
        """
        Implement agent logic here.
        Return dict with at least {"output": str}.
        Raise on unrecoverable failure — base class catches and logs.
        """
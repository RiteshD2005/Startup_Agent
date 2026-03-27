"""
agents/strategy.py
-------------------
Strategy specialist — market research, competitor analysis,
OKR definition, and go-to-market planning.

Pipeline per task:
  1. RAG  — retrieve relevant strategy knowledge from Chroma
  2. Web  — real web search (Tavily or DuckDuckGo)
  3. LLM  — generate strategic report with Ollama
  4. Save — persist report as artifact
"""

from typing import Any
from .base import BaseAgent


class StrategyAgent(BaseAgent):
    name        = "strategy"
    description = (
        "Market research, competitor analysis, OKRs, "
        "positioning, and go-to-market planning."
    )
    system_prompt = (
        "You are a senior startup strategist with deep experience in "
        "market research, competitive positioning, and go-to-market planning. "
        "Be specific, actionable, and concise. Use bullet points where helpful. "
        "Ground recommendations in the provided context."
    )

    def _run(self, description: str, **context: Any) -> dict:
        task_id    = context.get("task_id",    "unknown")
        stage      = context.get("stage",      "unknown")
        project_id = context.get("project_id", 0)

        # 1. Retrieve internal knowledge
        docs = self._retrieve("strategy", description)
        self.logger.info("[strategy] retrieved %d docs", len(docs))

        # 2. Web search for real-time context
        results = self._search(description, num_results=5)
        self.logger.info("[strategy] web search returned %d results", len(results))

        # 3. Build and invoke LLM
        prompt = f"""Task: {description}
Startup stage: {stage}

=== Internal Knowledge ===
{self._docs_to_text(docs)}

=== Live Web Research ===
{self._search_to_text(results)}

Produce a strategic report that includes:
- Situation summary (2–3 sentences)
- Key insights from research
- 3–5 concrete recommendations
- Suggested next steps for the {stage} stage
"""
        output = self._invoke_llm(prompt)

        # 4. Save artifact
        artifact = self._save_artifact(project_id, task_id, output, extension="md")

        return {
            "output": output,
            "metadata": {
                "agent":         self.name,
                "task_id":       task_id,
                "stage":         stage,
                "artifact":      artifact,
                "docs_retrieved": len(docs),
                "web_results":   len(results),
            },
        }
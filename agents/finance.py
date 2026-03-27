"""
agents/finance.py
------------------
Finance specialist — runway, burn rate, pricing, fundraising, cap table.

Pipeline:
  1. RAG  — retrieve financial models and fundraising templates
  2. Web  — search for market benchmarks and investor expectations
  3. LLM  — generate financial analysis
  4. Save — persist as artifact
"""

from typing import Any
from .base import BaseAgent


class FinanceAgent(BaseAgent):
    name        = "finance"
    description = (
        "Runway modelling, burn rate, pricing strategy, cap table, "
        "fundraising preparation, and investor reporting."
    )
    system_prompt = (
        "You are a startup CFO and fundraising advisor with experience across "
        "seed to Series B. Produce precise, numbers-driven financial analysis. "
        "Use realistic benchmarks. Flag assumptions clearly. "
        "Be actionable — every recommendation should tie to a specific decision."
    )

    def _run(self, description: str, **context: Any) -> dict:
        task_id    = context.get("task_id",    "unknown")
        stage      = context.get("stage",      "unknown")
        project_id = context.get("project_id", 0)

        # 1. Retrieve financial templates and benchmarks
        docs = self._retrieve("finance", description)
        self.logger.info("[finance] retrieved %d docs", len(docs))

        # 2. Search for current market benchmarks
        results = self._search(
            f"{description} startup financial benchmarks {stage} stage 2024",
            num_results=4
        )
        self.logger.info("[finance] web search returned %d results", len(results))

        # 3. LLM
        prompt = f"""Finance task: {description}
Startup stage: {stage}

=== Financial Knowledge Base ===
{self._docs_to_text(docs)}

=== Market Benchmarks & Context (Web) ===
{self._search_to_text(results)}

Produce a financial analysis that includes:
- Key metrics relevant to this task (with benchmark ranges where available)
- Specific numbers, formulas, or model structure (e.g. revenue drivers, cost categories)
- Risks and assumptions to flag
- Recommended action based on the {stage} stage context
- Investor-ready summary (2–3 sentences) if fundraising-related
"""
        output = self._invoke_llm(prompt)
        artifact = self._save_artifact(project_id, task_id, output, extension="md")

        return {
            "output": output,
            "metadata": {
                "agent":          self.name,
                "task_id":        task_id,
                "stage":          stage,
                "artifact":       artifact,
                "docs_retrieved": len(docs),
                "web_results":    len(results),
            },
        }
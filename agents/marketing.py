"""
agents/marketing.py
--------------------
Marketing specialist — campaigns, SEO, content, social, email.

Pipeline:
  1. RAG  — retrieve marketing playbooks and templates
  2. Web  — search for competitor positioning and channel trends
  3. LLM  — generate marketing plan / copy
  4. Save — persist as artifact
"""

from typing import Any
from .base import BaseAgent


class MarketingAgent(BaseAgent):
    name        = "marketing"
    description = (
        "Campaign strategy, ad copy, SEO, content calendars, "
        "social media, email sequences, and brand positioning."
    )
    system_prompt = (
        "You are a growth-focused startup marketing expert. "
        "Produce practical, channel-specific marketing plans and copy. "
        "Be data-driven — reference market research where available. "
        "Prioritise high-ROI, low-cost tactics appropriate for an early-stage startup."
    )

    def _run(self, description: str, **context: Any) -> dict:
        task_id    = context.get("task_id",    "unknown")
        stage      = context.get("stage",      "unknown")
        project_id = context.get("project_id", 0)

        # 1. Retrieve marketing playbooks
        docs = self._retrieve("marketing", description)
        self.logger.info("[marketing] retrieved %d docs", len(docs))

        # 2. Search for current channel performance data and competitors
        results = self._search(
            f"{description} marketing strategy startup 2024", num_results=5
        )
        self.logger.info("[marketing] web search returned %d results", len(results))

        # 3. LLM
        prompt = f"""Marketing task: {description}
Startup stage: {stage}

=== Marketing Knowledge Base ===
{self._docs_to_text(docs)}

=== Market & Competitor Research (Web) ===
{self._search_to_text(results)}

Produce a marketing plan that includes:
- Target audience definition (demographics, psychographics, pain points)
- Recommended channels with rationale (prioritise by stage: {stage})
- 3–5 specific campaign ideas with messaging angles
- Sample ad copy or social post (if applicable)
- KPIs to track success
- 30-day action plan
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
"""
agents/engineering.py
----------------------
Engineering specialist — architecture, code scaffolds, DevOps, DB design.

Pipeline:
  1. RAG  — retrieve engineering patterns and templates
  2. Web  — search for latest tooling recommendations
  3. LLM  — generate technical output
  4. Save — persist as .md artifact
"""

from typing import Any
from .base import BaseAgent


class EngineeringAgent(BaseAgent):
    name        = "engineering"
    description = (
        "Technical architecture, code scaffolding, database design, "
        "API development, and DevOps configuration."
    )
    system_prompt = (
        "You are a senior software architect and full-stack engineer. "
        "Produce precise, production-ready technical recommendations. "
        "Include concrete code examples, folder structures, or config snippets "
        "wherever they add clarity. Be specific about technology choices and explain why."
    )

    def _run(self, description: str, **context: Any) -> dict:
        task_id    = context.get("task_id",    "unknown")
        stage      = context.get("stage",      "unknown")
        project_id = context.get("project_id", 0)

        # 1. Retrieve internal engineering knowledge
        docs = self._retrieve("engineering", description)
        self.logger.info("[engineering] retrieved %d docs", len(docs))

        # 2. Search for current best practices
        results = self._search(f"{description} best practices 2024", num_results=4)
        self.logger.info("[engineering] web search returned %d results", len(results))

        # 3. LLM call
        prompt = f"""Engineering task: {description}
Startup stage: {stage}

=== Internal Knowledge Base ===
{self._docs_to_text(docs)}

=== Current Best Practices (Web) ===
{self._search_to_text(results)}

Produce a technical specification that includes:
- Recommended approach and rationale
- Technology/framework choices with reasons
- Step-by-step implementation plan
- Code scaffold or folder structure (if applicable)
- Potential risks and mitigations
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
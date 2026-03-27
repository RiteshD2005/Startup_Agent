"""
agents/legal.py
----------------
Legal specialist — ToS, Privacy Policy, contracts, compliance, IP.

Pipeline:
  1. RAG  — retrieve jurisdiction-specific legal templates
  2. Web  — search for recent regulatory updates
  3. LLM  — draft legal document
  4. Save — persist as .md artifact with disclaimer
"""

from typing import Any
from .base import BaseAgent

_DISCLAIMER = (
    "\n\n---\n"
    "**DISCLAIMER:** This document is an AI-generated template for informational "
    "purposes only. It does not constitute legal advice. Review with a qualified "
    "lawyer before use."
)


class LegalAgent(BaseAgent):
    name        = "legal"
    description = (
        "Terms of Service, Privacy Policy, contracts, IP assignment, "
        "company formation, and compliance documentation."
    )
    system_prompt = (
        "You are a startup legal expert specialising in technology companies. "
        "Draft clear, comprehensive legal documents using plain language where possible. "
        "Always include standard protective clauses. Flag jurisdiction-specific "
        "considerations. Every output must end with a disclaimer that it is a template "
        "requiring professional legal review."
    )

    def _run(self, description: str, **context: Any) -> dict:
        task_id    = context.get("task_id",    "unknown")
        stage      = context.get("stage",      "unknown")
        project_id = context.get("project_id", 0)

        # 1. Retrieve legal templates
        docs = self._retrieve("legal", description)
        self.logger.info("[legal] retrieved %d docs", len(docs))

        # 2. Search for relevant regulatory context
        results = self._search(
            f"{description} startup legal requirements 2024", num_results=3
        )
        self.logger.info("[legal] web search returned %d results", len(results))

        # 3. LLM draft
        prompt = f"""Legal task: {description}
Startup stage: {stage}

=== Legal Knowledge Base ===
{self._docs_to_text(docs)}

=== Recent Regulatory Context (Web) ===
{self._search_to_text(results)}

Draft the requested legal document. Include:
- All standard clauses for this document type
- Jurisdiction placeholders where law varies (mark as [JURISDICTION])
- Company and date placeholders ([COMPANY NAME], [DATE])
- A clear structure with numbered sections
- Plain-language summaries where helpful

End the document with a disclaimer that this is a template requiring legal review.
"""
        output = self._invoke_llm(prompt)

        # Ensure disclaimer is always appended
        if "disclaimer" not in output.lower():
            output += _DISCLAIMER

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
                "disclaimer":     True,
            },
        }
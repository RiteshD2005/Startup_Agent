"""
orchestrator/task_decomposer.py
--------------------------------
The brain of the system. Decomposes a founder goal into a COMPLETE,
realistic task list per stage — as many tasks as the project genuinely needs,
assigned across the 5 specialist domains.

Design philosophy:
- No artificial task count cap. A real startup idea needs 8–15 tasks per stage.
- Every task is assigned to exactly one of the 5 agents.
- The orchestrator (master.py) executes them in dependency order.
- llama3.2:3b safe: prompt is ultra-explicit, validation is lenient + corrective.
- Always falls back to a rich hardcoded task list — never returns empty.
"""

import json
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from utils.llm import get_llm
from utils.retry import with_retries
from utils.logger import get_logger

logger = get_logger(__name__)


class AgentType(str, Enum):
    ENGINEERING = "engineering"
    MARKETING   = "marketing"
    LEGAL       = "legal"
    FINANCE     = "finance"
    STRATEGY    = "strategy"


class RiskLevel(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


_AGENT_ALIASES: dict[str, AgentType] = {
    "market_research": AgentType.STRATEGY,  "research":       AgentType.STRATEGY,
    "analyst":         AgentType.STRATEGY,  "business":       AgentType.STRATEGY,
    "business_strategy": AgentType.STRATEGY,"product":        AgentType.STRATEGY,
    "product_manager": AgentType.STRATEGY,  "okr":            AgentType.STRATEGY,
    "planning":        AgentType.STRATEGY,  "competitive":    AgentType.STRATEGY,
    "growth":          AgentType.MARKETING, "content":        AgentType.MARKETING,
    "brand":           AgentType.MARKETING, "ads":            AgentType.MARKETING,
    "seo":             AgentType.MARKETING, "social":         AgentType.MARKETING,
    "pr":              AgentType.MARKETING, "communications": AgentType.MARKETING,
    "compliance":      AgentType.LEGAL,     "lawyer":         AgentType.LEGAL,
    "ip":              AgentType.LEGAL,     "contract":       AgentType.LEGAL,
    "regulatory":      AgentType.LEGAL,
    "cfo":             AgentType.FINANCE,   "financial":      AgentType.FINANCE,
    "accounting":      AgentType.FINANCE,   "fundraising":    AgentType.FINANCE,
    "revenue":         AgentType.FINANCE,   "pricing":        AgentType.FINANCE,
    "developer":       AgentType.ENGINEERING,"dev":           AgentType.ENGINEERING,
    "tech":            AgentType.ENGINEERING,"software":      AgentType.ENGINEERING,
    "backend":         AgentType.ENGINEERING,"frontend":      AgentType.ENGINEERING,
    "architect":       AgentType.ENGINEERING,"devops":        AgentType.ENGINEERING,
    "infrastructure":  AgentType.ENGINEERING,
}


def _resolve_agent(raw: str) -> AgentType:
    cleaned = raw.strip().lower()
    try:
        return AgentType(cleaned)
    except ValueError:
        pass
    if cleaned in _AGENT_ALIASES:
        logger.warning("Agent alias '%s' -> '%s'", cleaned, _AGENT_ALIASES[cleaned].value)
        return _AGENT_ALIASES[cleaned]
    for valid in AgentType:
        if valid.value in cleaned:
            logger.warning("Partial agent match '%s' -> '%s'", cleaned, valid.value)
            return valid
    raise ValueError(f"Unknown agent '{raw}'")


@dataclass
class TaskSpec:
    id:                str
    description:       str
    assigned_agent:    AgentType
    risk:              RiskLevel
    dependencies:      list[str] = field(default_factory=list)
    requires_approval: bool      = False
    estimated_hours:   Optional[int] = None

    def __post_init__(self):
        if self.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            self.requires_approval = True

    def to_db_dict(self, stage: str) -> dict:
        return {
            "stage":             stage,
            "task_id":           self.id,
            "description":       self.description,
            "assigned_agent":    self.assigned_agent.value,
            "risk":              self.risk.value,
            "dependencies":      self.dependencies,
            "requires_approval": str(self.requires_approval).lower(),
            "status":            "pending",
        }


_STAGE_CONTEXT: dict[str, str] = {
    "idea": (
        "IDEA stage: Discovery and validation of the concept. "
        "Tasks: market sizing, competitor research, customer personas, "
        "value proposition, brand/domain, IP landscape scan, "
        "early financial assumptions, OKRs. No engineering build yet."
    ),
    "validation": (
        "VALIDATION stage: Prove the idea before building. "
        "Tasks: landing page, waitlist/lead capture, customer interviews, "
        "demand analysis, MVP feature prioritisation, entity formation, "
        "IP protection, financial model, SEO foundations."
    ),
    "build": (
        "BUILD stage: Ship the MVP. "
        "Tasks: architecture, database schema, backend API, frontend UI, "
        "payments integration, CI/CD, security review, ToS, privacy policy, "
        "launch assets, beta onboarding, unit economics."
    ),
    "gtm": (
        "GO-TO-MARKET stage: Acquire first paying users. "
        "Tasks: pricing page, paid ads, SEO content, cold outreach, "
        "referral programme, product analytics, revenue dashboard, "
        "customer success playbook, sales deck, GDPR compliance."
    ),
    "scale": (
        "SCALE stage: Grow sustainably. "
        "Tasks: Series A pitch deck, data room, cap table modelling, "
        "hiring plan, JDs for key roles, performance marketing, "
        "SOC2 readiness, platform reliability, API platform, board reporting."
    ),
}


_SYSTEM_PROMPT = SystemMessage(content="""You are the master orchestration agent for an AI startup platform.
Decompose a startup goal into a COMPLETE list of tasks for the given stage.

RULES:
1. Output ONLY a valid JSON array. No prose, no markdown, no explanation.
2. Generate between 8 and 15 tasks covering ALL work needed at this stage.
3. Distribute tasks across MULTIPLE agents — do not assign everything to one.
4. Each task MUST have these exact fields:
   - "id": unique snake_case string
   - "description": clear 1-2 sentence instruction
   - "assigned_agent": MUST be one of: strategy, marketing, legal, finance, engineering
   - "risk": MUST be one of: low, medium, high, critical
   - "dependencies": array of id strings (can be [])
5. Dependencies must reference ids in the same array.
6. Output ONLY the JSON array.

AGENTS:
- strategy    -> market research, competitor analysis, OKRs, personas
- marketing   -> campaigns, SEO, content, social, email, brand, ad copy
- legal       -> contracts, ToS, privacy, IP, entity formation, compliance
- finance     -> runway, burn rate, pricing, fundraising, cap table
- engineering -> code, architecture, database, API, DevOps, security""")


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    if "[" in raw and "]" in raw:
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        raw   = raw[start:end]
    return raw.strip()


def _validate(raw: str) -> list[TaskSpec]:
    data = json.loads(_strip_fences(raw))
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")
    if len(data) < 3:
        raise ValueError(f"Too few tasks: got {len(data)}, need at least 3")

    all_ids: set[str] = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id", f"task_{i}"))
        tid = re.sub(r"[^a-z0-9_]", "_", tid.lower())
        tid = re.sub(r"_+", "_", tid).strip("_") or f"task_{i}"
        item["id"] = tid
        all_ids.add(tid)

    tasks: list[TaskSpec] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        tid = item.get("id", f"task_{i}")
        if not item.get("description"):
            logger.warning("Task '%s' missing description -- skipping", tid)
            continue
        try:
            agent = _resolve_agent(str(item.get("assigned_agent", "strategy")))
        except ValueError as e:
            logger.warning("%s -- defaulting to strategy", e)
            agent = AgentType.STRATEGY
        raw_risk = str(item.get("risk", "medium")).lower().strip()
        try:
            risk = RiskLevel(raw_risk)
        except ValueError:
            risk = RiskLevel.MEDIUM
        deps = item.get("dependencies", [])
        if not isinstance(deps, list):
            deps = []
        valid_deps = [d for d in deps if d in all_ids and d != tid]
        hours = item.get("estimated_hours")
        if not (isinstance(hours, int) and 1 <= hours <= 80):
            hours = None
        tasks.append(TaskSpec(
            id=tid, description=item["description"].strip(),
            assigned_agent=agent, risk=risk,
            dependencies=valid_deps, estimated_hours=hours,
        ))

    if len(tasks) < 3:
        raise ValueError(f"Only {len(tasks)} valid tasks after validation")
    return tasks


def _fallback_tasks(stage: str, goal: str) -> list[TaskSpec]:
    S, M, L, F, E = (
        AgentType.STRATEGY, AgentType.MARKETING, AgentType.LEGAL,
        AgentType.FINANCE,  AgentType.ENGINEERING
    )
    LO, ME, HI = RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH

    stages: dict[str, list[TaskSpec]] = {
        "idea": [
            TaskSpec("market_sizing",        "Calculate TAM, SAM, SOM for the target market using industry reports and bottom-up analysis.", S, LO),
            TaskSpec("competitor_research",  "Identify top 5-7 competitors, map their features, pricing, and weaknesses.", S, LO, ["market_sizing"]),
            TaskSpec("customer_personas",    "Define 3 detailed customer personas: demographics, pain points, goals, willingness to pay.", S, LO, ["market_sizing"]),
            TaskSpec("value_proposition",    "Craft a clear value proposition and unique differentiator statement.", S, ME, ["competitor_research", "customer_personas"]),
            TaskSpec("okr_definition",       "Set Q1 OKRs: 1 objective, 3-5 measurable key results aligned to validation goals.", S, LO, ["value_proposition"]),
            TaskSpec("brand_naming",         "Generate 10 brand name candidates, check .com domain availability, shortlist top 3.", M, LO),
            TaskSpec("initial_positioning",  "Write a positioning statement and elevator pitch for the venture.", M, LO, ["value_proposition", "brand_naming"]),
            TaskSpec("ip_landscape_scan",    "Scan patent and trademark databases for conflicts with brand name and core IP.", L, ME, ["brand_naming"]),
            TaskSpec("legal_entity_options", "Research best legal entity type (LLC vs C-corp) for this venture's goals.", L, ME),
            TaskSpec("financial_assumptions","Build a spreadsheet of initial revenue, cost, and headcount assumptions.", F, LO, ["market_sizing"]),
            TaskSpec("funding_options",      "Research bootstrapping vs angel vs pre-seed VC and recommend a funding path.", F, ME, ["financial_assumptions"]),
        ],
        "validation": [
            TaskSpec("interview_script",      "Write a 10-question customer discovery interview script targeting the core persona.", S, LO),
            TaskSpec("conduct_interviews",    "Conduct 10-15 customer interviews and synthesise key insights and quotes.", S, ME, ["interview_script"]),
            TaskSpec("demand_signal_analysis","Analyse interview results: identify top pain points and willingness to pay.", S, ME, ["conduct_interviews"]),
            TaskSpec("mvp_feature_list",      "Prioritise MVP feature set using the MoSCoW method based on interview insights.", S, ME, ["demand_signal_analysis"]),
            TaskSpec("landing_page_copy",     "Write landing page headline, subheadline, feature bullets, and CTA copy.", M, LO, ["mvp_feature_list"]),
            TaskSpec("landing_page_build",    "Build and deploy a landing page with email capture and waitlist form.", E, LO, ["landing_page_copy"]),
            TaskSpec("waitlist_campaign",     "Launch a waitlist campaign: social posts, email to network, relevant communities.", M, LO, ["landing_page_build"]),
            TaskSpec("seo_foundation",        "Research 20 target keywords; set up blog structure for long-term SEO.", M, LO),
            TaskSpec("entity_formation",      "Form the legal entity, open a business bank account, register EIN.", L, HI),
            TaskSpec("ip_protection",         "File provisional patent or trademark application for the core product concept.", L, HI),
            TaskSpec("financial_model_v1",    "Build a 12-month financial model: revenue scenarios, burn rate, runway.", F, ME, ["mvp_feature_list"]),
            TaskSpec("pricing_research",      "Research competitor pricing; propose 2-3 pricing tiers with rationale.", F, ME, ["demand_signal_analysis"]),
        ],
        "build": [
            TaskSpec("tech_stack_decision",  "Select and document the full technology stack with rationale for each choice.", E, LO),
            TaskSpec("system_architecture",  "Design system architecture diagram: services, data flow, external integrations.", E, ME, ["tech_stack_decision"]),
            TaskSpec("database_schema",      "Design normalised database schema for all core entities.", E, ME, ["system_architecture"]),
            TaskSpec("backend_api",          "Implement the core REST/GraphQL API with authentication and key endpoints.", E, HI, ["database_schema"]),
            TaskSpec("frontend_ui",          "Build the core frontend UI screens: onboarding, dashboard, key feature flows.", E, HI, ["backend_api"]),
            TaskSpec("payments_integration", "Integrate Stripe for subscription billing and checkout.", E, HI, ["backend_api"]),
            TaskSpec("cicd_pipeline",        "Set up CI/CD pipeline with automated tests, linting, and staging deployment.", E, ME, ["backend_api"]),
            TaskSpec("security_review",      "Conduct security review: input validation, auth hardening, secret management.", E, HI, ["backend_api"]),
            TaskSpec("tos_and_privacy",      "Draft Terms of Service and Privacy Policy compliant with GDPR and CCPA.", L, HI),
            TaskSpec("cookie_compliance",    "Implement cookie consent banner and data processing agreements.", L, ME, ["tos_and_privacy"]),
            TaskSpec("launch_assets",        "Create launch assets: product screenshots, demo video, tagline, press kit.", M, LO),
            TaskSpec("beta_onboarding_plan", "Design beta user onboarding flow: welcome email, in-app guides, check-in cadence.", M, ME, ["frontend_ui"]),
            TaskSpec("unit_economics_model", "Refine unit economics: CAC, LTV, payback period, gross margin per tier.", F, ME, ["payments_integration"]),
            TaskSpec("beta_pricing_setup",   "Finalise and implement pricing tiers in the billing system.", F, ME, ["unit_economics_model", "payments_integration"]),
        ],
        "gtm": [
            TaskSpec("gtm_strategy",         "Define go-to-market strategy: primary channel, ICP, messaging, 90-day plan.", S, ME),
            TaskSpec("sales_playbook",        "Write a sales playbook: ICP profile, discovery questions, objection handling, close.", S, ME, ["gtm_strategy"]),
            TaskSpec("pricing_page",         "Design and publish the pricing page with tier comparison and FAQs.", M, LO),
            TaskSpec("paid_ads_setup",       "Set up and launch Google Ads and Meta Ads campaigns with A/B test variants.", M, HI, ["gtm_strategy"]),
            TaskSpec("seo_content_plan",     "Publish 4 SEO-optimised blog posts targeting high-intent keywords.", M, LO),
            TaskSpec("cold_outreach",        "Write cold email sequences (3-step) for top 50 target accounts.", M, ME, ["sales_playbook"]),
            TaskSpec("referral_programme",   "Design and implement a referral programme with incentive structure.", M, ME),
            TaskSpec("product_analytics",    "Integrate Mixpanel or Amplitude; define and instrument key product events.", E, ME),
            TaskSpec("revenue_dashboard",    "Build a revenue dashboard: MRR, churn, ARR, CAC, LTV in real time.", E, ME, ["product_analytics"]),
            TaskSpec("customer_success",     "Create customer success playbook: health scores, check-in cadence, escalation.", S, ME),
            TaskSpec("gdpr_live_compliance", "Ensure live product is GDPR/CCPA compliant: data requests, deletion flows.", L, HI),
            TaskSpec("sales_deck",           "Create an investor/enterprise sales deck: problem, solution, traction, ROI.", M, ME, ["gtm_strategy"]),
            TaskSpec("mrr_financial_update", "Update financial model with real MRR data; recalculate runway and burn.", F, ME),
        ],
        "scale": [
            TaskSpec("series_a_narrative",   "Develop Series A investment narrative: story, market, traction, vision.", S, HI),
            TaskSpec("pitch_deck",           "Build full investor pitch deck (12 slides) with traction metrics.", M, HI, ["series_a_narrative"]),
            TaskSpec("data_room",            "Prepare investor data room: financials, cap table, contracts, metrics.", F, HI, ["pitch_deck"]),
            TaskSpec("cap_table_modelling",  "Model Series A dilution scenarios, option pool, and investor returns.", F, HI, ["data_room"]),
            TaskSpec("hiring_plan",          "Define 12-month hiring roadmap: roles, seniority, comp bands, timeline.", S, ME),
            TaskSpec("jd_engineering_lead",  "Write job description for Engineering Lead or CTO.", S, LO, ["hiring_plan"]),
            TaskSpec("jd_head_of_growth",    "Write job description for Head of Growth or VP Marketing.", S, LO, ["hiring_plan"]),
            TaskSpec("performance_marketing","Scale paid marketing: increase budgets, expand channels, optimise ROAS.", M, HI),
            TaskSpec("enterprise_seo",       "Build a domain-authority SEO programme: backlinks, pillar content, PR.", M, ME),
            TaskSpec("soc2_readiness",       "Begin SOC 2 Type II readiness: gap assessment, policy templates, auditor selection.", L, HI),
            TaskSpec("international_legal",  "Assess legal requirements for top 2 expansion markets.", L, HI),
            TaskSpec("platform_reliability", "Implement SLAs, on-call runbooks, uptime monitoring, and DR plan.", E, HI),
            TaskSpec("api_platform",         "Design and publish a public API and developer docs for ecosystem integrations.", E, ME),
            TaskSpec("board_reporting",      "Set up board reporting cadence: monthly metrics pack template.", F, ME, ["data_room"]),
        ],
    }

    fallback = stages.get(stage.lower(), stages["idea"])
    logger.info("Using fallback tasks for stage=%s (%d tasks)", stage, len(fallback))
    return fallback


@with_retries(retries=3, delay=2.0, exceptions=(ValueError, json.JSONDecodeError))
def decompose_goal(goal: str, stage: str) -> list[TaskSpec]:
    ctx = _STAGE_CONTEXT.get(stage.lower())
    if ctx is None:
        raise ValueError(f"Unknown stage '{stage}'. Valid: {list(_STAGE_CONTEXT)}")
    llm      = get_llm()
    user_msg = HumanMessage(content=(
        f"Startup goal: {goal}\n\n"
        f"Stage: {stage.upper()}\n"
        f"Stage context: {ctx}\n\n"
        f"Generate a COMPLETE task list for this stage (8-15 tasks).\n"
        f"Distribute tasks across: strategy, marketing, legal, finance, engineering.\n"
        f"assigned_agent MUST be one of: strategy, marketing, legal, finance, engineering\n"
        f"risk MUST be one of: low, medium, high, critical\n"
        f"Output ONLY the JSON array. No other text."
    ))
    logger.info("Decomposing goal for stage=%s | goal='%s'", stage, goal[:80])
    raw   = llm.invoke([_SYSTEM_PROMPT, user_msg]).content
    tasks = _validate(raw)
    logger.info("LLM decomposed into %d tasks for stage=%s", len(tasks), stage)
    return tasks


def decompose_with_fallback(goal: str, stage: str) -> list[TaskSpec]:
    try:
        return decompose_goal(goal, stage)
    except Exception as e:
        logger.warning("LLM decomposition failed for stage=%s: %s -- using fallback.", stage, e)
        return _fallback_tasks(stage, goal)


def topological_sort(tasks: list[TaskSpec]) -> list[TaskSpec]:
    id_map   = {t.id: t for t in tasks}
    visited: set[str]       = set()
    ordered: list[TaskSpec] = []

    def visit(task: TaskSpec, ancestors: set[str]):
        if task.id in ancestors:
            logger.warning("Circular dependency at '%s' -- breaking cycle", task.id)
            return
        if task.id in visited:
            return
        for dep in task.dependencies:
            if dep in id_map:
                visit(id_map[dep], ancestors | {task.id})
        visited.add(task.id)
        ordered.append(task)

    for t in tasks:
        visit(t, set())
    return ordered
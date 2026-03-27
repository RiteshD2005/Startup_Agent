"""
utils/clarify.py
----------------
Determines whether a founder's goal is specific enough to act on,
and generates one clarifying question at a time when it isn't.
"""

from langchain_core.messages import HumanMessage, SystemMessage

from utils.llm import get_llm
from utils.retry import with_retries
from utils.logger import get_logger

logger = get_logger(__name__)

# Maximum times we ask the founder to clarify before giving up and proceeding
MAX_CLARIFICATIONS = 3

_CLARITY_SYSTEM = SystemMessage(content=(
    "You are a senior startup advisor who evaluates whether a founder's "
    "startup goal contains enough information to be broken into concrete tasks. "
    "A clear goal specifies: what the product does, who it is for, and what "
    "success looks like.  Answer only YES or NO."
))

_QUESTION_SYSTEM = SystemMessage(content=(
    "You are a senior startup advisor helping a founder sharpen their idea. "
    "Ask exactly ONE concise clarifying question that would most improve the "
    "specificity of the goal.  Return only the question — no preamble, no options."
))


@with_retries(retries=2, delay=1.5, fallback=True, raise_on_exhaustion=False)
def is_goal_clear(goal: str) -> bool:
    """
    Returns True if the LLM judges the goal actionable.
    Falls back to True on failure so the flow is never permanently blocked.
    """
    llm = get_llm()
    response = llm.invoke([
        _CLARITY_SYSTEM,
        HumanMessage(content=f'Startup goal: "{goal}"\n\nIs this goal clear and actionable?'),
    ]).content.strip().upper()
    logger.debug("Clarity check response: %s", response)
    return "YES" in response


@with_retries(retries=2, delay=1.5, raise_on_exhaustion=False,
              fallback="Can you tell me more about who your target customer is and what problem you are solving for them?")
def generate_clarifying_question(goal: str) -> str:
    """
    Returns a single clarifying question.
    Falls back to a safe generic question on LLM failure.
    """
    llm = get_llm()
    response = llm.invoke([
        _QUESTION_SYSTEM,
        HumanMessage(content=f'Startup goal: "{goal}"'),
    ]).content.strip()
    logger.debug("Generated clarifying question: %s", response)
    return response
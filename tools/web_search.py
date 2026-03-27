"""
tools/web_search.py
-------------------
Real web search with two backends:

  1. Tavily  — best results, structured JSON, 1000 free searches/month.
               Set TAVILY_API_KEY in .env.  Sign up: https://tavily.com
  2. DuckDuckGo HTML scrape — completely free, no account, no API key.
               Used automatically when TAVILY_API_KEY is empty.

Both return a list of SearchResult dicts with keys:
  title   : str
  url     : str
  snippet : str

Usage:
    from tools.web_search import web_search
    results = web_search("SaaS invoicing tools for freelancers", num_results=5)
    for r in results:
        print(r["title"], r["url"])
        print(r["snippet"])
"""

import time
import urllib.parse
import urllib.request
import json
import re
from typing import TypedDict

from utils.config import get_config
from utils.logger import get_logger

logger = get_logger(__name__)


class SearchResult(TypedDict):
    title:   str
    url:     str
    snippet: str


# ── Tavily backend ─────────────────────────────────────────────────────────

def _tavily_search(query: str, num_results: int) -> list[SearchResult]:
    """
    Calls the Tavily Search API.
    Docs: https://docs.tavily.com/docs/tavily-api/rest_api
    """
    config  = get_config()
    api_key = config["TAVILY_API_KEY"]

    payload = json.dumps({
        "api_key":        api_key,
        "query":          query,
        "search_depth":   "basic",   # "basic" = faster, "advanced" = deeper
        "max_results":    num_results,
        "include_answer": False,
        "include_raw_content": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results: list[SearchResult] = []
    for item in data.get("results", [])[:num_results]:
        results.append({
            "title":   item.get("title",   ""),
            "url":     item.get("url",     ""),
            "snippet": item.get("content", ""),
        })
    return results


# ── DuckDuckGo HTML fallback ───────────────────────────────────────────────

_DDG_URL = "https://html.duckduckgo.com/html/?q={query}"

# Patterns for DuckDuckGo's HTML result blocks
_RE_RESULT  = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_RE_SNIPPET = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_RE_TAG     = re.compile(r"<[^>]+>")


def _strip_tags(html: str) -> str:
    return _RE_TAG.sub("", html).strip()


def _ddg_search(query: str, num_results: int) -> list[SearchResult]:
    """
    Scrapes DuckDuckGo's lightweight HTML version.
    No API key. No rate limit for reasonable usage.
    """
    encoded = urllib.parse.quote_plus(query)
    url     = _DDG_URL.format(query=encoded)

    req = urllib.request.Request(
        url,
        headers={
            # Mimic a browser — DDG blocks plain urllib UA
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        },
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    links    = _RE_RESULT.findall(html)
    snippets = _RE_SNIPPET.findall(html)

    results: list[SearchResult] = []
    for i, (href, title_html) in enumerate(links[:num_results]):
        # DDG wraps real URLs in a redirect — extract the `uddg` param
        if "uddg=" in href:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href   = parsed.get("uddg", [href])[0]

        snippet = _strip_tags(snippets[i]) if i < len(snippets) else ""
        results.append({
            "title":   _strip_tags(title_html),
            "url":     href,
            "snippet": snippet,
        })

    return results


# ── Public API ─────────────────────────────────────────────────────────────

def web_search(query: str, num_results: int = 5) -> list[SearchResult]:
    """
    Search the web and return structured results.

    Automatically chooses Tavily if TAVILY_API_KEY is set in .env,
    otherwise falls back to DuckDuckGo scraping (free, no key needed).

    Args:
        query:       The search query string.
        num_results: How many results to return (max ~10 for DDG).

    Returns:
        List of SearchResult dicts: {title, url, snippet}
    """
    config    = get_config()
    use_tavily = bool(config.get("TAVILY_API_KEY", "").strip())
    backend   = "Tavily" if use_tavily else "DuckDuckGo"

    logger.info("web_search | backend=%s | query='%s'", backend, query[:80])

    try:
        if use_tavily:
            results = _tavily_search(query, num_results)
        else:
            results = _ddg_search(query, num_results)

        logger.info(
            "web_search | backend=%s | returned %d results", backend, len(results)
        )
        return results

    except Exception as exc:
        logger.error(
            "web_search | backend=%s | FAILED: %s — returning empty list.",
            backend, exc, exc_info=True
        )
        # If Tavily failed, try DDG as ultimate fallback
        if use_tavily:
            logger.info("web_search | Tavily failed, retrying with DuckDuckGo.")
            try:
                return _ddg_search(query, num_results)
            except Exception as exc2:
                logger.error("web_search | DuckDuckGo also failed: %s", exc2)
        return []


def format_results_for_prompt(results: list[SearchResult]) -> str:
    """
    Formats search results into a clean string suitable for injecting
    into an LLM prompt.
    """
    if not results:
        return "No web search results available."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']}")
        lines.append(f"    URL: {r['url']}")
        lines.append(f"    {r['snippet']}")
        lines.append("")
    return "\n".join(lines).strip()
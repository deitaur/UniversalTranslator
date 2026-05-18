"""
Web search via DuckDuckGo — no API key required.
Returns formatted text snippet for injection into LLM context.
"""

import logging
log = logging.getLogger("web_search")

_MAX_RESULTS = 5
_SNIPPET_LEN = 300   # chars per result body


def search(query: str, max_results: int = _MAX_RESULTS) -> str:
    """Search DuckDuckGo and return a formatted text block."""
    query = query.strip()
    if not query:
        return "Empty search query."
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return f"No results found for: {query}"
        lines = [f"Web search results for: \"{query}\"\n"]
        for i, r in enumerate(results, 1):
            body = r.get("body", "").strip()[:_SNIPPET_LEN]
            href = r.get("href", "")
            title = r.get("title", "").strip()
            lines.append(f"{i}. {title}")
            if body:
                lines.append(f"   {body}")
            if href:
                lines.append(f"   {href}")
            lines.append("")
        return "\n".join(lines)
    except ImportError:
        log.warning("ddgs not installed — run: pip install ddgs")
        return "[Web search unavailable — run: pip install ddgs]"
    except Exception as e:
        log.error("web_search error: %s", e)
        return f"[Search error: {e}]"


WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the internet for current information, news, facts, prices, "
            "recent events, or anything the model doesn't know. "
            "Use this whenever the user asks about something that may have changed recently "
            "or that requires up-to-date data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Concise search query in the most relevant language"
                }
            },
            "required": ["query"]
        }
    }
}

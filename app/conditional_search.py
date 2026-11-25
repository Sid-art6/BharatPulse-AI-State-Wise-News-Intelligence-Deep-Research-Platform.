"""Optional, no-paid-key RSS discovery for explicit freshness requests.

This is an RSS feed search, NOT full web browsing or full publisher article
retrieval. Default OFF so ordinary chats add no network calls or surprise cost.
Queries are derived from server-stored article titles, not user-provided URLs.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx

from . import core
from .chat_router_v1 import dedupe_sources

FRESHNESS = re.compile(
    r'\b(?:latest|recent|today|new\s+developments|new\s+updates?|'
    r'what\s+happened\s+next|search\s+(?:for\s+)?(?:related\s+)?(?:news|coverage)|'
    r'find\s+(?:more\s+)?(?:reports|coverage))\b', re.I)
CACHE_TTL_SECONDS = 600
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def enabled() -> bool:
    return os.getenv('BHARATPULSE_ENABLE_ON_DEMAND_RSS_SEARCH', 'false').strip().lower() in ('1', 'true', 'yes')


def should_fetch(question: str) -> bool:
    return enabled() and bool(FRESHNESS.search(question))


def _search_query(article: dict[str, Any]) -> str:
    title = str(article.get('title') or '')[:160]
    tokens = re.findall(r'[A-Za-z][A-Za-z-]{2,}', title)
    stop = {'the', 'and', 'from', 'with', 'when', 'where', 'what', 'near', 'about', 'today'}
    important = [t for t in tokens if t.casefold() not in stop][:11]
    return ' '.join(important)[:140] + ' when:7d'


async def maybe_enrich(question: str, selected: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not should_fetch(question):
        return sources
    key = str(selected.get('id') or selected.get('title') or '')
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and cached[0] > now:
        return dedupe_sources(sources[0], sources[1:] + cached[1])
    try:
        data = await core.fetch_rss(_search_query(selected), 'en')
        news = core.parse_rss(data, str(selected.get('region') or 'All India'))
        related = core.find_related(selected, news, limit=4)
    except (httpx.HTTPError, ValueError, TimeoutError, OSError, RuntimeError):
        return sources
    if len(_cache) > 128:
        _cache.clear()
    _cache[key] = (now + CACHE_TTL_SECONDS, related)
    return dedupe_sources(sources[0], sources[1:] + related)

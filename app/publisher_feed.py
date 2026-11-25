"""Read bounded, publisher-configured RSS feeds for a matching original item."""
import asyncio
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from . import core
from .evidence_utils import normalise
from .regional_sources_v10 import feeds_for_region

_cache = {}
_locks = {}


async def _download(client, url, limit):
    async with client.stream("GET", url) as response:
        if response.status_code != 200:
            return response.status_code, b""
        data = bytearray()
        async for part in response.aiter_bytes():
            data.extend(part)
            if len(data) > limit:
                raise ValueError("publisher_feed_too_large")
        return 200, bytes(data)


async def _items(url):
    # All network destinations here are fixed feed configuration. Redirects
    # stay disabled, including redirects from robots.txt.
    async with _locks.setdefault(url, asyncio.Lock()):
        now = time.monotonic()
        saved = _cache.get(url)
        if saved and saved[0] > now:
            return saved[1]
        items = []
        try:
            async with httpx.AsyncClient(timeout=6, follow_redirects=False,
                                         headers={"User-Agent": core.USER_AGENT}) as client:
                base = urlsplit(url)
                status, policy = await _download(client, f"{base.scheme}://{base.netloc}/robots.txt", 120000)
                if status == 200:
                    rules = RobotFileParser()
                    rules.parse(policy.decode("utf-8", "replace").splitlines())
                    if not rules.can_fetch(core.USER_AGENT, url):
                        raise ValueError("publisher_feed_disallowed")
                elif status != 404:
                    raise ValueError("publisher_feed_policy_unavailable")
                status, data = await _download(client, url, core.MAX_RESPONSE_BYTES)
                if status == 200:
                    items = ET.fromstring(data).findall("./channel/item")[:60]
        except (ValueError, httpx.HTTPError, ET.ParseError, OSError):
            pass
        _cache[url] = (now + (300 if items else 60), items)
        return items


async def match(article, host_matches):
    publisher = article.get("publisher", "")
    region = article.get("region", "All India")
    specs = (*feeds_for_region(region), *feeds_for_region("All India"))
    feeds = dict.fromkeys(s.url for s in specs if s.name.casefold() == publisher.casefold())
    for feed in feeds:
        for item in await _items(feed):
            title = core.clean_title(item.findtext("title") or "")
            url = (item.findtext("link") or "").strip()
            if not host_matches(publisher, url) or not url.startswith("https://"):
                continue
            if normalise(title) != normalise(article.get("title", "")):
                continue
            body = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or ""
            soup = BeautifulSoup(body, "html.parser")
            for tag in soup.select("nav, aside, footer, script, style, form, figure"):
                tag.decompose()
            passages = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            text = "\n\n".join(p for p in passages if len(p) >= 35 and not re.match(
                r"(?:also read|read more|subscribe|advertisement)", p, re.I))
            return url, title, text[:32000]
    return None

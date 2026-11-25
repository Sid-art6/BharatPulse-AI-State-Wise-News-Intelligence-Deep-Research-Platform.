"""Background, publisher-permitted article retrieval and cached, quoted evidence.

Source URLs are read ONLY from indexed articles; no browser-supplied fetch URL.
No paywall, anti-bot, authentication or robots restrictions are bypassed.
Article text is untrusted data, never an instruction to the language model.
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import os
import re
import socket
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from . import core, publisher_feed

LOG = logging.getLogger('bharatpulse.article_context')
MAX_HTML_BYTES = 1_800_000
MAX_TEXT_CHARS = 32_000
MAX_REDIRECTS = 4
TTL_HOURS = 12
READER_REVISION = "1.5"
FAILURE_RETRY_MINUTES = 35
USER_AGENT = 'BharatPulseAI/1.4 (+source-grounded educational article reader)'

# Deliberate allowlist: browsers cannot make the backend visit arbitrary URLs.
# Administrators may add publishers, never user-supplied hostnames.
DEFAULT_DOMAINS = {
    'thehindu.com', 'newindianexpress.com', 'indianexpress.com',
    'deccanherald.com', 'hindustantimes.com', 'timesofindia.indiatimes.com',
    'indiatimes.com', 'tribuneindia.com', 'scroll.in', 'thenewsminute.com',
    'indiatoday.in', 'indianmasterminds.com', 'news.google.com',
    'newsonair.gov.in', 'indiagazette.com', 'bing.com',
    'bbc.com', 'bbc.co.uk', 'bbci.co.uk', 'firstpost.com', 'livemint.com',
    'moneycontrol.com', 'theprint.in', 'news18.com', 'onmanorama.com',
    'mathrubhumi.com', 'telegraphindia.com', 'thewire.in',
    'barandbench.com', 'livelaw.in', 'verdictum.in', 'ndtv.com',
    'the420.in', 'courtbook.in', 'medianama.com', 'thequint.com',
    'business-standard.com', 'financialexpress.com', 'economictimes.indiatimes.com',
    'aninews.in', 'outlookindia.com', 'thefederal.com', 'downtoearth.org.in',
    'thebetterindia.com', 'siasat.com', 'greaterkashmir.com',
}


def public_source(source: dict) -> dict:
    if source.get("evidence_origin") == "publisher_article":
        return {**source, "description": source.get("rss_description", "")}
    return source


def _allowed_domains() -> set[str]:
    extra = {x.strip().casefold().lstrip('.') for x in
             os.getenv('BHARATPULSE_ARTICLE_DOMAINS', '').split(',') if x.strip()}
    return DEFAULT_DOMAINS | extra


def _domain_allowed(host: str) -> bool:
    return any(host == domain or host.endswith('.' + domain) for domain in _allowed_domains())


def _public_hostname(host: str) -> bool:
    if not host or host == 'localhost' or host.endswith('.local'):
        return False
    try:
        if ipaddress.ip_address(host):
            return False  # Do not fetch an IP literal; publisher domains only.
    except ValueError:
        pass
    if not _domain_allowed(host):
        return False
    try:
        addresses = {row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        return bool(addresses) and all(ipaddress.ip_address(ip).is_global for ip in addresses)
    except (OSError, ValueError):
        return False


def _valid_url(url: str) -> bool:
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.port in (None, 443) and
                not p.username and not p.password and _public_hostname((p.hostname or '').casefold()))
    except ValueError:
        return False


def init_db() -> None:
    with core.db_conn() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS article_context (
          article_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          source_url TEXT NOT NULL DEFAULT '',
          article_title TEXT NOT NULL DEFAULT '',
          body TEXT NOT NULL DEFAULT '',
          evidence_origin TEXT NOT NULL DEFAULT 'rss',
          updated_at TEXT NOT NULL,
          failure_code TEXT NOT NULL DEFAULT '',
          reader_revision TEXT NOT NULL DEFAULT '', provenance TEXT NOT NULL DEFAULT ''
        )''')
        columns = {r[1] for r in db.execute('PRAGMA table_info(article_context)')}
        if 'provenance' not in columns:
            db.execute("ALTER TABLE article_context ADD COLUMN provenance TEXT NOT NULL DEFAULT ''")
        db.execute("UPDATE article_context SET body='' WHERE reader_revision != ? AND body != ''", (READER_REVISION,))
        if 'reader_revision' not in columns:
            db.execute("ALTER TABLE article_context ADD COLUMN reader_revision TEXT NOT NULL DEFAULT ''")


# Full text stays in bounded process memory unless the operator has explicitly
# configured a publisher for which they have storage permission.
_passages: OrderedDict[tuple, str] = OrderedDict()


def get_cached(article_id: str) -> dict:
    try:
        with core.db_conn() as db:
            row = db.execute('SELECT * FROM article_context WHERE article_id=?', (article_id,)).fetchone()
        result = dict(row) if row else {}
        if result.get("status") == "ready" and not result.get("body"):
            result["body"] = _passages.get((core.DB_PATH, article_id, result["updated_at"]), "")
            if not result["body"]:
                return {}
        return result
    except Exception:
        return {}


def _fresh(row: dict) -> bool:
    if row.get('reader_revision') != READER_REVISION:
        return False  # Upgrade stale pre-fix failures and evidence only once.
    try:
        dt = datetime.fromisoformat(row['updated_at'])
        age = datetime.now(timezone.utc) - dt
        ttl = timedelta(hours=TTL_HOURS) if row.get('status') == 'ready' else timedelta(minutes=FAILURE_RETRY_MINUTES)
        return age < ttl
    except (ValueError, TypeError, KeyError):
        return False


def _store(article_id: str, status: str, *, url='', title='', body='', failure='', provenance='publisher_web') -> dict:
    row = {'article_id': article_id, 'status': status, 'source_url': url,
           'provenance': provenance if status == 'ready' else 'rss', 'article_title': title[:300], 'body': body[:MAX_TEXT_CHARS],
           'evidence_origin': 'publisher_article' if status == 'ready' else 'rss',
           'updated_at': core.utcnow(), 'failure_code': failure[:80],
           'reader_revision': READER_REVISION}
    stored = dict(row)
    permitted = {x.strip().lower() for x in os.getenv('BHARATPULSE_LICENSED_STORAGE_HOSTS', '').split(',')}
    if body and (urlsplit(url).hostname or '').lower() not in permitted:
        stored['body'] = ''
        _passages[(core.DB_PATH, article_id, row['updated_at'])] = row['body']
        while len(_passages) > 96:
            _passages.popitem(last=False)
    with core.db_conn() as db:
        db.execute('''INSERT INTO article_context
            (article_id,status,source_url,article_title,body,evidence_origin,updated_at,failure_code,reader_revision,provenance)
            VALUES (:article_id,:status,:source_url,:article_title,:body,:evidence_origin,:updated_at,:failure_code,:reader_revision,:provenance)
            ON CONFLICT(article_id) DO UPDATE SET
              status=excluded.status,source_url=excluded.source_url,
              article_title=excluded.article_title,body=excluded.body,
              evidence_origin=excluded.evidence_origin,updated_at=excluded.updated_at,
              failure_code=excluded.failure_code,reader_revision=excluded.reader_revision,provenance=excluded.provenance''', stored)
    return row


def _select_body(html: str) -> tuple[str, str]:
    """Extract text, preferring publisher articleBody JSON-LD then article DOM."""
    soup = BeautifulSoup(html, 'html.parser')
    title = (soup.find('meta', attrs={'property': 'og:title'}) or {}).get('content', '')
    if not title and soup.title:
        title = soup.title.get_text(' ', strip=True)
    directives = " ".join(str(tag.get("content", "")) for tag in soup.select('meta[name="robots" i]'))
    if re.search(r"\b(?:noarchive|nosnippet)\b", directives, re.I):
        raise ValueError("publisher_access_restricted")
    if re.search(r'"isAccessibleForFree"\s*:\s*(?:"false"|false)', html, re.I):
        raise ValueError("publisher_access_restricted")
    if soup.select_one('[itemprop="isAccessibleForFree"][content="false" i], [data-paywall="true"]'):
        raise ValueError("publisher_access_restricted")
    if not title and soup.h1:
        title = soup.h1.get_text(' ', strip=True)
    for script in soup.find_all('script', type='application/ld+json')[:12]:
        try:
            payload = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get('@graph'), list):
                nodes.extend(node['@graph'])
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get('headline') and not _headline_overlap(title, str(node['headline'])):
                continue
            if isinstance(node.get('articleBody'), str):
                body = ' '.join(node['articleBody'].split())
                if len(body) >= 500:
                    return title[:300], body[:MAX_TEXT_CHARS]
    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form', 'noscript', 'svg']):
        tag.decompose()
    choices = soup.select('[itemprop="articleBody"], article, main article, .article-content, .story-content, .article-body, .story-body')
    candidates = choices
    best = ''
    for container in candidates[:20]:
        paragraphs = [p.get_text(' ', strip=True) for p in container.find_all('p')]
        seen = set()
        cleaned = []
        for line in paragraphs:
            line = ' '.join(line.split())
            if len(line) < 35 or line in seen or re.search(r'^(?:also read|read more|advertisement|subscribe|follow us)\b', line, re.I):
                continue
            seen.add(line)
            cleaned.append(line)
        body = '\n\n'.join(cleaned)
        if len(body) > len(best):
            best = body
    return title[:300], best[:MAX_TEXT_CHARS]


def _same_story_title(expected: str, fetched: str, body: str) -> bool:
    return _headline_overlap(expected, fetched)



async def _robots_allowed(client: httpx.AsyncClient, url: str) -> bool:
    parts = urlsplit(url)
    robots = f'{parts.scheme}://{parts.netloc}/robots.txt'
    if not _valid_url(robots):
        return False
    try:
        response = await client.get(robots, follow_redirects=False)
        if response.status_code in (401, 403):
            return False
        if response.status_code == 404:
            return True
        if response.status_code != 200 or len(response.content) > 120_000:
            raise ValueError('robots_policy_unavailable')
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser.can_fetch(USER_AGENT, url)
    except (httpx.HTTPError, UnicodeError) as error:
        raise ValueError('robots_policy_unavailable') from error


async def _fetch_publisher_page(initial_url: str) -> tuple[str, str]:
    if not _valid_url(initial_url):
        host = urlsplit(initial_url).hostname or ''
        if host and _domain_allowed(host):
            try:
                socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            except OSError as error:
                raise ValueError('publisher_dns_unavailable') from error
        raise ValueError('source_url_not_permitted')
    url = initial_url
    async with httpx.AsyncClient(timeout=httpx.Timeout(16, connect=6), follow_redirects=False,
                                 trust_env=False, headers={'User-Agent': USER_AGENT,
                                 'Accept': 'text/html,application/xhtml+xml'}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            if not _valid_url(url):
                raise ValueError('redirect_not_permitted')
            if not await _robots_allowed(client, url):
                raise ValueError('publisher_access_not_permitted')
            async with client.stream('GET', url) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    destination = response.headers.get('location', '')
                    if not destination:
                        raise ValueError('redirect_missing')
                    url = urljoin(url, destination)
                    continue
                if response.status_code in (401, 403, 402, 429, 451):
                    raise ValueError('publisher_access_restricted')
                response.raise_for_status()
                if 'html' not in response.headers.get('content-type', '').lower():
                    raise ValueError('publisher_non_html')
                if re.search(r'\b(?:noarchive|nosnippet)\b', response.headers.get('x-robots-tag', ''), re.I):
                    raise ValueError('publisher_access_restricted')
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_HTML_BYTES:
                        raise ValueError('publisher_page_too_large')
                    chunks.append(chunk)
                raw = b''.join(chunks)
                return url, raw.decode(response.encoding or 'utf-8', errors='replace')
    raise ValueError('too_many_redirects')


def _decode_legacy_google_news_link(url: str) -> str | None:
    """Some old RSS tokens embed a public URL; newer opaque tokens do not.

    This is a best-effort offline decode, not an anti-bot workaround.
    Every decoded URL still passes the same domain/network/robots checks.
    """
    path = urlsplit(url).path
    match = re.search(r'/articles/([A-Za-z0-9_-]{16,})', path)
    if not match:
        return None
    token = match.group(1)
    try:
        data = base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))
        text = data.decode('utf-8', errors='ignore')
    except (ValueError, UnicodeError):
        return None
    for candidate in re.findall(r'https://[^\x00-\x20\"<>]+', text):
        candidate = candidate.rstrip('\x00\x01\x02\x03\x04')
        if _valid_url(candidate) and 'news.google.com' not in candidate:
            return candidate
    return None


async def _public_google_redirect(url: str, publisher: str) -> str | None:
    """Use an ordinary authorised HTTP redirect if the item supplies one."""
    if not _valid_url(url) or urlsplit(url).hostname != 'news.google.com':
        return None
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False,
                                     headers={'User-Agent': USER_AGENT}) as client:
            if not await _robots_allowed(client, url):
                return None
            async with client.stream('GET', url) as response:
                if response.status_code not in (301, 302, 303, 307, 308):
                    return None
                target = urljoin(url, response.headers.get('location', ''))
                if _publisher_host_matches(publisher, target) and _valid_url(target):
                    return target
    except (httpx.HTTPError, ValueError, OSError):
        pass
    return None


# Publisher mapping is not article-specific. It is an allowlist to prevent an
# identically worded story on an unrelated website from becoming source evidence.
PUBLISHER_DOMAINS: dict[str, tuple[str, ...]] = {
    'bbc news': ('bbc.com','bbc.co.uk'),
    'scroll.in': ('scroll.in',),
    'times of india': ('timesofindia.indiatimes.com',),
    'the news minute': ('thenewsminute.com',),
    'theprint': ('theprint.in',),
    'india today': ('indiatoday.in',),
    'the new indian express': ('newindianexpress.com',),
    'the times of india': ('timesofindia.indiatimes.com',),
    'news on air': ('newsonair.gov.in',),
    'akashvani news': ('newsonair.gov.in',),
    'www.indiagazette.com': ('indiagazette.com',),
    'india gazette': ('indiagazette.com',),
    'the hindu': ('thehindu.com',),
    'deccan herald': ('deccanherald.com',),
    'the indian express': ('indianexpress.com',),
    'hindustan times': ('hindustantimes.com',),
    'ndtv': ('ndtv.com',),
    'business standard': ('business-standard.com',),
    'firstpost': ('firstpost.com',),
    'news18': ('news18.com',),
    'the print': ('theprint.in',),
    'the wire': ('thewire.in',),
    'scroll': ('scroll.in',),
    'moneycontrol': ('moneycontrol.com',),
}

_TITLE_STOPWORDS = {
    'against', 'with', 'from', 'that', 'this', 'news', 'india', 'says',
    'latest', 'reports', 'report', 'court', 'high', 'refuses', 'quash',
    'following', 'after', 'before', 'amid', 'into', 'the', 'and',
    'been', 'said', 'have', 'will', 'about', 'their', 'over', 'under',
}


def _publisher_host_matches(publisher: str, url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https' or parsed.port not in (None,443) or parsed.username or parsed.password:
            return False
    except ValueError:
        return False
    domains = PUBLISHER_DOMAINS.get(str(publisher or '').strip().casefold())
    if not domains:
        # Unknown publisher: no automatic cross-provider URL assertion.
        return False
    return any(host == domain or host.endswith('.' + domain) for domain in domains)


def _headline_overlap(expected: str, candidate: str) -> bool:
    """Require incident-specific overlap, not just common legal/news words."""
    tokens = lambda t: core.title_tokens(t) - _TITLE_STOPWORDS
    a, b = tokens(expected), tokens(candidate)
    if len(a) < 3 or len(b) < 3:
        return a == b and len(a) >= 2
    shared = a & b
    # A high overlap with the smaller headline allows reasonable synonyms,
    # but requires > half the selected headline's distinctive terms too.
    return len(shared) >= 3 and len(shared) / len(a) >= 0.55 and len(shared) / len(b) >= 0.50


def _unwrap_bing_news_link(url: str) -> str:
    """Extract public publisher URL from a Bing News RSS `apiclick` link."""
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    if host == 'bing.com' or host.endswith('.bing.com'):
        urls = parse_qs(parsed.query).get('url', [])
        return urls[0] if urls else ''
    return url


async def _resolve_from_index(article: dict) -> str | None:
    """Reuse a direct publisher RSS URL if it already describes this story."""
    try:
        with core.db_conn() as db:
            exact = db.execute("""SELECT url,title FROM publisher_links
                WHERE fingerprint=? AND publisher=?""",
                (core.fingerprint(article.get("title", "")), article.get("publisher", "").casefold())).fetchone()
            if (exact and _publisher_host_matches(article.get("publisher", ""), exact["url"])
                    and _headline_overlap(article["title"], exact["title"]) and _valid_url(exact["url"])):
                return exact["url"]
            rows = db.execute("""SELECT title,url,publisher FROM articles
                WHERE feed_origin IN ('direct_publisher_rss','bbc_publisher_rss')
                  AND is_demo=0 ORDER BY published_at DESC LIMIT 400""").fetchall()
    except Exception:
        return None
    for row in rows:
        candidate = str(row['url'] or '')
        if (_publisher_host_matches(article.get('publisher', ''), candidate)
                and _headline_overlap(article.get('title', ''), row['title'])
                and _valid_url(candidate)):
            return candidate
    return None


async def _resolve_from_bing_rss(article: dict) -> str | None:
    """Look up direct publisher links in a public RSS search, without
    contacting blocked Google News article pages or scraping search HTML.

    This is optional discovery: publisher robots rules are checked separately
    before the article text is downloaded.  No result is trusted by default.
    """
    if os.getenv('BHARATPULSE_BING_RSS_DISCOVERY', 'true').casefold() not in {'true', '1', 'yes'}:
        return None
    publisher = str(article.get('publisher') or '')
    if publisher.casefold() not in PUBLISHER_DOMAINS:
        return None
    title = str(article.get('title') or '').strip()
    if not title:
        return None
    # A bounded search, fixed service origin and no user-specified URLs.
    query = quote(f'{title[:150]} {publisher[:60]}', safe='')
    rss_url = f'https://www.bing.com/news/search?q={query}&format=rss'
    # Confirm the service grants permission to retrieve the RSS feed.
    if not _valid_url(rss_url):
        return None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5),
                                     follow_redirects=False, trust_env=False,
                                     headers={'User-Agent': USER_AGENT,
                                              'Accept': 'application/rss+xml,application/xml'}) as client:
            if not await _robots_allowed(client, rss_url):
                LOG.info('direct URL discovery: Bing RSS disallowed by robots')
                return None
            response = await client.get(rss_url)
            if response.status_code != 200 or len(response.content) > 450_000:
                return None
            data = response.content
        root = ET.fromstring(data)
        for item in root.findall('./channel/item')[:30]:
            link = _unwrap_bing_news_link((item.findtext('link') or '').strip())
            candidate_title = (item.findtext('title') or '').strip()
            if (_publisher_host_matches(publisher, link)
                    and _headline_overlap(title, candidate_title)
                    and _valid_url(link)):
                return link
    except (httpx.HTTPError, ET.ParseError, OSError, ValueError):
        return None
    return None


async def _resolve_google_rss(article: dict) -> str | None:
    """Find original publisher URL *before* fetching any page as article text."""
    google_url = str(article.get('url') or '')
    legacy = _decode_legacy_google_news_link(google_url)
    if legacy and _publisher_host_matches(article.get('publisher', ''), legacy):
        return legacy
    indexed = await _resolve_from_index(article)
    if indexed:
        return indexed
    redirect = await _public_google_redirect(google_url, article.get('publisher', ''))
    return redirect or await _resolve_from_bing_rss(article)


async def _retrieve(article: dict) -> dict:
    url = str(article.get('url') or '')
    if not url:
        return _store(article['id'], 'limited', failure='no_source_url')
    try:
        matched = await publisher_feed.match(article, _publisher_host_matches)
        if matched:
            direct, title, passages = matched
            if len(passages) >= 500 and len(passages.split()) >= 60:
                return _store(article['id'], 'ready', url=direct, title=title, body=passages,
                              provenance='publisher_syndicated_feed')
            url = direct
        if (urlsplit(url).hostname or '').casefold() == 'news.google.com':
            # Never treat an aggregator URL as a publisher page. The previous
            # implementation fetched Google first; its robots check failed
            # before the original publisher was ever reached.
            url = await _resolve_google_rss(article)
            if not url:
                return _store(article['id'], 'limited',
                              failure='publisher_url_not_resolved')
        try:
            final_url, html = await _fetch_publisher_page(url)
        except (httpx.TimeoutException, httpx.NetworkError):
            await asyncio.sleep(0.4)
            final_url, html = await _fetch_publisher_page(url)
        except httpx.HTTPStatusError as error:
            if error.response.status_code not in (502, 503, 504):
                raise
            await asyncio.sleep(0.5)
            final_url, html = await _fetch_publisher_page(url)
        # A permitted redirect to another publisher is not evidence for the
        # originally selected publisher's story.
        publisher = str(article.get('publisher') or '')
        if publisher.casefold() in PUBLISHER_DOMAINS:
            matches_publisher = _publisher_host_matches(publisher, final_url)
        else:
            matches_publisher = urlsplit(url).hostname == urlsplit(final_url).hostname
        if not matches_publisher:
            return _store(article['id'], 'limited', failure='publisher_domain_mismatch')
        title, body = _select_body(html)
        if len(body) < 500 or len(body.split()) < 60:
            return _store(article['id'], 'limited', failure='insufficient_accessible_text')
        if not _same_story_title(str(article.get('title') or ''), title, body):
            return _store(article['id'], 'limited', failure='publisher_story_mismatch')
        return _store(article['id'], 'ready', url=final_url, title=title, body=body)
    except (ValueError, httpx.HTTPError, UnicodeError, OSError) as exc:
        code = (f'publisher_http_{exc.response.status_code}' if isinstance(exc, httpx.HTTPStatusError)
                else str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        LOG.info('article prefetch fallback article=%s reason=%s', article['id'][:12], code[:60])
        return _store(article['id'], 'limited', url=url or '', failure=code[:80])


_inflight: dict[str, asyncio.Task] = {}
_limit = asyncio.Semaphore(3)


async def _prepare(article: dict) -> dict:
    async with _limit:
        try:
            return await _retrieve(article)
        finally:
            _inflight.pop(article['id'], None)


def schedule(article: dict) -> dict:
    if article.get('is_demo'):
        return {'status': 'demo', 'evidence_origin': 'demo'}
    existing = get_cached(article['id'])
    if existing and _fresh(existing):
        return public_status(existing)
    task = _inflight.get(article['id'])
    if len(_inflight) >= 32 and task is None:
        return {'status': 'busy', 'evidence_origin': 'rss', 'failure_code': 'reader_busy'}
    if task is None or task.done():
        _inflight[article['id']] = asyncio.create_task(_prepare(article))
    return {'status': 'loading', 'evidence_origin': 'pending'}


async def ensure(article: dict, timeout: float = 22.0) -> dict:
    if article.get('is_demo'):
        return {}
    row = get_cached(article['id'])
    if row and _fresh(row):
        return row
    schedule(article)
    task = _inflight.get(article['id'])
    if task:
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except asyncio.TimeoutError:
            return {"status": "loading"}
    return get_cached(article['id'])


def public_status(row: dict) -> dict:
    return {'provenance': row.get('provenance', ''), 'source_url': row.get('source_url', ''), 'status': row.get('status', 'not_started'),
            'evidence_origin': row.get('evidence_origin', 'rss'),
            'retrieved_at': row.get('updated_at', ''),
            'word_count': len(str(row.get('body') or '').split()) if row.get('status') == 'ready' else 0,
            'failure_code': row.get('failure_code', '') if row.get('status') != 'ready' else ''}


_STOP = {'what', 'when', 'where', 'which', 'does', 'from', 'this', 'that', 'about',
         'article', 'report', 'reported', 'were', 'have', 'been', 'with', 'against',
         'could', 'would', 'should', 'does', 'their', 'they', 'then', 'them', 'there',
         'after', 'before', 'details', 'information', 'tell', 'please', 'explain',
         'case', 'news', 'some', 'will', 'happened', 'happens'}


def relevant_passages(body: str, question: str, max_chars: int = 6500) -> str:
    """Question-relevant verbatim passages, no LLM-produced summaries or invented facts."""
    paras = []
    for paragraph in re.split(r'\n\s*\n+', body):
        paragraph = paragraph.strip()
        if len(paragraph) < 35:
            continue
        if len(paragraph) <= 850:
            paras.append(paragraph)
            continue
        # ArticleBody JSON-LD often contains a single huge paragraph. Split
        # on sentence boundaries and keep each source excerpt below the LLM
        # context budget without manufacturing new text.
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', paragraph)
        section = ''
        for sentence in sentences:
            if len(sentence) > 850:
                if section:
                    paras.append(section); section = ''
                # Word-boundary split preserves literal contiguous substrings.
                for block in re.findall(r'.{1,760}(?:\s|$)', sentence, re.S):
                    if len(block.strip()) >= 35:
                        paras.append(block.strip())
                continue
            if section and len(section) + len(sentence) + 1 > 800:
                paras.append(section); section = ''
            section = (section + ' ' + sentence).strip()
        if section:
            paras.append(section)
    if not paras:
        paras = [body[i:i+500] for i in range(0, len(body), 500)]
    query = {t for t in re.findall(r'\w{3,}', question.casefold()) if t not in _STOP}
    scored = []
    for i, p in enumerate(paras):
        tokens = set(re.findall(r'\w{3,}', p.casefold()))
        score = sum(3 if t in tokens else 0 for t in query)
        # A general 'why' or 'what happened' question benefits from the lead.
        if i < 3:
            score += (3 - i)
        scored.append((score, i, p))
    ranked = sorted(scored, key=lambda r: (-r[0], r[1]))
    indices, used = [], 0
    for score, i, p in ranked:
        if used + len(p) > max_chars:
            continue
        indices.append(i)
        used += len(p) + 2
        if len(indices) >= 12:
            break
    return '\n\n'.join(paras[i] for i in sorted(indices))


def attach(article: dict, context: dict, question: str = '') -> dict:
    if context.get('status') != 'ready' or not context.get('body'):
        return article
    view = dict(article)
    evidence = relevant_passages(context['body'], question)
    if len(evidence) < 100:
        return article
    view['rss_description'] = article.get('description', '')
    view['description'] = evidence
    view['url'] = context['source_url']
    view['provenance'] = context.get('provenance', 'publisher_web')
    view['evidence_origin'] = 'publisher_article'
    view['context_retrieved_at'] = context.get('updated_at')
    return view

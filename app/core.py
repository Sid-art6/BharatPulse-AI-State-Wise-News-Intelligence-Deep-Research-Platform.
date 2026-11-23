"""Feed ingestion, persistent news store, and grounded evidence retrieval.

Google News RSS syndicates publisher links/headlines. This application does not
scrape copyrighted full text or assert that snippets constitute article text.
"""
from __future__ import annotations

import hashlib
import asyncio
import html
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .regions import REGIONS, TOPICS, REGION_RSS_LANG, REGION_LOCAL_ALIASES, classify_topic, infer_region, detect_language

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("BHARATPULSE_DATA_DIR", str(BASE / "data")))
DB_PATH = DATA_DIR / "news.db"
MAX_RESPONSE_BYTES = 1_500_000
MAX_RSS_ITEMS = 60
USER_AGENT = "BharatPulseAI/0.2 (+local educational news explorer)"
BBC_INDIA_RSS = "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml"


class StripHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []

    def handle_data(self, data: str) -> None:
        self.out.append(data)


def strip_html(value: str | None) -> str:
    parser = StripHTML()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.out))).strip()[:1200]


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", strip_html(title)).strip()[:240]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def fingerprint(title: str) -> str:
    lower = title.lower()
    lower = re.sub(r"\s+-\s+[^-]+$", "", lower)
    # Preserve Unicode letters: stripping non-Latin scripts made every Hindi,
    # Tamil, Kannada etc. headline collide with the same empty fingerprint.
    import unicodedata
    norm = re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", lower)).strip()
    return stable_id(norm or title)


def date_to_iso(value: str | None) -> str:
    if not value:
        return ""  # Unknown: never fabricate a publication timestamp.
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return ""


@contextmanager
def db_conn():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            publisher TEXT NOT NULL,
            published_at TEXT NOT NULL,
            region TEXT NOT NULL,
            region_confidence TEXT NOT NULL,
            topic TEXT NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'Unknown',
            summary_en TEXT NOT NULL DEFAULT '',
            UNIQUE(fingerprint, is_demo)
        );
        CREATE INDEX IF NOT EXISTS idx_article_region ON articles(region, is_demo, published_at);
        CREATE TABLE IF NOT EXISTS rejected_headlines (
            fingerprint TEXT PRIMARY KEY,
            checked_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS refresh_state (
            region TEXT PRIMARY KEY,
            last_attempt TEXT,
            last_success TEXT,
            last_error TEXT,
            fetched INTEGER NOT NULL DEFAULT 0,
            added INTEGER NOT NULL DEFAULT 0,
            filter_mode TEXT
        );
        """)
        # Existing user databases must migrate without losing stored articles.
        existing = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
        if "language" not in existing:
            conn.execute("ALTER TABLE articles ADD COLUMN language TEXT NOT NULL DEFAULT 'Unknown'")
        if "summary_en" not in existing:
            conn.execute("ALTER TABLE articles ADD COLUMN summary_en TEXT NOT NULL DEFAULT ''")


def get_refresh_state(region: str) -> dict[str, Any]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM refresh_state WHERE region=?", (region,)).fetchone()
        return dict(row) if row else {}


def record_refresh_attempt(region: str) -> None:
    with db_conn() as conn:
        conn.execute("""
            INSERT INTO refresh_state (region, last_attempt, last_error)
            VALUES (?, ?, NULL)
            ON CONFLICT(region) DO UPDATE SET last_attempt=excluded.last_attempt, last_error=NULL
        """, (region, utcnow()))


def record_refresh_result(region: str, *, fetched: int, added: int, filter_mode: str) -> None:
    with db_conn() as conn:
        conn.execute("""
            UPDATE refresh_state SET last_success=?, last_error=NULL, fetched=?, added=?, filter_mode=?
            WHERE region=?
        """, (utcnow(), fetched, added, filter_mode, region))


def record_refresh_error(region: str, error: str) -> None:
    with db_conn() as conn:
        conn.execute("UPDATE refresh_state SET last_error=? WHERE region=?", (error[:200], region))


def parse_rss(xml_bytes: bytes, region: str, provider: str = "Google News") -> list[dict[str, Any]]:
    if len(xml_bytes) > MAX_RESPONSE_BYTES:
        raise ValueError("RSS response too large")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as ex:
        raise ValueError("Invalid RSS data from news provider") from ex
    result: list[dict[str, Any]] = []
    for item in root.findall("./channel/item")[:MAX_RSS_ITEMS]:
        raw_title = item.findtext("title", default="")
        title = clean_title(raw_title)
        url = (item.findtext("link", default="") or "").strip()
        if not title or not url.startswith("https://"):
            continue
        source = item.find("source")
        publisher = (source.text or "").strip() if source is not None and source.text else ("BBC News" if provider == "BBC News" else "News publisher via Google News")
        if publisher == "News publisher via Google News" and " - " in title:
            publisher = title.rsplit(" - ", 1)[-1][:100]
        if title.endswith(" - " + publisher):
            title = title[: -len(" - " + publisher)]
        description = strip_html(item.findtext("description", default=""))
        article_region, region_confidence = infer_region(title + " " + description, region)
        language = detect_language(title + " " + description, article_region)
        result.append({
            "id": stable_id(url), "fingerprint": fingerprint(title), "title": title,
            "description": description, "url": url,
            "publisher": publisher[:100],
            "published_at": date_to_iso(item.findtext("pubDate")),
            "region": article_region, "region_confidence": region_confidence,
            "topic": classify_topic(title + " " + description),
            "is_demo": 0, "created_at": utcnow(), "language": language,
            "summary_en": description if language == "English" else "",
        })
    return result


def rss_url_for_query(query: str, language: str = "en") -> str:
    if language not in {"en", "hi", "ta", "te", "kn", "ml", "mr", "bn", "gu", "pa", "or", "as", "ur"}:
        raise ValueError("Unsupported feed language")
    return f"https://news.google.com/rss/search?q={quote(query, safe='')}&hl={language}-IN&gl=IN&ceid=IN:{language}"


async def fetch_rss(query: str, language: str = "en") -> bytes:
    # Fixed provider origin prevents user-controlled URL fetching / SSRF.
    return await _fetch_fixed_rss(rss_url_for_query(query, language))


async def _fetch_fixed_rss(url: str) -> bytes:
    # URL is always built from a fixed origin, never passed from the browser.
    async with httpx.AsyncClient(timeout=httpx.Timeout(18, connect=8), follow_redirects=False,
                                 headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"}) as client:
        response = await client.get(url)
        response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ValueError("RSS response too large")
        return response.content


async def fetch_news(region: str) -> list[dict[str, Any]]:
    query = "India latest news when:7d" if region == "All India" else f'"{region}" India news when:7d'
    # National feed combines the aggregator and a second independent RSS origin.
    # A failing provider should not hide valid results from another provider.
    sources = [("Google News", fetch_rss(query))]
    local_language = REGION_RSS_LANG.get(region, "hi" if region == "All India" else None)
    if local_language:
        # Endonym query improves discovery of news originally written in local
        # languages; content stays in the publisher's original language.
        native = REGION_LOCAL_ALIASES.get(region, ["भारत"])[0]
        local_query = f"{native} news when:7d"
        sources.append(("Google News (regional)", fetch_rss(local_query, local_language)))
    if region == "All India":
        sources.append(("BBC News", _fetch_fixed_rss(BBC_INDIA_RSS)))
    results = await asyncio.gather(*(work for _, work in sources), return_exceptions=True)
    news: list[dict[str, Any]] = []
    errors: list[Exception] = []
    for (provider, _), result in zip(sources, results):
        if isinstance(result, Exception):
            errors.append(result)
            continue
        try:
            news.extend(parse_rss(result, region, provider=provider))
        except ValueError as exc:
            errors.append(exc)
    if not news and errors:
        raise errors[0]
    return news


def save_articles(articles: list[dict[str, Any]]) -> int:
    if not articles:
        return 0
    columns = ("id", "fingerprint", "title", "description", "url", "publisher", "published_at", "region", "region_confidence", "topic", "is_demo", "created_at", "language", "summary_en")
    added = 0
    with db_conn() as conn:
        for a in articles:
            before = conn.total_changes
            conn.execute(f"INSERT OR IGNORE INTO articles ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", tuple(a.get(c, "") for c in columns))
            added += conn.total_changes - before
    return added


def unseen_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only new articles need LLM screening; prevent repeat API costs on polling.

    Skip duplicates both within the incoming batch and against stored headlines.
    """
    if not articles:
        return []
    fingerprints = list(dict.fromkeys(a["fingerprint"] for a in articles))
    known: set[str] = set()
    with db_conn() as conn:
        for start in range(0, len(fingerprints), 400):
            subset = fingerprints[start:start + 400]
            placeholders = ','.join('?' for _ in subset)
            rows = conn.execute(
                f"SELECT fingerprint FROM articles WHERE is_demo=0 AND fingerprint IN ({placeholders})",
                subset).fetchall()
            known.update(r[0] for r in rows)
            rejected = conn.execute(
                f"SELECT fingerprint FROM rejected_headlines WHERE fingerprint IN ({placeholders})",
                subset).fetchall()
            known.update(r[0] for r in rejected)
    fresh: list[dict[str, Any]] = []
    seen = set(known)
    for a in articles:
        if a["fingerprint"] not in seen:
            seen.add(a["fingerprint"])
            fresh.append(a)
    return fresh


def remember_rejected_headlines(incoming: list[dict[str, Any]], accepted: list[dict[str, Any]]) -> None:
    """Keep rejected headlines from consuming model tokens at every RSS poll."""
    accepted_ids = {a["id"] for a in accepted}
    rejected = {a["fingerprint"] for a in incoming if a["id"] not in accepted_ids}
    if rejected:
        with db_conn() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO rejected_headlines (fingerprint,checked_at) VALUES (?,?)",
                ((fingerprint, utcnow()) for fingerprint in rejected),
            )


def pending_english_previews(articles: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    """Only translate excerpts still missing English previews in SQLite."""
    candidates = [a for a in articles
                  if a.get("language") not in {"English", "Unknown"} and a.get("description")]
    pending = []
    with db_conn() as conn:
        for a in candidates:
            row = conn.execute("SELECT summary_en FROM articles WHERE id=? AND is_demo=0", (a["id"],)).fetchone()
            if not row or not row[0]:
                pending.append(a)
                if len(pending) >= limit:
                    break
    return pending


def save_english_summaries(previews: dict[str, str]) -> None:
    if not previews:
        return
    with db_conn() as conn:
        for article_id, text in previews.items():
            if text and len(text) <= 1000:
                conn.execute("UPDATE articles SET summary_en=? WHERE id=? AND is_demo=0",
                             (text, article_id))


def list_articles(region: str = "All India", topic: str = "All topics", search: str = "", demo: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    where = ["is_demo = ?"]
    params: list[Any] = [int(demo)]
    if region != "All India":
        where.append("region = ?")
        params.append(region)
    if topic != "All topics":
        where.append("topic = ?")
        params.append(topic)
    if search:
        where.append("(title LIKE ? OR description LIKE ? OR publisher LIKE ?)")
        term = "%" + search[:100].replace("%", "\\%").replace("_", "\\_") + "%"
        # LIKE escape is explicit, so search text is not a wildcard.
        where[-1] = "(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR publisher LIKE ? ESCAPE '\\')"
        params.extend([term] * 3)
    params.append(min(max(limit, 1), 100))
    sql = f"SELECT * FROM articles WHERE {' AND '.join(where)} ORDER BY published_at DESC LIMIT ?"
    with db_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_article(article_id: str) -> dict[str, Any] | None:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return dict(row) if row else None


def dashboard_stats(demo: bool = False) -> dict[str, Any]:
    with db_conn() as conn:
        rows = conn.execute("SELECT region, topic, COUNT(*) n FROM articles WHERE is_demo=? GROUP BY region, topic", (int(demo),)).fetchall()
        latest = conn.execute("SELECT MAX(published_at) FROM articles WHERE is_demo=?", (int(demo),)).fetchone()[0]
    total = sum(r[2] for r in rows)
    region_counts: dict[str, int] = {}
    topic_counts: dict[str, int] = {}
    for region, topic, n in rows:
        region_counts[region] = region_counts.get(region, 0) + n
        topic_counts[topic] = topic_counts.get(topic, 0) + n
    return {"total_articles": total, "regions_covered": len([k for k in region_counts if k != "All India"]), "region_counts": region_counts, "topic_counts": topic_counts, "latest_at": latest}


def demo_fixtures() -> list[dict[str, Any]]:
    # Explicitly hypothetical: no real reporting or links are invented.
    examples = [
        ("Maharashtra", "Transport", "Mumbai metro expansion proposal", "Hypothetical planning meeting about new metro connections and commuter impact."),
        ("Maharashtra", "Business", "Pune startup funding round", "Illustrative example of a local technology firm's funding announcement."),
        ("Karnataka", "Technology", "Bengaluru AI skills programme", "Hypothetical training programme for students and professionals."),
        ("Karnataka", "Environment", "Bengaluru urban water review", "Illustrative scenario involving water demand and supply monitoring."),
        ("Delhi", "Policy", "Delhi public transit policy consultation", "Hypothetical public consultation on urban transport planning."),
        ("Delhi", "Environment", "Delhi air quality action planning", "Illustrative scenario for environmental policy research."),
        ("Tamil Nadu", "Business", "Chennai industrial investment proposal", "Hypothetical announcement related to manufacturing investment."),
        ("Tamil Nadu", "Health", "Tamil Nadu public health outreach plan", "Illustrative scenario for community health programme coverage."),
        ("Bihar", "Transport", "Bihar district road connectivity proposal", "Hypothetical district road development policy example."),
        ("Bihar", "Policy", "Bihar education initiative discussion", "Illustrative state-level education programme scenario."),
        ("West Bengal", "Technology", "Kolkata digital services pilot", "Hypothetical public-service digitisation project."),
        ("Kerala", "Environment", "Kerala coastal conservation proposal", "Illustrative climate resilience planning example."),
    ]
    now = datetime.now(timezone.utc)
    rows = []
    for idx, (region, topic, title, description) in enumerate(examples):
        title = f"[DEMO SCENARIO] {title}"
        rows.append({
            "id": "demo-" + stable_id(region + title), "fingerprint": fingerprint(title),
            "title": title, "description": description,
            "url": "", "publisher": "Illustrative fixture (not a news source)",
            "published_at": (now - timedelta(hours=idx * 2)).isoformat(timespec="seconds"),
            "region": region, "region_confidence": "demo_only", "topic": topic,
            "is_demo": 1, "created_at": utcnow(), "language": "English", "summary_en": description,
        })
    return rows


def relevance_score(query: str, text: str) -> float:
    ignore = {"a", "an", "the", "and", "of", "in", "on", "to", "as", "for", "from", "by", "news", "india", "latest", "with", "at", "is"}
    tokens = lambda s: {x for x in re.findall(r"[^\W_]{2,}", s.lower(), flags=re.UNICODE) if x not in ignore}
    a, b = tokens(query), tokens(text)
    return len(a & b) / max(len(a), 1)


def find_related(article: dict[str, Any], candidate_articles: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    results = []
    for other in candidate_articles:
        if other["id"] == article["id"] or other.get("is_demo"):
            continue
        score = relevance_score(article["title"], other["title"] + " " + other["description"])
        if score >= 0.17:
            results.append((score, other))
    results.sort(key=lambda p: (p[0], p[1]["published_at"]), reverse=True)
    seen = {article["fingerprint"]}
    unique = []
    for score, candidate in results:
        if candidate["fingerprint"] not in seen:
            seen.add(candidate["fingerprint"])
            unique.append({**candidate, "relevance": round(score, 2)})
        if len(unique) >= limit:
            break
    return unique

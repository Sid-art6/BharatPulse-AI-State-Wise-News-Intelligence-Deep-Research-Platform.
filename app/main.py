"""HTTP interface for the BharatPulse local news explorer."""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, core, research_v2, chat_v07
from .live import monitor
from .regions import REGIONS, TOPICS, LANGUAGES


@asynccontextmanager
async def lifespan(_app: FastAPI):
    core.init_db()
    core.save_articles(core.demo_fixtures())
    monitor.start()
    try:
        yield
    finally:
        await monitor.stop()


app = FastAPI(title="BharatPulse AI", description="Source-grounded, state-wise Indian news intelligence", version="0.7.0", lifespan=lifespan)
STATIC = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def validate_region(region: str) -> str:
    if region not in REGIONS:
        raise HTTPException(status_code=422, detail="Choose a valid Indian state, union territory, or All India")
    return region


def validate_topic(topic: str) -> str:
    if topic not in TOPICS:
        raise HTTPException(status_code=422, detail="Unknown topic")
    return topic


@app.get("/")
def homepage():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "BharatPulse AI", "version": "0.7.0"}


@app.get("/api/meta")
async def meta():
    return {
        "regions": REGIONS,
        "topics": TOPICS,
        "response_languages": list(LANGUAGES),
        "default_response_language": "English",
        "providers": {"google_news_rss": "implemented", "bbc_news_india_rss": "implemented_national", "x_api": "not_implemented", "google_trends": "not_implemented"},
        "auto_refresh_seconds": monitor.poll_seconds,
        "refresh_on_open": "check immediately; fetch when due (at most once per region per 5-minute window)",
        "multilingual": "regional RSS discovery; heuristic language detection; English excerpts are translated by selected LLM when configured",
        "llm_provider": ai.active_provider(),
        "llm_configured": await ai.llm_is_configured(),
        "llm_model": ai.active_model(),
        "llm_filter_enabled": ai.ENABLE_LLM_FILTER,
        "ollama_enabled": ai.ENABLE_OLLAMA,
        "ollama_ready": await ai.ollama_is_ready(),
        "ollama_model": ai.OLLAMA_MODEL,
        "limitations": "RSS snippets only; model-based semantic review is not independent fact-checking and cannot guarantee accuracy",
        "chat_workflow": "v0.7: atomic English claims -> exact RSS quote / number check -> semantic review -> verified translation -> cited draft or abstention",
        "research_workflow": "v2: RSS discovery, relevant excerpts, quoted findings, publication-only timeline",
    }


@app.post("/api/ai/check")
async def ai_connection_check():
    """An explicit probe; never returns credentials or untrusted provider messages."""
    try:
        return await ai.check_provider_connection()
    except ai.LLMServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/news")
def news(
    region: str = "All India",
    topic: str = "All topics",
    q: str = Query(default="", max_length=120),
    demo: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
):
    validate_region(region)
    validate_topic(topic)
    articles = core.list_articles(region=region, topic=topic, search=q, demo=demo, limit=limit)
    return {"items": articles, "count": len(articles), "demo": demo, "stats": core.dashboard_stats(demo)}


def validate_language(language: str) -> str:
    if language not in LANGUAGES:
        raise HTTPException(status_code=422, detail="Choose a supported response language")
    return language


class RefreshPayload(BaseModel):
    region: str = "All India"


@app.post("/api/news/refresh")
async def refresh_news(payload: RefreshPayload):
    region = validate_region(payload.region)
    try:
        return await monitor.refresh(region, force=True)
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"News provider is unavailable: {type(exc).__name__}. Try again later or use Demo mode.") from exc


@app.post("/api/news/watch")
async def watch_news(payload: RefreshPayload):
    region = validate_region(payload.region)
    monitor.watch(region)
    return monitor.status(region)


@app.get("/api/news/status")
def news_status(region: str = "All India"):
    validate_region(region)
    return monitor.status(region)


@app.get("/api/news/{article_id}")
def article(article_id: str):
    item = core.get_article(article_id)
    if not item:
        raise HTTPException(status_code=404, detail="Article not found")
    return item


@app.get("/api/stats")
def stats(demo: bool = False):
    return core.dashboard_stats(demo)


class ResearchPayload(BaseModel):
    language: str = "English"


@app.post("/api/research/{article_id}")
async def deep_research(article_id: str, payload: ResearchPayload = ResearchPayload()):
    """Explicit stages: discovery -> retrieval -> evidence anchoring -> report.

    Uses only RSS metadata; publication dates are NEVER labelled event dates.
    The structured report is checked for exact quoted evidence before display.
    """
    language = validate_language(payload.language)
    selected = core.get_article(article_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Article not found")
    if selected["is_demo"]:
        return {
            "article_id": article_id, "demo": True, "generated_by": "demo_notice",
            "answer": ai.no_information_message(language), "sources": [],
            "report": research_v2.initial_report([]),
            "caveat": "Illustrative demo content is not real reporting.",
            "stages": ["Demo content excluded from research"],
        }

    # Stage 1: discover related headlines on the known Google RSS origin only.
    # Article URLs are never fetched by this API: no arbitrary URL requests.
    short_title = re.sub(r"[^\w\s-]", " ", selected["title"])[:130]
    extra: list[dict[str, Any]] = []
    warning: str | None = None
    try:
        extra = core.parse_rss(await core.fetch_rss(f"{short_title} when:30d"), selected["region"])
        core.save_articles(extra)
    except (httpx.HTTPError, ValueError) as exc:
        warning = f"Follow-up RSS search failed ({type(exc).__name__}); stored reporting only."

    # Stage 2: retrieve relevant snippets from the current news store.
    from_store = core.list_articles(region="All India", demo=False, limit=100)
    related = core.find_related(selected, extra + from_store, limit=7)
    sources = [selected, *related]
    report = research_v2.initial_report(sources)
    mode = "insufficient_evidence"

    # Stage 3: request structured model evidence anchors; fail closed.
    if len(sources) >= 2 and await ai.llm_is_configured():
        try:
            report = await research_v2.generate_report(sources, language)
            mode = ai.active_provider() if report["findings"] else "insufficient_evidence"
        except (httpx.HTTPError, RuntimeError, ValueError, TypeError):
            mode = "source_index_llm_unavailable"
    elif len(sources) >= 2:
        mode = "source_index_no_llm"

    # Stage 4: always expose a deterministic publication-only timeline.
    # No claim of independent fact-checking is made.
    return {
        "article_id": article_id, "demo": False, "generated_by": mode,
        "answer": "Anchored research brief available." if report["findings"] else ai.no_information_message(language),
        "report": report,
        "sources": [{"index": i, **row} for i, row in enumerate(sources, 1)],
        "stages": [
            "Discover: search matching RSS feed metadata",
            f"Retrieve: {len(sources)} related headlines or excerpts",
            "Evidence check: exact-source quotes and numeric/citation screening",
            "Report: structured findings and publication-only timeline",
        ],
        "caveat": (
            "This is an RSS-level research brief, not full-article research. "
            "Quoted excerpts and matching keywords do not establish factual truth, independent confirmation, "
            "or semantic correctness. Human review of publisher articles is essential."
        ),
        "warning": warning,
    }


def evidence_fallback(sources: list[dict[str, Any]], language: str = "English") -> str:
    text = ai.no_information_message(language) + "\n\nSource index (not an AI answer):\n\n"
    for i, s in enumerate(sources, 1):
        text += f"[{i}] {s['publisher']} — {s['title']}\n"
    text += "\nNews-feed metadata and excerpts are not verified full articles. Inspect the original publisher links; matching headlines do not prove independent corroboration."
    return text


class ChatPayload(BaseModel):
    article_id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=2, max_length=1200)
    language: str = "English"


@app.post("/api/chat")
async def chat(payload: ChatPayload):
    language = validate_language(payload.language)
    selected = core.get_article(payload.article_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Article not found")
    if selected["is_demo"]:
        return {"answer": ai.no_information_message(language) + " [Illustrative demo content is not real reporting.]", "generated_by": "demo_notice", "sources": []}
    related = core.find_related(selected, core.list_articles(demo=False, limit=100), limit=5)
    sources = [selected, *related]
    if await ai.llm_is_configured():
        try:
            result = await chat_v07.answer_grounded(payload.question, sources, language)
            claims = result["claims"]
            if claims:
                answer = "\n\n".join(f"{claim['text']} [{claim['source']}]" for claim in claims)
                mode = ai.active_provider()
                used = {claim["source"] for claim in claims}
                visible_sources = [{"index": i, **row} for i, row in enumerate(sources, 1) if i in used]
            else:
                answer, mode = ai.no_information_message(language), "insufficient_evidence"
                visible_sources = [{"index": i, **row} for i, row in enumerate(sources, 1)]
        except (httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError):
            answer, mode = ai.no_information_message(language), "source_index_llm_unavailable"
            result = {"claims": [], "rejected_claims": 0, "reason": "provider_unavailable"}
            visible_sources = [{"index": i, **row} for i, row in enumerate(sources, 1)]
    else:
        answer, mode = ai.no_information_message(language), "source_index"
        result = {"claims": [], "rejected_claims": 0, "reason": "provider_unavailable"}
        visible_sources = [{"index": i, **row} for i, row in enumerate(sources, 1)]
    return {
        "answer": answer, "generated_by": mode,
        "sources": visible_sources,
        "claims": result["claims"],
        "rejected_claims": result["rejected_claims"],
        "evidence_status": result["reason"],
        "caveat": (
            "Source-anchored AI draft from RSS headlines and excerpts only. "
            "Automated quotation/semantic checks cannot establish factual truth or independent corroboration. "
            "Verify with primary sources before reporting."
        ),
    }

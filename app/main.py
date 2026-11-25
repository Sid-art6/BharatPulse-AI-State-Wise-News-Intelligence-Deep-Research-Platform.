"""HTTP interface for the BharatPulse local news explorer."""
from __future__ import annotations

import os
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from . import ai, core, research_v2, chat_v07, weather, research_agents_v09, answer_policy, chat_router_v1, chat_memory, context_engine, conditional_search, article_context
from .regional_sources_v10 import REGION_FEEDS, HINDU_FEEDS
from .live import monitor
from .regions import REGIONS, TOPICS, LANGUAGES
from .public_safety import public_safety_middleware, enabled


@asynccontextmanager
async def lifespan(_app: FastAPI):
    core.init_db()
    chat_memory.init_db()
    article_context.init_db()
    core.save_articles(core.demo_fixtures())
    monitor.start()
    try:
        yield
    finally:
        await monitor.stop()


app = FastAPI(title="BharatPulse AI", description="Source-grounded, state-wise Indian news intelligence", version="1.6.0", lifespan=lifespan,
                 docs_url=None if enabled('BHARATPULSE_PUBLIC_MODE') else '/docs',
                 redoc_url=None if enabled('BHARATPULSE_PUBLIC_MODE') else '/redoc')
allowed_hosts = [value.strip() for value in os.getenv('BHARATPULSE_ALLOWED_HOSTS', '').split(',') if value.strip()]
if allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
app.middleware('http')(public_safety_middleware)
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
    return {"status": "ok", "service": "BharatPulse AI", "version": app.version, "chat_revision": "v1.0-pass3-context-why", "validation_revision": "v1.0-final-context-audit", "context_revision": "v1.0-context-memory-rc", "identity_routing_revision": "v1.0-person-identity-fix", "short_question_revision": "v1.0-article-followup-qa", "session_memory": "article-isolated, 24h TTL"}


@app.get("/api/meta")
async def meta():
    return {
        "regions": REGIONS,
        "topics": TOPICS,
        "response_languages": list(LANGUAGES),
        "default_response_language": "English",
        "providers": {"scroll_direct_rss": "implemented_national", "google_news_rss": "implemented", "bbc_news_india_rss": "implemented_national", "indian_express_direct_rss": "implemented_curated_sections", "the_hindu_direct_rss": "implemented_selected_sections", "x_api": "not_implemented", "google_trends": "not_implemented"},
        "direct_publisher_feed_sections": len(REGION_FEEDS) + len(HINDU_FEEDS),
        "direct_publisher_feed_regions": len(REGION_FEEDS),
        "source_provenance": "feed_origin stored; RSS section affiliation is not independent confirmation",
        "auto_refresh_seconds": monitor.poll_seconds,
        "refresh_on_open": "check immediately; fetch when due (at most once per region per 5-minute window)",
        "multilingual": "regional RSS discovery; heuristic language detection; English excerpts are translated by selected LLM when configured",
        "llm_provider": ai.active_provider() if not enabled("BHARATPULSE_PUBLIC_MODE") or enabled("BHARATPULSE_PUBLIC_AI_ENABLED") else "none",
        "llm_configured": await ai.llm_is_configured() if not enabled("BHARATPULSE_PUBLIC_MODE") or enabled("BHARATPULSE_PUBLIC_AI_ENABLED") else False,
        "llm_model": ai.active_model(),
        "llm_filter_enabled": ai.ENABLE_LLM_FILTER,
        "ollama_enabled": ai.ENABLE_OLLAMA,
        "ollama_ready": await ai.ollama_is_ready() if not enabled("BHARATPULSE_PUBLIC_MODE") else False,
        "ollama_model": ai.OLLAMA_MODEL,
        "limitations": "Selected articles may be read from publicly accessible publisher pages, subject to access and robots restrictions. If unavailable, RSS-only answers are clearly labelled. Model review is not fact-checking.",
        "chat_context": "selected RSS metadata is supplied for term disambiguation",
        "chat_memory": "first-party cookie, SQLite, isolated per article, five turns, 24h expiry, explicit clear",
        "external_search": "optional targeted Google News RSS discovery on explicit freshness requests; off by default, no paid search API",
        "chat_workflow": "v1.4: background publisher-page retrieval -> cached article evidence -> question-relevant source passages -> quote/numeric review -> cited response or safe RSS fallback",
        "research_workflow": "Six connected LangGraph stages; cached publisher evidence when accessible plus source-tiered RSS discovery, reviewed findings and explicit evidence gaps",
        "research_engine": "LangGraph StateGraph (stateless per request, no cross-user memory)",
        "public_demo": enabled("BHARATPULSE_PUBLIC_MODE"),
        "public_ai_enabled": enabled("BHARATPULSE_PUBLIC_AI_ENABLED"),
        "langsmith_tracing": (
            "configured" if (os.getenv("LANGSMITH_TRACING", "false").lower() in {"true", "1", "yes"}
                             and bool(os.getenv("LANGSMITH_API_KEY", "").strip())
                             and not os.getenv("LANGSMITH_API_KEY", "").startswith("PASTE_"))
            else "disabled"
        ),
        "weather": {"status": "implemented", "provider": "Open-Meteo", "days": 7, "cities": len(weather.CITY_CATALOG), "map": "city point temperatures", "no_unsupported_forecasts": True},
    }


@app.post("/api/ai/check")
async def ai_connection_check():
    """An explicit probe; never returns credentials or untrusted provider messages."""
    try:
        return await ai.check_provider_connection()
    except ai.LLMServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc




# Weather Intelligence (v0.8): provider-derived, city-specific readings.
@app.get("/api/weather/cities")
def weather_cities():
    return {"items": weather.cities(), "source": "Representative India city coordinates"}


@app.get("/api/weather/forecast")
async def weather_forecast(city: str = Query(default="Bengaluru", max_length=80)):
    if city not in weather.CITY_INDEX:
        raise HTTPException(status_code=422, detail="Choose a listed Indian city")
    try:
        return await weather.fetch_forecast(city)
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail="Current weather forecast is unavailable. Try again later.") from exc


@app.get("/api/weather/map")
async def weather_map():
    return await weather.fetch_map_weather()


@app.get("/api/weather/news")
def weather_related_news(region: str = "Karnataka"):
    validate_region(region)
    items = weather.weather_news(region)
    return {"items": items, "count": len(items), "region": region,
            "caveat": "Indexed RSS titles and excerpts only; headlines are not official weather warnings."}


class WeatherChatPayload(BaseModel):
    city: str = Field(min_length=2, max_length=80)
    question: str = Field(min_length=2, max_length=800)
    language: str = "English"


@app.post("/api/weather/chat")
async def weather_chat(payload: WeatherChatPayload):
    language = validate_language(payload.language)
    if payload.city not in weather.CITY_INDEX:
        raise HTTPException(status_code=422, detail="Choose a listed Indian city")
    try:
        forecast = await weather.fetch_forecast(payload.city)
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail="Weather data is unavailable; AI cannot provide a current forecast.") from exc
    answer = await weather.weather_answer(forecast, payload.question, language)
    return {**answer, "city": payload.city, "forecast_fetched_at": forecast["fetched_at"],
            "news_note": "Weather-related news is shown separately; it is not forecast evidence."}

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


@app.post("/api/article-context/{article_id}/prepare")
async def prepare_article_context(article_id: str):
    """Fast, idempotent request: retrieval runs in a bounded background task."""
    selected = core.get_article(article_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"article_id": article_id, **article_context.schedule(selected)}


@app.get("/api/article-context/{article_id}")
async def article_context_status(article_id: str):
    """Only expose readiness/provenance, never hidden article context."""
    selected = core.get_article(article_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Article not found")
    if selected.get('is_demo'):
        return {"article_id": article_id, "status": "demo"}
    row = article_context.get_cached(article_id)
    status = article_context.public_status(row) if row and article_context._fresh(row) else {"status": "not_started"}
    if article_id in article_context._inflight:
        status = {"status": "loading"}
    return {"article_id": article_id, **status}


@app.get("/api/stats")
def stats(demo: bool = False):
    return core.dashboard_stats(demo)


class ResearchPayload(BaseModel):
    language: str = "English"
    question: str = Field(default="", max_length=500)


@app.post("/api/research/{article_id}")
async def deep_research(article_id: str, payload: ResearchPayload = ResearchPayload()):
    """v0.9 LangGraph multi-stage RSS research, fail-closed on model issues."""
    language = validate_language(payload.language)
    selected = core.get_article(article_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Article not found")
    if selected["is_demo"]:
        return {
            "article_id": article_id, "demo": True, "generated_by": "demo_notice",
            "answer": ai.no_information_message(language), "sources": [],
            "report": research_v2.initial_report([]),
            "workflow": {"engine": "LangGraph StateGraph", "version": "1.2", "trace": [],
                         "review_status": "demo_excluded", "source_count": 0, "approved_findings": 0},
            "caveat": "Illustrative demo content is not real reporting.",
            "stages": ["Demo content excluded from research"],
        }
    try:
        context = await article_context.ensure(selected, timeout=22.0)
        evidence_selected = article_context.attach(selected, context, payload.question)
        return await research_agents_v09.run_research(evidence_selected, language, payload.question)
    except RuntimeError as exc:
        # Includes LangGraph dependency not installed; never leak raw provider
        # or RSS response strings and never invent research claims.
        raise HTTPException(status_code=503, detail="Research workflow is unavailable. Install requirements and check the server logs.") from exc


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


@app.get("/api/chat/history")
def chat_history(article_id: str, request: Request):
    if not core.get_article(article_id):
        raise HTTPException(status_code=404, detail="Article not found")
    token = request.cookies.get(chat_memory.COOKIE_NAME)
    turns = chat_memory.read_turns(token, article_id) if chat_memory.valid_session(token) else []
    return {"article_id": article_id, "turns": turns, "retention_hours": chat_memory.RETENTION_HOURS}


class ClearChatPayload(BaseModel):
    article_id: str = Field(min_length=1, max_length=80)


@app.post("/api/chat/clear")
def clear_chat(payload: ClearChatPayload, request: Request):
    token = request.cookies.get(chat_memory.COOKIE_NAME)
    removed = chat_memory.clear_turns(token, payload.article_id) if chat_memory.valid_session(token) else 0
    return {"cleared": True, "deleted_turns": removed}


@app.post("/api/chat")
async def chat(payload: ChatPayload, request: Request, response: Response):
    if not core.get_article(payload.article_id):
        raise HTTPException(status_code=404, detail="Article not found")
    token = request.cookies.get(chat_memory.COOKIE_NAME)
    if not chat_memory.valid_session(token):
        token = chat_memory.new_session()
        response.set_cookie(
            chat_memory.COOKIE_NAME, token, httponly=True, samesite='lax',
            secure=enabled('BHARATPULSE_PUBLIC_MODE'), max_age=24 * 3600, path='/',
        )
    history = chat_memory.read_turns(token, payload.article_id)
    result = await _chat_answer(payload, history)
    if result.get('generated_by') != 'demo_notice':
        chat_memory.save_turn(token, payload.article_id, payload.question, result.get('answer', ''))
    for claim in result.get("claims", []):
        claim.pop("context", None)
    result["sources"] = [article_context.public_source(s) for s in result.get("sources", [])]
    return {**result, 'context_revision': 'v1.0-context-memory-rc', 'memory_turns_used': len(history)}


async def _chat_answer(payload: ChatPayload, history: list[dict[str, Any]] | None = None):
    language = validate_language(payload.language)
    selected = core.get_article(payload.article_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Article not found")
    if selected["is_demo"]:
        return {"answer": ai.no_information_message(language) + " [Illustrative demo content is not real reporting.]", "generated_by": "demo_notice", "sources": []}

    if answer_policy.METADATA_QUESTIONS.search(payload.question):
        answer, cited = answer_policy.answer_metadata(payload.question, selected)
        return {"answer": answer, "generated_by": "source_metadata", "intent": "metadata",
                "sources": cited, "claims": [], "rejected_claims": 0,
                "evidence_status": "rss_metadata_only", "caveat": "Time supplied by the feed."}
    context = await article_context.ensure(selected, timeout=22.0)
    evidence_selected = article_context.attach(selected, context, payload.question)
    related = core.find_related(selected, core.list_articles(demo=False, limit=100) + core.candidate_articles(selected), limit=7)
    sources = chat_router_v1.dedupe_sources(evidence_selected, related)
    sources = await conditional_search.maybe_enrich(payload.question, selected, sources)
    sources = [sources[0], *(s for s in sources[1:] if s.get("relationship") == "possible_same_story")]
    question_intent = answer_policy.article_intent(payload.question, selected, chat_router_v1.intent(payload.question))
    # A request for a conceptual definition is not a request to infer this
    # particular article's causes, actors or court decision.
    if not re.search(r"\b(?:his|her|their|this decision|this ruling|for this|in this case)\b", payload.question, re.I) and re.match(r"^\s*(?:what\s+does\s+.{2,85}\s+mean(?:\s+in\s+.+)?|define\s+.{2,85})\s*[?.!]*$", payload.question, re.I):
        question_intent = 'general'
    # Named-person and event-specific questions MUST use source evidence,
    # even if only RSS metadata is available. No invented biographies.
    elif question_intent in {'general', 'mixed'}:
        # A genuine, locally defined acronym/term stays conceptual; a named
        # person's biography or an event-specific request stays evidence-only.
        cached_definition = chat_router_v1.reference_definition(
            payload.question, str(selected.get('title') or ''), selected)
        if cached_definition is None and (
                chat_router_v1.person_identity_query(payload.question) or
                re.search(r'\b(?:allegations?|accused|why|who\s+is|what\s+happened|reason|previous|background|charges?|court|decision|role|appointment)\b', payload.question, re.I)):
            question_intent = 'article' 
    logging.getLogger("bharatpulse.qa").info("chat route=%s source_count=%s article=%s", question_intent, len(sources), str(selected.get('id',''))[:24])
    memory_context = chat_memory.last_context(history or [])
    explicit_article_question = context_engine.resolve_elliptical_article_question(payload.question, selected)
    grounded_question = context_engine.user_followup(explicit_article_question, history or [])
    full_article = context.get('status') == 'ready' and evidence_selected.get('evidence_origin') == 'publisher_article'
    caveat = (("Source-anchored AI draft from accessible publisher article text; quotes are not independently verified. "
               "Automated review can make mistakes. Check the linked original source. " ) if full_article else
              ("Source-anchored AI draft from RSS headlines and excerpts only. "
               "The original article was not accessible for a permitted full-text read. "
               "Automated review cannot establish factual truth."))

    if context.get("status") == "loading":
        caveat = "Publisher retrieval is still running. This answer uses currently indexed evidence."

    if question_intent in {"source_list", "later_events"}:
        if question_intent == "source_list":
            answer, cited = answer_policy.answer_source_list(sources)
        else:
            answer, cited = answer_policy.answer_later_events(sources)
        return {"answer": answer, "generated_by": f"source_{question_intent}",
                "intent": question_intent, "sources": cited, "claims": [],
                "rejected_claims": 0, "evidence_status": "rss_metadata_only", "caveat": caveat}

    if question_intent in {"evidence", "summary", "overview"}:
        if full_article and question_intent in {"evidence", "summary"}:
            answer = f'{sources[0]["publisher"]} reports [1]\n“{sources[0]["description"][:450]}”'
            cited = [{"index": 1, **sources[0]}]
        elif question_intent == "evidence":
            answer, cited = chat_router_v1.evidence_answer(sources)
        elif question_intent == "overview":
            answer, cited = chat_router_v1.source_overview(sources)
        else:
            answer, cited = chat_router_v1.excerpt_summary(sources)
        return {"answer": answer, "generated_by": f"source_{question_intent}",
                "intent": question_intent, "sources": cited, "claims": [],
                "rejected_claims": 0, "evidence_status": "publisher_article" if full_article else "rss_metadata_only", "caveat": caveat}

    if question_intent == "general" and (chat_router_v1.person_identity_query(payload.question)
                                         or (re.search(r"^\s*who\s+(?:is|was)\s+", payload.question, re.I)
                                             and context_engine.abbreviation(payload.question) is None
                                             and chat_router_v1.reference_definition(payload.question, str(selected.get('title') or ''), selected) is None)):
        return {"answer": ("A biographical identity cannot be reliably verified from the selected "
                           "RSS headline and excerpt alone. Please consult an attributable biography "
                           "or primary source; I will not invent a person's background."),
                "generated_by": "insufficient_evidence", "intent": "general",
                "sources": [{"index": 1, **selected}], "claims": [], "rejected_claims": 0,
                "evidence_status": "identity_not_verified", "caveat": caveat}

    if question_intent in {"general", "mixed"}:
        # A curated definition can be shown without charging Groq, but unknown
        # general questions still require an explicitly configured provider.
        if not await ai.llm_is_configured() and chat_router_v1.reference_definition(payload.question, str(selected.get("title") or ""), selected) is None:
            return {"answer": ai.no_information_message(language), "generated_by": "ai_unavailable",
                    "intent": question_intent, "sources": [], "claims": [], "rejected_claims": 0,
                    "evidence_status": "provider_unavailable", "caveat": "General AI explanations require a configured provider."}
        background_question, news_question = (
            chat_router_v1.split_mixed(payload.question) if question_intent == "mixed"
            else (payload.question, "")
        )
        try:
            # Every concept query sees the selected RSS context, not only a
            # hardcoded set of acronyms. The article remains untrusted data.
            background = await chat_router_v1.general_answer(
                background_question, language, str(selected.get('title') or ''),
                selected, memory_context,
            )
            if not answer_policy.general_answer_firewall(background_question, background, selected):
                answer, cited = chat_router_v1.limited_article_answer(payload.question, sources)
                return {"answer": answer, "generated_by": "insufficient_evidence", "intent": "article",
                        "sources": cited, "claims": [], "rejected_claims": 1,
                        "evidence_status": "general_answer_rejected_article_leak", "caveat": caveat}
            if question_intent == "general":
                origin = "general_reference" if chat_router_v1.reference_definition(background_question, str(selected.get('title') or ''), selected) is not None else "general_ai"
                # An optional one-line *separately labelled* selected-headline
                # reference helps readers relate a definition to the article.
                # It is not a model-generated news claim and cannot establish
                # allegations, causes, or full-article details.
                title = str(selected.get('title') or '')
                is_relevant = (
                    (chat_router_v1._police_complaint(background_question)
                     and 'police complaint' in title.casefold())
                    or ('passport' in background_question.casefold()
                        and 'passport' in title.casefold())
                    or (context_engine.abbreviation(background_question) is not None
                        and context_engine.abbreviation(background_question).casefold() in title.casefold())
                    or (chat_router_v1.reference_definition(background_question, title, selected) is not None
                        and ('fir' in background_question.casefold() or 'tvk' in background_question.casefold())
                        and ('tvk' in title.casefold() or 'police' in title.casefold()))
                )
                cited = []
                if is_relevant:
                    background += (f"\n\nSelected RSS headline (not independent verification): "
                                   f"“{title}” [1]. The headline alone does not establish further details.")
                    cited = [{"index": 1, **selected}]
                return {"answer": background, "generated_by": origin, "intent": question_intent,
                        "sources": cited, "claims": [], "rejected_claims": 0,
                        "evidence_status": "general_knowledge_with_rss_headline" if cited else "general_knowledge_not_article_evidence",
                        "caveat": "General background is separate from the selected RSS report; its headline is not independent fact-checking."}

            # A mixed request has two separate evidence standards. Use the RSS
            # summary when it asks what the article says; otherwise run the
            # reviewed article answer path. Never treat general knowledge as a
            # news citation or silently copy it into an article claim.
            if chat_router_v1.intent(news_question) in {"summary", "overview", "evidence"}:
                article_text, cited = chat_router_v1.excerpt_summary(sources)
                reviewed = {"claims": [], "rejected_claims": 0, "reason": "rss_metadata_only"}
            elif not await ai.llm_is_configured():
                article_text, cited = chat_router_v1.limited_article_answer(news_question, sources)
                reviewed = {"claims": [], "rejected_claims": 0, "reason": "provider_unavailable"}
            else:
                reviewed = await chat_v07.answer_grounded(news_question, sources, language)
                claims = [row for row in reviewed["claims"]
                          if answer_policy.claim_answers_question(news_question, row)]
                reviewed = {**reviewed, "claims": claims}
                if claims:
                    article_text = "\n".join(f"{row['text']} [{row['source']}]" for row in claims)
                    used = {row["source"] for row in claims}
                    cited = [{"index": i, **row} for i, row in enumerate(sources, 1) if i in used]
                else:
                    article_text, cited = chat_router_v1.limited_article_answer(news_question, sources)
            return {"answer": f"General background:\n{background}\n\nWhat the RSS reports:\n{article_text}",
                    "generated_by": "mixed_ai", "intent": question_intent, "sources": cited,
                    "claims": reviewed["claims"], "rejected_claims": reviewed["rejected_claims"],
                    "evidence_status": reviewed["reason"],
                    "caveat": "The general explanation is separate from the cited RSS reporting; neither is independent fact-checking."}
        except (ai.LLMServiceError, httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError):
            return {"answer": ai.no_information_message(language), "generated_by": "ai_unavailable",
                    "intent": question_intent, "sources": [], "claims": [], "rejected_claims": 0,
                    "evidence_status": "provider_unavailable", "caveat": "The AI provider did not respond; no background information was invented."}

    # An RSS excerpt describing election-security preparations can explain
    # what is reported without inventing a particular threat or incident.
    security_context = context_engine.election_security_context_answer(payload.question, sources)
    if security_context:
        answer, visible_sources = security_context
        return {"answer": answer, "generated_by": "source_security_context",
                "intent": question_intent, "sources": visible_sources,
                "claims": [], "rejected_claims": 0,
                "evidence_status": "partial_election_security_context",
                "caveat": caveat}

    # If the selected report explicitly quotes the legal argument for seeking
    # court action, present that attributed argument instead of discarding it.
    legal_evidence = context_engine.legal_argument_answer(payload.question, sources)
    if legal_evidence:
        answer, visible_sources = legal_evidence
        return {"answer": answer, "generated_by": "source_argument",
                "intent": question_intent, "sources": visible_sources,
                "claims": [], "rejected_claims": 0,
                "evidence_status": "reported_legal_argument_not_court_finding",
                "caveat": caveat}

    # An answer to "why" must establish an actual reason, not just repeat
    # the event. If the *selected* RSS headline/excerpt has no explicit
    # causal evidence, show that gap immediately (without a needless LLM
    # completion that may convert "on the way to" into a false cause).
    if (chat_router_v1.question_requires_cause(payload.question)
            and not any(chat_router_v1.selected_rss_has_cause([s]) for s in sources)):
        answer, visible_sources = chat_router_v1.limited_article_answer(payload.question, sources)
        return {
            "answer": answer, "generated_by": "insufficient_evidence",
            "intent": question_intent, "sources": visible_sources,
            "claims": [], "rejected_claims": 0,
            "evidence_status": "reason_not_established_by_selected_rss",
            "caveat": caveat,
        }

    if await ai.llm_is_configured():
        try:
            result = await chat_v07.answer_grounded(grounded_question, sources, language)
            claims = [row for row in result["claims"]
                      if answer_policy.claim_answers_question(payload.question, row)]
            if claims and chat_router_v1.question_requires_cause(payload.question):
                # A generic event restatement is not an answer to "why".
                claims = [claim for claim in claims if
                          chat_router_v1.EXPLICIT_CAUSE.search(str(claim.get('text') or ''))
                          and chat_router_v1.EXPLICIT_CAUSE.search(str(claim.get('quote') or ''))]
            if claims:
                answer = "\n\n".join(f"{row['text']} [{row['source']}]" for row in claims)
                mode = ai.active_provider()
                used = {row["source"] for row in claims}
                visible_sources = [{"index": i, **row} for i, row in enumerate(sources, 1) if i in used]
                result = {**result, "claims": claims}
            else:
                direct = chat_router_v1.requested_passage(payload.question, sources)
                if direct:
                    answer, visible_sources = direct
                    mode = "source_passage"
                    result = {"claims": [], "rejected_claims": result.get("rejected_claims", 0),
                              "reason": "direct_source_passage_after_unapproved_draft"}
                else:
                    answer, visible_sources = chat_router_v1.limited_article_answer(payload.question, sources)
                    mode = "insufficient_evidence"
                    result = {"claims": [], "rejected_claims": result.get("rejected_claims", 0),
                              "reason": "insufficient_evidence"}
        except (ai.LLMServiceError, httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError):
            direct = chat_router_v1.requested_passage(payload.question, sources)
            if direct:
                answer, visible_sources = direct
                answer = "AI review unavailable; the following is directly quoted source text:\n\n" + answer
            else:
                answer, visible_sources = chat_router_v1.limited_article_answer(payload.question, sources)
                answer = "AI review unavailable; the following is indexed evidence only:\n\n" + answer
            mode = "ai_unavailable"
            result = {"claims": [], "rejected_claims": 0, "reason": "provider_unavailable"}
    else:
        answer, visible_sources = chat_router_v1.limited_article_answer(payload.question, sources)
        extract = chat_router_v1.requested_passage(payload.question, sources)
        if extract:
            answer, visible_sources = extract
        mode = "source_passage" if extract else "source_index"
        result = {"claims": [], "rejected_claims": 0, "reason": "provider_unavailable"}
    return {
        "answer": answer, "generated_by": mode, "intent": question_intent,
        "sources": visible_sources,
        "claims": result["claims"],
        "rejected_claims": result["rejected_claims"],
        "evidence_status": result["reason"],
        "caveat": caveat,
    }

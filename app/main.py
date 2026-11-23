"""HTTP interface for the BharatPulse local news explorer."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, core, research_v2, chat_v07, weather, research_agents_v09
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


app = FastAPI(title="BharatPulse AI", description="Source-grounded, state-wise Indian news intelligence", version="0.9.0", lifespan=lifespan)
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
    return {"status": "ok", "service": "BharatPulse AI", "version": "0.9.0"}


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
        "research_workflow": "v0.9: LangGraph planner -> RSS discovery -> excerpt retrieval -> quoted synthesis -> semantic review -> report / abstention",
        "research_engine": "LangGraph StateGraph (stateless per request, no cross-user memory)",
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
            "workflow": {"engine": "LangGraph StateGraph", "version": "0.9", "trace": [],
                         "review_status": "demo_excluded", "source_count": 0, "approved_findings": 0},
            "caveat": "Illustrative demo content is not real reporting.",
            "stages": ["Demo content excluded from research"],
        }
    try:
        return await research_agents_v09.run_research(selected, language, payload.question)
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

from fastapi.testclient import TestClient
from app.main import app


def test_health_and_demo_dashboard(monkeypatch, tmp_path):
    from app import core
    monkeypatch.setattr(core, "DATA_DIR", tmp_path)
    monkeypatch.setattr(core, "DB_PATH", tmp_path / "test.db")
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        r = client.get("/api/news", params={"demo": "true"})
        assert r.status_code == 200
        assert r.json()["count"] >= 10
        assert all(x["is_demo"] for x in r.json()["items"])
        assert r.json()["stats"]["regions_covered"] >= 5
        live = client.get("/api/news", params={"demo": "false"})
        assert live.status_code == 200
        assert live.json()["count"] == 0
        assert client.get("/api/news", params={"region": "Atlantis"}).status_code == 422
        item = r.json()["items"][0]
        assert client.get(f"/api/news/{item['id']}").status_code == 200
        research = client.post(f"/api/research/{item['id']}").json()
        assert research["demo"] is True and research["sources"] == []
        response = client.post("/api/chat", json={"article_id": item["id"], "question": "What happened?"})
        assert response.status_code == 200
        assert response.json()["generated_by"] == "demo_notice"
        assert client.post("/api/chat", json={"article_id": "none", "question": "What happened?"}).status_code == 404
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200


def test_refresh_saves_only_feed_metadata(monkeypatch, tmp_path):
    import asyncio
    from app import ai, core
    from app.live import monitor
    monkeypatch.setattr(core, "DATA_DIR", tmp_path)
    monkeypatch.setattr(core, "DB_PATH", tmp_path / "test.db")

    # Unit tests should not depend on live Groq credentials, rate limits or
    # background national feed polling. The region refresh is still exercised.
    async def offline_filter(articles):
        return articles, "test_offline_filter"

    async def offline_previews(_articles):
        return {}

    async def idle_national_poller():
        await asyncio.Event().wait()

    monkeypatch.setattr(ai, "optional_llm_filter", offline_filter)
    monkeypatch.setattr(ai, "english_previews", offline_previews)
    monkeypatch.setattr(monitor, "_run", idle_national_poller)

    async def stub(region):
        return core.parse_rss(b'''<rss><channel><item><title>Assam rail update - Paper</title><link>https://news.google.com/rss/articles/xyz</link><description>Assam rail update</description><source>Paper</source></item></channel></rss>''', region)
    monkeypatch.setattr(core,"fetch_news",stub)
    with TestClient(app) as client:
        r = client.post("/api/news/refresh", json={"region":"Assam"})
        # The app now refreshes national headlines as soon as it starts.
        # The same item may have been indexed before this manual check.
        assert r.status_code == 200 and r.json()["added"] in (0, 1)
        r2 = client.post("/api/news/refresh", json={"region":"Assam"})
        assert r2.json()["added"] == 0
        news = client.get("/api/news",params={"region":"Assam","demo":"false"}).json()
        assert news["count"] == 1
        assert news["items"][0]["region_confidence"] == "explicit"


def test_watch_on_open_schedules_live_ingestion(monkeypatch, tmp_path):
    """Opening a region starts a due background fetch with no manual refresh."""
    import asyncio
    import time
    from app import ai, core
    from app.live import monitor
    monkeypatch.setattr(core, "DATA_DIR", tmp_path)
    monkeypatch.setattr(core, "DB_PATH", tmp_path / "test.db")

    # Test regional on-open scheduling without competing external requests or
    # LLM calls; do not weaken the endpoint's behavioural assertions.
    async def offline_filter(articles):
        return articles, "test_offline_filter"

    async def offline_previews(_articles):
        return {}

    async def idle_national_poller():
        await asyncio.Event().wait()

    monkeypatch.setattr(ai, "optional_llm_filter", offline_filter)
    monkeypatch.setattr(ai, "english_previews", offline_previews)
    monkeypatch.setattr(monitor, "_run", idle_national_poller)

    async def stub(region):
        return core.parse_rss(
            f'<rss><channel><item><title>{region} rail update</title>'
            f'<link>https://regional.example/{region.replace(" ", "-")}</link>'
            f'<description>{region} transport update</description>'
            '</item></channel></rss>'.encode(), region)

    monkeypatch.setattr(core, "fetch_news", stub)
    with TestClient(app) as client:
        result = client.post('/api/news/watch', json={'region': 'Karnataka'})
        assert result.status_code == 200
        for _ in range(50):
            cached = client.get('/api/news', params={'region': 'Karnataka'}).json()
            if cached['count']:
                break
            time.sleep(.03)
        assert cached['count'] == 1
        status = client.get('/api/news/status', params={'region':'Karnataka'}).json()
        assert status['poll_seconds'] == 300
        assert status['last_success'] is not None


def test_real_article_research_abstains_when_no_followup_evidence(monkeypatch, tmp_path):
    import pytest
    pytest.importorskip("langgraph")  # Actual StateGraph; no simulation.
    from app import core
    monkeypatch.setattr(core, "DATA_DIR", tmp_path)
    monkeypatch.setattr(core, "DB_PATH", tmp_path / "test.db")

    async def no_fetch(_region):
        return []

    async def no_followup(_query):
        return b'<rss><channel/></rss>'

    monkeypatch.setattr(core, "fetch_news", no_fetch)
    monkeypatch.setattr(core, "fetch_rss", no_followup)
    with TestClient(app) as client:
        original = core.parse_rss(b'<rss><channel><item><title>Karnataka new proposal</title>'
                                   b'<link>https://example.org/story</link><description>Karnataka topic</description>'
                                   b'</item></channel></rss>', 'Karnataka')
        core.save_articles(original)
        response = client.post('/api/research/' + original[0]['id'], json={'language': 'Kannada'})
        assert response.status_code == 200
        assert response.json()['generated_by'] == 'insufficient_evidence'
        assert response.json()['sources'][0]['title'] == 'Karnataka new proposal'

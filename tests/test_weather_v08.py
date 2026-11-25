"""Offline tests for weather provider parsing, API, map and evidence-bound responses."""
import pytest
from fastapi.testclient import TestClient
from app import weather
from app.main import app


def sample_weather():
    return {
        "timezone": "Asia/Kolkata",
        "current": {"time": "2026-11-23T14:00", "temperature_2m": 25.7,
                    "relative_humidity_2m": 68, "wind_speed_10m": 8.3, "weather_code": 2},
        "daily": {
            "time": [f"2026-11-{d:02d}" for d in range(23, 30)],
            "temperature_2m_max": [30.0] * 7,
            "temperature_2m_min": [20.0] * 7,
            "precipitation_probability_max": [40] * 7,
            "precipitation_sum": [1.5] * 7,
            "weather_code": [3] * 7,
        }
    }


def test_city_catalog_and_provider_result():
    assert len(weather.CITY_CATALOG) >= 36
    assert len({row[1] for row in weather.CITY_CATALOG}) == 36
    result = weather._normalise_forecast(sample_weather(), "Bengaluru")
    assert len(result["daily"]) == 7
    assert result["current"]["temperature_c"] == 25.7
    assert result["daily"][0]["description"] == "Overcast"
    assert result["region"] == "Karnataka"
    with pytest.raises(ValueError):
        weather._normalise_forecast({"daily": {"time": ["2026-11-23"]}}, "Bengaluru")
    with pytest.raises(KeyError):
        weather._normalise_forecast(sample_weather(), "Atlantis")


def test_canonical_answer_preserves_provider_figures():
    result = weather._normalise_forecast(sample_weather(), "Bengaluru")
    default = weather.canonical_answer(result, "Is there rain in the next few days?")
    assert default.count("precipitation total") == 3
    assert "1.5 mm" in default and "40%" in default
    assert "official warnings" in default
    assert weather.canonical_answer(result, "tomorrow").count("precipitation total") == 1
    assert weather.canonical_answer(result, "next week").count("precipitation total") == 7


def test_weather_answer_english_without_llm(monkeypatch):
    import asyncio
    result = weather._normalise_forecast(sample_weather(), "Bengaluru")
    value = asyncio.run(weather.weather_answer(result, "tomorrow", "English"))
    assert value["language"] == "English" and value["generated_by"] == "forecast_data"
    assert "20.0–30.0 °C" in value["answer"]


def test_weather_unverified_translation_falls_back(monkeypatch):
    import asyncio
    result = weather._normalise_forecast(sample_weather(), "Bengaluru")
    async def yes(): return True
    async def reject(*args, **kwargs): return []
    monkeypatch.setattr(weather.ai, 'llm_is_configured', yes)
    monkeypatch.setattr(weather.chat_v07, '_translate_and_verify', reject)
    value = asyncio.run(weather.weather_answer(result, "tomorrow", "Hindi"))
    assert value["language"] == "English"
    assert "Translation could not be verified" in value["caveat"]


def test_weather_endpoints_offline(monkeypatch, tmp_path):
    from app import core
    monkeypatch.setattr(core, "DATA_DIR", tmp_path)
    monkeypatch.setattr(core, "DB_PATH", tmp_path / "test.db")
    async def fake_forecast(city):
        return weather._normalise_forecast(sample_weather(), city)
    async def fake_map():
        return {"points": [{"city": "Bengaluru", "temperature_c": 25.7, "latitude": 12.97, "longitude": 77.59}]}
    monkeypatch.setattr(weather, "fetch_forecast", fake_forecast)
    monkeypatch.setattr(weather, "fetch_map_weather", fake_map)
    with TestClient(app) as client:
        assert client.get("/api/health").json()["version"] == '1.6.0'
        assert client.get("/api/weather/cities").json()["items"]
        result = client.get("/api/weather/forecast", params={"city": "Bengaluru"})
        assert result.status_code == 200 and len(result.json()["daily"]) == 7
        assert client.get("/api/weather/forecast", params={"city": "Atlantis"}).status_code == 422
        assert client.get("/api/weather/map").json()["points"][0]["temperature_c"] == 25.7
        response = client.post("/api/weather/chat", json={"city": "Bengaluru", "question": "Tomorrow weather", "language": "English"})
        assert response.status_code == 200 and response.json()["source"] == "Open-Meteo"
        assert client.post("/api/weather/chat", json={"city": "Bengaluru", "question": "Hello", "language": "Esperanto"}).status_code == 422
        assert client.get("/api/weather/news", params={"region": "Atlantis"}).status_code == 422


def test_weather_news_never_uses_demo(monkeypatch, tmp_path):
    from app import core
    monkeypatch.setattr(core, "DATA_DIR", tmp_path)
    monkeypatch.setattr(core, "DB_PATH", tmp_path / "news.db")
    core.init_db()
    live = core.parse_rss(b'<rss><channel><item><title>Karnataka rain alert</title>'
                          b'<link>https://example.org/weather</link><description>Karnataka rainfall forecast</description>'
                          b'</item></channel></rss>', 'Karnataka')
    core.save_articles(live)
    result = weather.weather_news("Karnataka")
    assert len(result) == 1 and result[0]["id"] == live[0]["id"]
    assert weather.weather_news("Maharashtra") == []

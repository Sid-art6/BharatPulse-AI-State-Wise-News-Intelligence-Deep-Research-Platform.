"""v0.8 weather intelligence: provider-derived forecasts, mapped city samples, news discovery.

Forecast measurements always come from Open-Meteo, never from an LLM. No fabricated
weather fixtures are presented as live observations. Named cities are representative
points, not state-wide forecasts or official severe-weather alerts.
"""
from __future__ import annotations

import asyncio
import copy
import re
import time
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from . import ai, chat_v07, core

PROVIDER_URL = "https://api.open-meteo.com/v1/forecast"
TTL_SECONDS = 600
# Representative cities, approximate centre coordinates. Forecasts apply to the
# selected point, never to the entire named state or union territory.
CITY_CATALOG: tuple[tuple[str, str, float, float], ...] = (
    ("Amaravati", "Andhra Pradesh", 16.57, 80.36),
    ("Itanagar", "Arunachal Pradesh", 27.09, 93.61),
    ("Guwahati", "Assam", 26.14, 91.74),
    ("Patna", "Bihar", 25.61, 85.14),
    ("Raipur", "Chhattisgarh", 21.25, 81.63),
    ("Panaji", "Goa", 15.50, 73.83),
    ("Ahmedabad", "Gujarat", 23.03, 72.58),
    ("Gurugram", "Haryana", 28.46, 77.03),
    ("Shimla", "Himachal Pradesh", 31.10, 77.17),
    ("Ranchi", "Jharkhand", 23.34, 85.31),
    ("Bengaluru", "Karnataka", 12.97, 77.59),
    ("Kochi", "Kerala", 9.93, 76.27),
    ("Bhopal", "Madhya Pradesh", 23.26, 77.41),
    ("Mumbai", "Maharashtra", 19.08, 72.88),
    ("Imphal", "Manipur", 24.82, 93.94),
    ("Shillong", "Meghalaya", 25.58, 91.89),
    ("Aizawl", "Mizoram", 23.73, 92.72),
    ("Kohima", "Nagaland", 25.67, 94.11),
    ("Bhubaneswar", "Odisha", 20.30, 85.82),
    ("Ludhiana", "Punjab", 30.90, 75.85),
    ("Jaipur", "Rajasthan", 26.91, 75.79),
    ("Gangtok", "Sikkim", 27.34, 88.61),
    ("Chennai", "Tamil Nadu", 13.08, 80.27),
    ("Hyderabad", "Telangana", 17.38, 78.49),
    ("Agartala", "Tripura", 23.83, 91.28),
    ("Lucknow", "Uttar Pradesh", 26.85, 80.95),
    ("Dehradun", "Uttarakhand", 30.32, 78.03),
    ("Kolkata", "West Bengal", 22.57, 88.36),
    ("Port Blair", "Andaman and Nicobar Islands", 11.67, 92.74),
    ("Chandigarh", "Chandigarh", 30.73, 76.78),
    ("Daman", "Dadra and Nagar Haveli and Daman and Diu", 20.42, 72.83),
    ("New Delhi", "Delhi", 28.61, 77.21),
    ("Srinagar", "Jammu and Kashmir", 34.08, 74.83),
    ("Leh", "Ladakh", 34.15, 77.58),
    ("Kavaratti", "Lakshadweep", 10.57, 72.64),
    ("Puducherry", "Puducherry", 11.93, 79.83),
    ("Pune", "Maharashtra", 18.52, 73.86),
    ("Mysuru", "Karnataka", 12.30, 76.65),
    ("Thiruvananthapuram", "Kerala", 8.52, 76.94),
)
CITY_INDEX = {row[0]: row for row in CITY_CATALOG}
MAP_CITIES = ("New Delhi", "Mumbai", "Bengaluru", "Kolkata", "Chennai", "Hyderabad", "Jaipur", "Lucknow", "Guwahati", "Srinagar", "Ahmedabad", "Thiruvananthapuram")
# Bounded in-memory cache; resets at process restart, no sensitive data.
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_locks: dict[str, asyncio.Lock] = {}


def cities() -> list[dict[str, Any]]:
    return [{"city": city, "region": region, "latitude": lat, "longitude": lon}
            for city, region, lat, lon in CITY_CATALOG]


def weather_description(code: int | None) -> str:
    labels = {0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
              45: "Fog", 48: "Freezing fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
              56: "Freezing drizzle", 57: "Heavy freezing drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
              66: "Freezing rain", 67: "Heavy freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
              77: "Snow grains", 80: "Light rain showers", 81: "Rain showers", 82: "Heavy rain showers",
              85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorms", 96: "Thunderstorms with hail",
              99: "Severe thunderstorms with hail"}
    return labels.get(code, "Condition unavailable")


def _float_value(value: Any) -> float | None:
    if type(value) not in (float, int) or not -10000 < value < 10000:
        return None
    return float(value)


def _normalise_forecast(payload: dict[str, Any], city: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("daily"), dict):
        raise ValueError("Weather provider returned incomplete daily forecast data")
    current = payload.get("current") or {}
    daily = payload["daily"]
    required = ("time", "temperature_2m_max", "temperature_2m_min", "precipitation_probability_max", "precipitation_sum", "weather_code")
    if any(not isinstance(daily.get(k), list) or len(daily[k]) < 7 for k in required):
        raise ValueError("Weather provider returned an incomplete seven-day forecast")
    days = []
    for i in range(7):
        day = daily["time"][i]
        if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise ValueError("Weather provider returned invalid forecast dates")
        values = {k: _float_value(daily[k][i]) for k in required[1:-1]}
        code = daily["weather_code"][i]
        if any(v is None for v in values.values()) or type(code) is not int:
            raise ValueError("Weather provider returned invalid forecast measurements")
        days.append({"date": day, **values, "weather_code": code, "description": weather_description(code)})
    name, region, latitude, longitude = CITY_INDEX[city]
    return {"city": name, "region": region, "latitude": latitude, "longitude": longitude,
            "timezone": payload.get("timezone", "Asia/Kolkata"), "provider": "Open-Meteo",
            "provider_url": "https://open-meteo.com/en/docs", "fetched_at": datetime.now(timezone.utc).isoformat(),
            "current": {"time": current.get("time"), "temperature_c": _float_value(current.get("temperature_2m")),
                        "humidity_percent": _float_value(current.get("relative_humidity_2m")),
                        "wind_kmh": _float_value(current.get("wind_speed_10m")),
                        "weather_code": current.get("weather_code") if type(current.get("weather_code")) is int else None,
                        "description": weather_description(current.get("weather_code"))},
            "daily": days,
            "note": "Seven-day model forecast for the selected city coordinates, not a state-wide forecast or official warning."}


async def _request_forecast(city: str) -> dict[str, Any]:
    _, _, latitude, longitude = CITY_INDEX[city]
    params = {"latitude": latitude, "longitude": longitude, "timezone": "Asia/Kolkata", "forecast_days": 7,
              "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
              "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,weather_code"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=8), follow_redirects=False) as client:
        response = await client.get(PROVIDER_URL, params=params)
        response.raise_for_status()
        if len(response.content) > 300_000:
            raise ValueError("Weather provider response is too large")
        return _normalise_forecast(response.json(), city)


async def fetch_forecast(city: str) -> dict[str, Any]:
    if city not in CITY_INDEX:
        raise ValueError("Choose a supported Indian city")
    key = "forecast:" + city
    existing = _cache.get(key)
    if existing and time.monotonic() - existing[0] < TTL_SECONDS:
        return copy.deepcopy(existing[1])
    # Avoid duplicated provider calls from simultaneous page loads.
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        existing = _cache.get(key)
        if existing and time.monotonic() - existing[0] < TTL_SECONDS:
            return copy.deepcopy(existing[1])
        result = await _request_forecast(city)
        _cache[key] = (time.monotonic(), result)
        return copy.deepcopy(result)


async def fetch_map_weather() -> dict[str, Any]:
    # Fetch only curated, bounded city coordinates. No arbitrary URL requests.
    results = await asyncio.gather(*(fetch_forecast(city) for city in MAP_CITIES), return_exceptions=True)
    points = []
    for city, result in zip(MAP_CITIES, results):
        name, region, lat, lon = CITY_INDEX[city]
        current = result.get("current", {}) if isinstance(result, dict) else {}
        points.append({"city": name, "region": region, "latitude": lat, "longitude": lon,
                       "temperature_c": current.get("temperature_c"),
                       "description": current.get("description"),
                       "available": isinstance(result, dict)})
    return {"points": points, "provider": "Open-Meteo", "note": "City point readings only; not a continuous heatmap, weather radar, or official alert layer."}


WEATHER_TERMS = ("weather", "rain", "rainfall", "flood", "cyclone", "storm", "monsoon", "heatwave", "heat wave", "cold wave", "thunder", "hail", "temperature", "landslide",
                 "मौसम", "बारिश", "बाढ़", "चक्रवात", "वर्षा", "पाऊस", "मಳೆ", "ಮಳೆ", "ಹವಾಮಾನ", "மழை", "வானிலை", "వర్షం", "వాతావరణ", "മഴ", "കാലാവസ്ഥ", "বৃষ্টি", "আবহাওয়া")


def weather_news(region: str, *, limit: int = 12) -> list[dict[str, Any]]:
    # Existing RSS index only. Absence of a headline is not an absence of an event.
    rows = core.list_articles(region=region, demo=False, limit=100)
    results = []
    for row in rows:
        text = (row.get("title", "") + " " + row.get("description", "")).lower()
        if any((re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", text) if term.isascii() else term in text) for term in WEATHER_TERMS):
            results.append({k: row.get(k) for k in ("id", "title", "publisher", "published_at", "url", "region", "language")})
            if len(results) >= limit:
                break
    return results


def _days_for_question(question: str, daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    q = question.lower()
    if re.search(r"\bday after tomorrow\b", q):
        return daily[2:3]
    if any(w in q for w in ("tomorrow", "कल", "ನಾಳೆ", "நாளை")):
        return daily[1:2]
    if any(w in q for w in ("today", "आज", "ಇಂದು", "இன்று")):
        return daily[:1]
    if any(w in q for w in ("week", "seven", "7 day", "7-day", "सप्ताह", "ವಾರ", "வாரம்")):
        return daily
    return daily[:3]


def canonical_answer(forecast: dict[str, Any], question: str) -> str:
    """A deterministic answer backed only by forecast JSON, not LLM freeform prose."""
    days = _days_for_question(question, forecast["daily"])
    if not days:
        return "I cannot provide a forecast because no forecast days were returned."
    lines = [f"Open-Meteo model forecast for {forecast['city']}, {forecast['region']} (Asia/Kolkata time)."]
    for day in days:
        lines.append(f"{day['date']}: {day['description']}; temperature {day['temperature_2m_min']:.1f}–{day['temperature_2m_max']:.1f} °C; "
                     f"maximum precipitation probability {day['precipitation_probability_max']:.0f}%; forecast precipitation total {day['precipitation_sum']:.1f} mm.")
    lines.append("These are weather-model forecasts, not guarantees or official warnings. Forecast details can change as models update.")
    return "\n".join(lines)


async def weather_answer(forecast: dict[str, Any], question: str, language: str) -> dict[str, Any]:
    english = canonical_answer(forecast, question)
    result = {"answer": english, "generated_by": "forecast_data", "language": "English", "source": "Open-Meteo",
              "source_url": forecast["provider_url"], "caveat": "Forecasts are model estimates for one city point. Groq is not predicting weather independently."}
    if language == "English":
        return result
    if not await ai.llm_is_configured():
        return {**result, "caveat": "Translation unavailable: no configured AI model. Showing the source-grounded English forecast."}
    # Reuse v0.7 translation+equivalence review; reject extra quantities/facts.
    try:
        translated_lines = []
        for offset in range(0, len(english.splitlines()), 3):
            lines = english.splitlines()[offset:offset + 3]
            translated = await chat_v07._translate_and_verify(
                [{"id": i + 1, "claim_en": line} for i, line in enumerate(lines)], language)
            if len(translated) != len(lines):
                break
            translated_lines.extend(entry["text"] for entry in translated)
        if len(translated_lines) == len(english.splitlines()):
            return {**result, "answer": "\n".join(translated_lines), "language": language,
                    "generated_by": ai.active_provider() + "_reviewed_translation"}
    except (ai.LLMServiceError, httpx.HTTPError, ValueError, RuntimeError):
        pass
    return {**result, "caveat": "Translation could not be verified. Showing the source-grounded English forecast."}

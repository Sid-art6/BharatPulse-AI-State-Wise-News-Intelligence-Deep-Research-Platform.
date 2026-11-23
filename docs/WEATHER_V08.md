# BharatPulse AI v0.8 — Weather Intelligence

## What the new section does

- Select an Indian city from the supported city list. City coordinates are fixed by the backend and correspond to 28 states and 8 union territories; some states have multiple cities.
- Read **current model conditions** (temperature, relative humidity and wind), and **7 daily forecast entries** (min/max temperature, maximum precipitation probability, precipitation total, WMO condition description).
- Use an interactive **Leaflet/OpenStreetMap** map. Choosing a city from the dropdown **automatically recentres the map and highlights that location**, including cities without a temperature marker in the 12-city overview. Clicking a temperature marker also changes the selected city, the forecast cards and weather-news region. The highlighted location shows the latest selected-city temperature once fetched. This is **not a national radar, continuous weather surface, or official warning map**.
- See a list of weather-related RSS articles matching regional headlines/excerpts. These come from the **existing news index**; there is no separate complete weather-news provider. Use **Research** or **Ask AI** on those cards to open the news evidence workflow.
- Ask Weather AI about the coming days. The English response is constructed from the real provider JSON values, not an LLM forecast. Other languages use the existing Groq/Ollama translation and a separate equivalence check; failure returns the English forecast with an explanation.

## Technical flow

```text
City select → /api/weather/forecast → fixed backend coordinates → Open-Meteo
           → validated JSON + 10-minute cache → forecast cards
           → map city markers via /api/weather/map
           → weather chatbot /api/weather/chat
              → deterministic forecast summary → optional reviewed translation
Region from city → /api/news/watch → existing RSS storage → /api/weather/news
                 → keyword-based news list → existing article Research/Ask AI
```

## Weather API endpoints

| Endpoint | Description |
|---|---|
| `GET /api/weather/cities` | Supported city/region coordinates |
| `GET /api/weather/forecast?city=Bengaluru` | Current values and seven-day model forecast |
| `GET /api/weather/map` | Curated city-point temperature markers |
| `GET /api/weather/news?region=Karnataka` | Matching news articles from indexed RSS |
| `POST /api/weather/chat` | `{ "city": "Bengaluru", "question": "Will it rain tomorrow?", "language": "Hindi" }` |

## Accuracy, privacy and usage boundaries

- Do not label forecast data as a confirmed future event. Probabilities are estimates and can change.
- Timezone is explicitly set to `Asia/Kolkata` in the weather provider request.
- Forecast is one coordinate; it does not describe the weather throughout an entire state.
- Weather API errors return unavailable messages; no fabricated live weather samples are presented.
- The Open-Meteo public endpoint is offered for **non-commercial** usage; verify licensing, service limits and attribution before public or paid deployment: https://open-meteo.com/en/docs
- Map uses OpenStreetMap standard tiles; follow the OSM tile use policy, show attribution, and select a suitable tile provider for public/large-scale traffic: https://operations.osmfoundation.org/policies/tiles/
- Leaflet is loaded from a public CDN; map tiles and library loading need internet access. Forecast cards can work without a map if tiles/CDN fail.
- No official India Meteorological Department warning feed is integrated. Always consult official sources for severe-weather alerts.
- Groq responses are translations/explanations of supplied data, not an independent forecasting model. Claims about weather news use source-indexed article excerpts and require editorial review.

## Tests

From the project root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Tests mock provider responses; passing does not establish live availability or complete meteorological accuracy.

# BharatPulse AI · Local News Intelligence

**Browse Indian news by state → discover regional reporting → research related headlines → ask a source-grounded AI.**

A runnable, local-first prototype using **FastAPI, SQLite, JavaScript, RSS and optional GroqCloud or Ollama**. v0.7 adds conservative claim-by-claim chat review on top of automatic feeds, multilingual discovery, and RSS-level research. It is an **MVP, not a production-deployed service or an independently verified newsroom fact-checker**.

## What's implemented in v0.7

| Capability | Actual behaviour |
|---|---|
| **Open app → refresh check** | The browser asks the server to watch its selected region; if that region's feed was not checked within the last **5 minutes**, a background fetch begins immediately. Cached news is displayed while fetching. |
| **Every 5 minutes** | While the FastAPI process runs, it polls **All India** and regions recently viewed in a browser. The UI synchronises with the database every **20 seconds** while visible. This is polling, **not provider push**. |
| **Regions** | 28 Indian states, 8 union territories, and All India; region tags require a detectable mention, rather than relying solely on the search query. |
| **Multilingual ingestion** | Google News RSS searches in English plus a regional-language locale where supported by the chosen region. Native-script titles and excerpts remain unchanged. Language detection uses heuristic Unicode script rules. |
| **English previews** | Original English RSS excerpts appear by default. For non-English excerpts, the configured **Groq API or local Ollama** can generate a bounded English translation preview (up to 12 pending excerpts per refresh). Without an enabled LLM, the original-language excerpt is clearly labelled **not translated**. |
| **Response language** | Choose **English (default)**, Hindi, Bengali, Tamil, Telugu, Kannada, Malayalam, Marathi, Gujarati, Punjabi, Odia, Assamese or Urdu for the optional AI chat and research brief. |
| **Sources** | Google News RSS metadata, regional-language Google News searches, and BBC India RSS for national coverage. These do **not** imply direct integrations with every publisher. |
| **AI filtering** | Optional Groq or Ollama screens up to 20 **new** headlines per regional feed check for news relevance (previously indexed or rejected headlines are not repeatedly screened); without it, deterministic cleaning, deduplication, region and topic tagging still work. |
| **Research** | Searches related RSS metadata, calls Groq/Ollama for structured JSON claims with literal quotation anchors, screens claims for excerpt/source alignment and unsupported figures, then renders source-linked findings, explicit unknowns and a **publication-only** timeline. It politely abstains when evidence is insufficient. No full-text crawling. |
| **Chat v0.7** | Generates short **atomic English claims** for the selected article and related RSS metadata. Requires an exact quotation from the claimed source, checks citation indices and figures, and uses a separate model-based semantic entailment review. Only approved claims may be translated; translations receive a separate equivalence check. Fails closed to a polite insufficient-evidence response if review fails. Shows supporting quotes and cited publisher links. This reduces risk but is **not a factual-accuracy guarantee**. |
| **No evidence** | The service responds politely that available sources do not establish the answer, including a selected-language fallback even without a model. |
| **Demo mode** | Clearly fictional articles, isolated from real live news. |

### What is **not** implemented

- Direct X API, Google Trends, or direct regional publisher API integrations; these need authorisation and provider-by-provider licensing review.
- Licensed full-article ingestion, real-time push notifications, guaranteed coverage for every region/language, or a verified fake-news detector.
- LangGraph multi-agent orchestration, semantic vector search, independent fact-checking, human editorial approvals, user accounts, rate limiting, cloud deployment, or production monitoring. v0.7 uses a model-based semantic *review*, not authoritative entailment verification.
- Guaranteed accuracy of model-written translations or AI claims. **RSS snippets are short, incomplete, unverified source descriptions** and citations are numerical references, not independent verification.

## Development roadmap

Feature status describes **implemented and tested work**, not production-readiness. ✓ does not mean that independent factual accuracy or live third-party availability has been certified.

| Version | Planned improvement | Status |
|---|---|---|
| **v0.6** | Live RSS news, Groq RAG, multilingual responses, RSS-grounded research | ✓ Complete (previous release) |
| **v0.7** | Quote-anchored chat claims, multilingual translation review, safer abstentions | ✓ Implemented; **49 offline tests passed** — live Groq retest pending |
| **v0.8** | LangGraph multi-agent Deep Research orchestration | ○ Planned |
| **v0.9** | Expanded regional publishers, licensing review and improved retrieval | ○ Planned |
| **v0.10** | Weather intelligence: current conditions, 7-day forecast and weather news | ○ Planned |
| **v0.11** | Interactive India weather map and geospatial visualisations | ○ Planned |
| **v0.12** | Multilingual weather chatbot and evidence-backed weather research | ○ Planned |
| **v1.0** | Security hardening, monitoring, evaluation and deployment-readiness review | ○ Planned |

**Note:** Weather forecasts will come from an authorised forecasting service (not from LLM predictions). Groq will explain forecast measurements and source-backed weather news; weather features are *not yet implemented*.

## Run on Windows (PowerShell)

**Requirements:** Python 3.11/3.12, internet to install dependencies, network access to news feeds for live mode. No Node.js or paid APIs required.

1. Extract the ZIP, for example to `C:\Projects\bharatpulse-ai`.
2. Open **PowerShell** in that directory (the one containing `requirements.txt`).
3. Run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

4. Open **http://127.0.0.1:8000** in your browser. It starts in **Live RSS** mode and checks feed freshness automatically. The first fetch may take several seconds. Check the **Last success** indicator. If your network blocks news feeds, switch to **Demo data**.
5. Choose a state, then choose an **AI response language**. Each selected state is monitored while in use. Open any news card and click **Research** or **Ask AI**.
6. Stop with `Ctrl+C`. SQLite saves news at `data/news.db`.

**Status/API:** [health](http://127.0.0.1:8000/api/health), [metadata](http://127.0.0.1:8000/api/meta), [Swagger](http://127.0.0.1:8000/docs).

**If you use Python 3.12**, replace `py -3.11` with `py -3.12`. If `py` is not recognised, inspect your local Python installation.

## Run on Linux / WSL / macOS

```bash
cd bharatpulse-ai
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In WSL you can usually open `http://127.0.0.1:8000` in the Windows browser. Python 3.12 also works.

## Groq API (recommended) — Windows, beginner setup

See **[docs/GROQ_WINDOWS_SETUP.md](docs/GROQ_WINDOWS_SETUP.md)** for exact staged steps for the Windows/VS Code laptop. No Docker, WSL, Node.js or Ollama is required.

1. Copy `.env.example` to `.env` in the project folder (beside `requirements.txt`). Edit it **locally** in VS Code:

```ini
LLM_PROVIDER=groq
GROQ_API_KEY=your_actual_secret_key_here
GROQ_MODEL=openai/gpt-oss-20b
ENABLE_LLM_FILTER=true
BHARATPULSE_POLL_SECONDS=300
```

2. Install the new dependency (included in `requirements.txt`) and start the server:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The `.env` file is now loaded automatically by Python at startup. **Do not share the key, put it in a screenshot, or commit `.env`**. `.gitignore` excludes it. Restart the server after editing `.env`.

3. Open `http://127.0.0.1:8000`, click **Test AI connection**, then open a live headline and try **Ask AI** or **Research**. The test performs one small Groq inference request. You can also inspect `GET /api/meta` for `llm_provider` and `llm_configured`; **configured does not mean connection was verified**.

**Optional Ollama instead:** install Ollama and pull `qwen2.5:3b`. In `.env`, use `LLM_PROVIDER=ollama`, `ENABLE_OLLAMA=true` and `OLLAMA_MODEL=qwen2.5:3b`; restart the FastAPI server. There is no automatic fallback between providers in v0.7: the chosen provider must work or the app displays its source index without LLM synthesis.

**Usage and limits:** Groq has rate limits and may bill under certain plans. The RSS refresh remains every five minutes, but LLM screening runs only for newly discovered headlines. Chat and research can trigger additional requests. Original RSS text is preserved; generated English previews are machine translations, not guaranteed fact checks. 401 means the key is invalid; 429 means your account hit a rate limit.

## Feed refresh settings

Default polling is **300 seconds (5 minutes)**. The browser checks feed status every **20 seconds** but those checks do not trigger a network fetch every 20 seconds.

```powershell
$env:BHARATPULSE_POLL_SECONDS="300"
```

Set this **before** starting the server. The application enforces a minimum of 300 seconds to avoid excessive requests. Open/reopen a page: the browser always asks the server to check freshness, but an additional provider request is skipped if the selected region was checked less than 5 minutes ago. News checks operate **only while FastAPI is running**. Manual **Fetch live news** can explicitly retry a provider.

**Providers can fail, rate-limit or delay their feeds.** The status distinguishes the latest attempt, success, a fetch in progress, and failure. Previous cached articles remain available on failure. Polling isn't an instant breaking-news stream.

## Verify it

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Run from the folder containing `requirements.txt`. The suite includes parsing, regional script recognition, Unicode deduplication, startup/live-refresh API flows, response-language validation, conservative claim and quotation gates, rejected figures, semantic-review failures, mistranslation handling, research citation validation and publication-only timestamps. Feed requests are mocked in tests; **successful live external RSS access cannot be guaranteed until tested on your machine**.

## Architecture

```text
Open dashboard ──► FastAPI /api/news/watch ──► is a feed check due?
                                                   │
                                    yes ──► RSS: English + regional query
                                                   │
                                 clean + preserve original source metadata
                                                   │
                         Unicode dedup + region/topic/language tagging
                                                   │
                             optional Groq/Ollama relevance and translation
                                                   │
                                        SQLite article store
                                                   │
Browser (every 20 sec) ◄── FastAPI news/status + news articles
      │
      ├── Research v2 ► RSS discovery ► Groq/Ollama JSON ► excerpt-quote checks ► structured report
      └── Ask AI v0.7 ► source-only claim proposals (English + exact quotations)
                        ► deterministic quote/index/number checks
                        ► second LLM entailment review
                        ► translate approved claims (only when selected language ≠ English)
                        ► second translation-equivalence review
                        ► supported claim cards + cited links, or honest abstention
```

The research flow is documented in **[docs/RESEARCH_V2.md](docs/RESEARCH_V2.md)**. The v0.7 chatbot checks and limitations are in **[docs/CHAT_V07.md](docs/CHAT_V07.md)**. Upgrading from your working Windows v0.6 GitHub checkout? Read **[docs/WINDOWS_UPGRADE_V07.md](docs/WINDOWS_UPGRADE_V07.md)**.

For v0.7, chat may use 2 model calls for English and up to 4 for other supported languages. This can increase latency and Groq rate-limit usage. The LLM does not independently browse the internet. News text is untrusted input. Do not upload private data or use this MVP for official reporting or consequential decisions without editorial review, permissions and evidence verification.

For a beginner-friendly explanation of both this project and **Globalmove-AI**, see [`docs/BEGINNER_GUIDE.md`](docs/BEGINNER_GUIDE.md). The genuinely production-grade roadmap is in [`docs/NEXT_STAGES.md`](docs/NEXT_STAGES.md).

# BharatPulse AI — Context-First Chat and Lightweight Memory Candidate

This is an **offline-tested release candidate**, not a guarantee of production readiness or live Groq answer accuracy. It builds on the last v1.0 context-QA candidate without replacing News, Deep Research or Weather.

## Root cause corrected

Earlier, `What is SIR?` went to a general LLM prompt with no selected-article context; the model could select an epidemiology meaning even though the selected article discussed voter lists. The revised `general_answer` receives **the actual server-stored RSS title, excerpt, region and topic** for every definition query. It uses that metadata for **disambiguation, not for treating a headline as independently verified fact**.

- Short uppercase acronym queries are routed generically, not restricted to FIR/TVK/BJP.
- When an RSS record explicitly supplies a full form in parentheses, the application checks that the initials actually match before using it.
- The election context for SIR is handled with a low-cost built-in definition: **Special Intensive Revision of electoral rolls**; no Groq call is needed.
- Unrecognised terms fall back to **one context-aware general LLM call**, with instructions to admit ambiguity rather than invent a definition. This is not a deterministic correctness guarantee.
- Action questions such as `What is BJP doing?` remain article-specific rather than receiving a glossary answer.
- In court-dispute stories, a selected RSS excerpt explicitly saying `Karnataka argued that …` can answer **what legal argument was reported** without presenting the claim as a Supreme Court finding. If it does not provide a reason for an event, the assistant still abstains.

## Low-cost conversation memory

- First-party SQLite storage: at most **five turns per selected article and anonymous browser session**.
- A randomly generated session token is placed in an **HttpOnly, SameSite=Lax cookie**; only its SHA-256 digest is stored server-side. Cookies are marked `Secure` in public mode (which should be served over HTTPS).
- Each article has its own conversation thread. User history from another browser session is not returned by the history API.
- Only previous user questions, **not previous AI outputs**, are supplied for reference resolution, so an old hallucination is not silently turned into evidence.
- The TTL is **24 hours**. Existing entries are pruned during startup and writes; expired entries are excluded from reads. Users can clear memory for one article in the UI or via `/api/chat/clear`.
- This is **anonymous, short-term memory**, not login-backed user profiles or cross-device long-term memory. Browser cookie deletion or Render `/tmp` restarts reset it. SQLite is not encrypted at rest by this project.

## Optional on-demand RSS discovery

Set `BHARATPULSE_ENABLE_ON_DEMAND_RSS_SEARCH=true` in local `.env` to enable server-initiated **Google News RSS** searches only on explicit freshness/related-news questions (for example, `What are the latest updates?`). The query is built from the **server-stored selected headline**, not a user-controlled URL. Results are deduplicated, relevance-ranked and cached for ten minutes per article in process memory.

This adds **no paid search API** and is disabled by default to avoid extra network load or surprise latency. It is *not* full web search or full publisher-article retrieval; the retrieved content is still feed headlines and excerpts. RSS providers can throttle, change or fail. The application falls back to cached evidence.

## Provider cost boundary

- Known glossary terms and source-only responses can use **zero LLM calls**.
- Unknown general concepts aim for **one Groq call**, with bounded article and recent-user-question context.
- Existing source-grounded claim generation intentionally uses a separate model-based semantic review (and translation review where relevant). **Do not claim every article question costs one LLM call.** Token limits, provider quotas and hosting still require monitoring.
- A key is never shipped with the candidate ZIP. The public demo continues to disable AI by default.

## QA and Windows tests

```powershell
cd "C:\Users\Administrator\Downloads\BharatPulse-AI-v1.0-Context-First-Memory-Candidate\bharatpulse-ai"
$python = "C:\Users\Administrator\Downloads\a\bharatpulse-AI\.venv\Scripts\python.exe"
& $python -m pytest -q
& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Expect `context_revision = v1.0-context-memory-rc`.

**Manual prompts for the selected headlines:**

1. Election voter-list story: `What is SIR?` → **Special Intensive Revision**, not the epidemiology model.
2. Collector/TVK story: `What is FIR?` → **First Information Report**.
3. Same story: `Who is TVK?` → political party, not MLA/person.
4. Karnataka Cauvery case: `Why has Karnataka approached the Supreme Court?` → cite the **reported legal argument** if the excerpt contains it, distinguish from a court decision.
5. Tamil Nadu detention story: `Why was the BJP chief detained?` → do **not** substitute `on the way to a ceremony` for the grounds of detention.
6. On an article, ask `What is SIR?` followed by `How does it affect the voter lists?`. Check that prior questions are relevant, without reusing unsupported AI assertions.
7. Reopen the selected article to see saved messages, then use `Clear this article conversation`. Another browser/private window should not see the first window's history.
8. With the feature flag ON, try `What are the latest updates?`; it may retrieve additional Google News RSS entries, but must **not** claim to have read a full article.

**Scope of automated QA:** the tests mock Groq and RSS. The source-grounding path, session boundaries and FastAPI responses are tested, but **real Groq answers, 6 LangGraph tests skipped when LangGraph is absent, HTTPS cookie behaviour behind Render, and browser rendering remain to be checked on Windows and after deployment**.

## Production work remaining

This remains a candidate for a controlled portfolio demo. Before unrestricted public AI or real multi-tenant production use, add durable encrypted storage, consent/privacy disclosure, authentication or strictly hardened anonymous-session protection, deployment-level rate limits/spend controls, metrics, abuse testing, legally compliant licensed article access where full text is required, and live-provider evaluations. Never present RSS metadata as full article coverage.

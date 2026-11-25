# Version 1.3 — question-aware evidence and research reporting

- Fixed named-person compound requests and expanded deterministic publisher metadata routing.
- Added explicit question-slot relevance checks to prevent irrelevant but true headline restatements.
- Added `research_insights.py` for deterministic source highlights, gap mapping and safe question-aware supplementary RSS discovery.
- Connected the Research Report Builder to source highlights and question coverage, without treating unreviewed statements as AI-approved claims.
- Updated the frontend to display distinct source reporting and missing evidence clearly; unverified national-feed geography is labelled as such.
- Included offline regression tests and a localhost-only smoke-test script.
- Included the hermetically mocked `test_api.py` to avoid the previous Windows no-provider false failure.

---

## v1.1 — Reliability & Intelligence Upgrade (24 Nov 2026)

- Corrected selected-article versus general-definition routing with generic, incident-independent rules.
- Restricted topical context as evidence for the chosen incident; publisher lists distinguish context from possible same-story reporting.
- Preserved six explicit LangGraph stages, including skipped synthesis and review when no model is ready.
- Tightened unsupported follow-up assumptions, citation gates and reviewer context.
- Added platform-wide synthetic regression coverage and RSS numeral display improvements.
- Existing data sources remain RSS title/excerpt metadata; no independent full-text or fact verification is claimed.

## v1.0 candidate — Consolidated audit corrections (unreleased)

- Intent-aware article chat: separate general knowledge, mixed questions, article summary/evidence index, and conservative RSS-grounded reporting.
- Persistent chat output quality: correct banners for source-based responses, eliminate repeated caveats within a conversation, keep citations source-specific.
- News search now visible; multiple tokens match indexed metadata, stale AJAX responses are discarded, and Reset Filters restores the feed.
- Deep Research shows literal source-by-source RSS excerpt coverage, preserving actual six-stage LangGraph quality gates without invented claims.
- Public-demo security: per-client plus global AI quotas, streamed request-body cap, RSS and weather/news read quotas; no API keys in the bundle.
- News UI shows explicit AI connection status; additional offline regression tests cover audit failures.
- Still requires full Windows regression and public Render deployment validation before release.

# Changelog

## v0.10 — Regional RSS discovery and evidence quality (Windows test candidate)

- Added **29 curated publisher-hosted RSS sections (25 Indian Express, 4 The Hindu)**: direct publisher-hosted news metadata alongside Google News discovery, with a fixed allowlist and up to two extra requests per watched region where supported.
- Added partial-feed failure tolerance, section-based location classification at lower confidence and `feed_origin` persistence/migration for existing SQLite databases.
- Added conservative source-diversity-aware ranking of related RSS sources; near-identical headlines are deprioritised, not assumed copied or independently corroborated.
- Added deterministic research coverage signals: number of distinct publisher **labels**, possible similar-headline groups, and exact numerical expressions from headline/excerpt data with source indices.
- Updated research UI and source cards to show origin and evidence comparison, always labelled as unverified metadata.
- Retained the v0.9 real LangGraph graph, Groq, v0.8 weather/map, and v0.7 multilingual chat. LangSmith is optional and off by default.
- Added offline regression tests; real LangGraph package and live direct-feed access must be verified on user's Windows laptop before pushing.
- **Important:** Publisher feeds are not licensed full-article APIs. Review attribution, feed terms, rate limits and commercial redistribution rights before external use.

## v0.9 — LangGraph Deep Research and opt-in LangSmith tracing (Windows integration candidate)

- Added **real LangGraph StateGraph** orchestration with planning, RSS discovery, stored-source retrieval, model-based synthesis, semantic quality review, and report assembly; conditional branch to abstention/source index without LLM.
- Added an optional research question/angle and an inspectable stage timeline in the existing Research drawer.
- Preserved exact source-quote, citation index, number checks, separate semantic review, publication-only timeline and controlled abstentions.
- Added **LangSmith opt-in observability** using standard `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT`; model completions can appear as child traces. Local `.env` is never bundled or committed.
- Added mocked offline tests for rejection, fallback and conditional routing; **real LangGraph and LangSmith integration on Windows remains to be verified**.
- No Node.js, Docker, vector database, full-text scraping or automated independent fact-checking.


## v0.8 — Weather Intelligence (local test candidate)

- Weather map sync improvement: selecting any supported city automatically centres and highlights its map location; clicking map markers updates the selected city and forecast. Selection remains visible even for cities outside the initial 12 temperature markers.

- Added a separate Weather Intelligence section without introducing Node.js or mandatory Docker.
- Added Open-Meteo current model readings and seven-day weather forecast cards for a curated city list covering Indian states/UTs.
- Added a Leaflet map with selected Indian city-point temperature markers, not a continuous radar/heatmap.
- Added weather-related headlines from the existing regional RSS index with article Research and Ask AI actions.
- Added provider-grounded forecast Q&A with optional multilingual translation and equivalence review using the existing Groq/Ollama integration.
- Added bounded 10-minute in-memory forecast caching and safe failure handling.
- Added offline weather API/normalisation tests, preserving the v0.7 tests. Live provider access and model translations still require testing on the user's laptop.
- **Caveats:** Model predictions, not official weather warnings; regional news snippets are not official meteorological bulletins. Open-Meteo free endpoint is for non-commercial usage; OSM tile service conditions apply.



## v0.7 — Multilingual chat grounding (local candidate)

- Added atomic English claim generation with exact source-indexed RSS quotes.
- Added deterministic checks for source index, exact quotation, numeric and currency assertions.
- Added mandatory model-based entailment review and post-translation equivalence review.
- Added explicit quoted evidence under chatbot answers, only citations actually used in accepted claims, and controlled abstentions on failed checks.
- Added test scenarios for invented source numbers, invented quotes/figures, polarity reversal and multilingual translation drift.
- Updated README roadmap with accurately marked completed and planned stages.
- Existing 5-minute polling, Groq/Ollama provider selection, SQLite store and structured Research v2 remain intact.
- **Caveat:** This is excerpt-level evidence review, not independently verified reporting; real Groq output still needs checking on Windows.

## v0.6 — Deep Research v2

- Structured source-linked research briefs from RSS snippets.
- Exact quotation and numerical grounding checks, publication-only timeline, multilingual research text and safe insufficient-evidence fallback.

# Changelog

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

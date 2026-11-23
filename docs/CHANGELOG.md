# Changelog

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

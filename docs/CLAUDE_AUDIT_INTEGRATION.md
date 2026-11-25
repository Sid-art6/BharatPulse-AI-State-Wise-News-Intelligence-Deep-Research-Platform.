# Claude audit cross-check — BharatPulse AI v1.2

This version uses the v1.1 source as its baseline and incorporates high-impact,
platform-wide findings from the **24 November 2026 Claude reliability audit**.

## Changes implemented

- Generic event-slot routing and deterministic publisher/date/link metadata answers.
- Additional firewall on model-generated general background, including leakage of article figures.
- Reusable Unicode, Indic digit, exact-quote, pseudo-excerpt and numeric utilities.
- Evidence checks shared by chat and Deep Research, with conservative allegation/status labelling.
- Per-item reviewer decisions; a malformed verdict cannot approve its own claim.
- Research-only RSS discovery does not change the live news index.
- Bounded historical candidate query (up to 300), without changing public /api/news limits.
- Ask AI semantic reviewer receives the reader's question.
- Larger bounded reviewer output budgets to reduce truncated JSON.
- News evidence depth distinguishes Google News title repetition from meaningful excerpts.
- English-with-₹ or typographic punctuation language recognition.
- Weather query fixes for day after tomorrow and substring false-positive matches.
- Research UI identity race, region confidence and evidence-status labels.
- No API key, .env, database or local .venv in the release ZIP.

## What this does NOT prove

- Zero hallucinations (not possible to guarantee with LLM reasoning).
- Publisher independence or correctness of an RSS assertion.
- Full-article research; only RSS titles and available excerpts are retrieved.
- Completely cross-language incident matching or multilingual semantic equivalence.
- Live Groq performance, rate-limit behaviour, or public Render infrastructure security.

## Prior to publishing

Run `python -m pytest -q` locally, test the six-step LangGraph execution with a
configured provider, and review at least one real article from each major news
category. Do not upload `.env`, cached databases or secrets to public repositories.

## Verification

The offline suite was executed with a mocked external-provider environment. Final release count must be taken from the current test run. The seven skipped cases require optional graph or provider components not present in this environment. The reported fixes are code-level improvements, not proof of live Groq accuracy.

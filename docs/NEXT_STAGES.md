# Path from local MVP to genuinely production-grade BharatPulse

These are **future production capabilities** beyond the local-first v0.10 MVP; some v0.10 source-origin and lexical-similarity foundations are already implemented.

## Stage 2 — Robust ingestion and licensing
- Add authorised provider integrations and contracts for permissible article metadata/text usage.
- Evaluate X API and Google Trends access/quotas before promising coverage.
- Replace the implemented in-process five-minute RSS scheduler with a durable task queue (Celery/RQ + Redis), per-provider budgets, retries/backoff and idempotent jobs.
- Extend v0.10 basic `feed_origin` to canonical publisher/agency provenance records, link canonicalisation, robots/terms checks, provider health and retry telemetry.

## Stage 3 — Actual ML/LLM intelligence
- Benchmark multilingual topic/region classifiers across Hindi, English and regional languages.
- Evaluate embedding-based semantic event clustering against v0.10 lexical overlap and exact-headline deduplication; label false-positive/negative rates.
- Build retrieval evaluation datasets with citation precision, grounding and abstention metrics.
- Isolate untrusted documents against prompt injection and test adversarial prompts.

## Stage 4 — Agent workflow and investigations
- Extend the v0.10 LangGraph pipeline with contradiction detection, human approval gates, durable checkpoints and deeper retrieval (not yet implemented).
- Track decisions/retries/checkpoints; never infer independent corroboration from syndicated copies.
- Expand the v0.6 structured quote-anchored RSS report into semantic claim-evidence checking with reviewer sign-off, contradiction labels and report export.

## Stage 5 — Cloud and collaboration
- Use Postgres + pgvector, secure auth/RBAC and a permissioned team workspace.
- Add CI/CD deployment, observability, alerting, retention/privacy policies and API rate limits.
- Conduct load tests, security review, reliability drills and content compliance checks before public access.

## Suggested resume phrasing for THIS version

> Built a local-first Indian regional news explorer with FastAPI, SQLite, LangGraph and JavaScript, featuring curated regional RSS metadata, source-origin indicators, lexical headline-overlap analysis and source-anchored Groq research with review and abstentions.

Avoid quantified accuracy, "realtime push", "production-deployed", "independent fact-checking" or "verified fake-news detection" claims without independently measured implementation evidence. LangGraph provides a multi-stage orchestration workflow, not multiple independently validated autonomous agents.

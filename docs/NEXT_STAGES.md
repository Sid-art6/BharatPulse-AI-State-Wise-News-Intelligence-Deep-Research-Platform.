# Path from local MVP to genuinely production-grade BharatPulse

Do not claim any of these stages are currently implemented.

## Stage 2 — Robust ingestion and licensing
- Add authorised provider integrations and contracts for permissible article metadata/text usage.
- Evaluate X API and Google Trends access/quotas before promising coverage.
- Replace the implemented in-process five-minute RSS scheduler with a durable task queue (Celery/RQ + Redis), per-provider budgets, retries/backoff and idempotent jobs.
- Create provenance records, link canonicalisation, robots/terms checks, provider health and retry telemetry.

## Stage 3 — Actual ML/LLM intelligence
- Benchmark multilingual topic/region classifiers across Hindi, English and regional languages.
- Add embedding-based semantic event clustering, title similarity evaluation and duplicate detection.
- Build retrieval evaluation datasets with citation precision, grounding and abstention metrics.
- Isolate untrusted documents against prompt injection and test adversarial prompts.

## Stage 4 — Agent workflow and investigations
- Extend the v0.9 LangGraph pipeline with contradiction detection, human approval gates, durable checkpoints and deeper retrieval (not yet implemented).
- Track decisions/retries/checkpoints; never infer independent corroboration from syndicated copies.
- Expand the v0.6 structured quote-anchored RSS report into semantic claim-evidence checking with reviewer sign-off, contradiction labels and report export.

## Stage 5 — Cloud and collaboration
- Use Postgres + pgvector, secure auth/RBAC and a permissioned team workspace.
- Add CI/CD deployment, observability, alerting, retention/privacy policies and API rate limits.
- Conduct load tests, security review, reliability drills and content compliance checks before public access.

## Suggested resume phrasing for THIS version

> Built a local-first Indian regional news explorer with FastAPI, SQLite and JavaScript, featuring live RSS metadata ingestion, state-aware filtering, headline deduplication, article-specific evidence discovery, and optional Ollama-grounded Q&A.

Avoid quantified accuracy, "real-time", "multi-agent", "production-deployed" or "verified fake-news detection" claims without independently measured implementation evidence.

# BharatPulse AI v1.6 — QA report and deployment gate

**Release stage:** candidate for live verification, not a claim of zero hallucinations or full publisher accessibility. Prepared 25 November 2026.

## Confirmed defects in v1.5

1. Research objectives were chosen with a very narrow keyword set; a multi-part report about an incident could be reduced to a few vague slots.
2. Research-topic coverage was recomputed from a keyword search of the raw RSS text rather than being reconciled with the **approved findings**, leading to an internal contradiction such as "date not established" despite a quoted date.
3. Publisher text already available to Ask AI was sometimes discarded along with an unapproved model draft; the fallback unnecessarily restated the headline.
4. Reported quantity extraction missed a number followed by "injured" and some spelled-out counts, such as "two visitors".

## Changes

- `app/research_insights.py`: generalised research objectives, partial month/day date detection, passages-and-approved-claim coverage reconciliation; more specific missing-evidence labels.
- `app/research_agents_v09.py`: reviewer-approved findings now flow into Report Builder's objective coverage; optional `question_coverage` map.
- `app/research_v2.py`: sends explicit question objectives to synthesis, requests separate supported findings, and permits six verified findings rather than five. Every finding still requires exact quotes, number/modality checks, and the independent reviewer.
- `app/chat_router_v1.py` and `app/main.py`: when no approved draft answers the question, choose a narrow verbatim source quote if there is a relevant passage, clearly distinguish excerpt from a factual conclusion, and preserve the conservative refusal for unsupported causal questions.
- `app/coverage_v10.py`: count expressions such as `11 injured` or `two visitors` without inferring the total or treating different subsets as conflicting.
- `tests/test_reliability_v16.py`: six cross-category tests for the new interactions.
- UI and documentation: version updated to 1.6.

**No story-specific article names or event facts were added to application code.**

## Offline test results in this environment

The complete test suite was verified in three isolated subprocesses due to a combined-run teardown stall in this environment:

| Group | Passed | Skipped |
|---|---:|---:|
| Tests `test_api.py` through `test_evidence_paths.py` | 82 | 1 |
| Tests `test_final_context_qa.py` through `test_public_safety_v10.py` | 70 | 1 |
| Tests `test_regional_coverage_v10.py` through `test_weather_v08.py` | 87 | 5 |
| **Total** | **239** | **7** |

No test failures in these runs. Python 3.13 was used here; the project targets Python 3.11+ and Render pins Python 3.12.7. The seven skipped tests require LangGraph, not installed here. Do not claim those tests passed.

A direct offline replay confirmed a multi-part article question now identifies event date, casualties, location, attribution, official response, and assistance as separate objectives; a reviewer-approved November 24 finding no longer leads the report to say the date is unknown. The direct-quote Ask AI fallback also located a publisher passage about a government response when model claims were not accepted.

## Mandatory local live verification before public AI

1. Create Python 3.11 venv and install `requirements-dev.txt`; run `python -m pytest -q`. Resolve failures; **all seven LangGraph tests should execute** in this environment.
2. Set `.env` privately and verify `active_provider()` reports `groq` without printing credentials.
3. Start Uvicorn with **one worker**, open a live article, verify the reader can access a permitted publisher article (or clearly reports RSS-only).
4. Ask a simple event question, a date question, an official-response question, and an unsupported question. Verify direct answers, exact citations, and no invented actors, causes or figures.
5. Run Deep Research on a multi-part question. Confirm all six nodes' actual trace and no contradictions between the finding/date and evidence-gap sections. Confirm unrelated news does not enter numerical coverage or the event chronology.
6. Run `scripts/verify_local.py` with the server running. Optionally run `python -m scripts.check_publisher_access`; external access depends on publisher permission and network conditions.
7. Confirm `/api/health`, `/api/meta`, frontend assets, region filtering, weather, and source links.
8. Inspect `git status` and `git diff --cached --name-only` to ensure `.env`, database files, caches and tokens are not committed. Only then push to existing GitHub repo and create a Render preview.

## Render deployment

`render.yaml` is configured for a **portfolio preview**: one Python web service, health route `/api/health`, `BHARATPULSE_PUBLIC_MODE=true`, and **public AI disabled** by default (`BHARATPULSE_PUBLIC_AI_ENABLED=false`). This is a safer initial deployment.

To enable public Ask AI and Deep Research, configure `GROQ_API_KEY` as a Render secret and deliberately set `BHARATPULSE_PUBLIC_AI_ENABLED=true`. Review Groq quotas, rate limits, billing alerts and unexpected traffic before enabling. Do not store a key in the repository. This public demo does not provide strong user authentication or multi-instance rate limiting.

**Hosting limitations:** On free services, cold starts and process sleeping can interrupt the five-minute refresh cadence. SQLite under `/tmp/bharatpulse` is ephemeral; articles and chat memory may disappear at deployments or restarts. For durable production, use persistent managed storage and a separately scheduled ingestion worker. The current configuration is **not** an always-on news service.

### Deploy decision

Deploy a public preview after the local FastAPI smoke tests pass. Enable public AI only after article retrieval, grounded chat and six-node LangGraph research are validated with live Groq. A single live success does not certify zero hallucinations; keep monitoring and treat publisher content as attributed reporting, not independent truth.

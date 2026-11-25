# BharatPulse AI v1.3 — Release Verification

## Scope

This is an evidence-grounded RSS news intelligence portfolio application, not an independent newswire verification engine or full-article research crawler. The LangGraph workflow includes six **stages**; only synthesis and quality review require an LLM. The other stages perform bounded, auditable deterministic work.

## Quality changes and their rationale

| Failure observed | Generalised code correction |
|---|---|
| Named-person question answered with invented employer/history | Named-subject and compound-identity questions follow article evidence; general prompt refuses biographies without attributable support |
| Publisher question refused even though publisher is stored | Metadata intent returns fields deterministically without the model |
| Headline repeated for background, effective-date, or duties questions | Evidence-slot relevance gate; explicit missing detail in fallback |
| Second same-story headline was buried when LLM produced one claim | Separate literal source-highlights block plus source comparison |
| Research prompt barely affected discovery | Planner derives bounded generic research slots and optional RSS query; no arbitrary user URLs |
| Report gave no overview or gap mapping | Report Builder produces attributed key takeaway, question-driven coverage list, provenance labels |
| Single source could skip AI | Connected six stages preserved; one source is eligible for bounded synthesis when a model is available |
| Main feed contaminated by research discovery | Discovered RSS metadata stays in per-request graph state |

## Verification commands

From project root, with Python 3.11/3.12 and dependencies installed:

```powershell
python -m pytest -q
python -m compileall -q app scripts
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Use `python scripts/verify_local.py` in another terminal after live RSS data exists. If the national feed is empty, use `--article-id` with a known live local article. Use `POST /api/ai/check` explicitly to confirm the configured provider actually responds.

## Mandatory live review before publishing

Test **at least three unrelated news topics**, each with a headline-only and, where available, a detailed excerpt. Ask identity, metadata, role, reason, numbers, and follow-up questions. Deep Research must visit all six stages, distinguish source observations from reviewed findings, preserve quote/source indices, and identify missing evidence. Check for invented ownership, biography, dates, policies and causes. Check weather with fresh provider data.

When only RSS titles exist, even a successful LLM response cannot recover missing biography, causal explanations or official documents. Do not claim zero hallucinations, independently verified journalism, or complete full-text research. Current public demo configuration deliberately disables shared public AI until quotas and authenticated access are configured.

## GitHub hygiene

The release ZIP omits `.env`, API keys, local databases, virtual environments and runtime caches. Before pushing, confirm `.gitignore` is applied and inspect staged filenames. The ZIP is not a Git repository. Clone the user's existing repository and update the tracked source files rather than using `git init` in a random extracted folder.

## Test scope

The bundled suite uses synthetic RSS and mocked LLMs; a few tests need the separately installed LangGraph dependency. Offline pass counts are *not* provider connectivity or research quality measurements. A local live smoke script validates response structure, not independent factual accuracy.

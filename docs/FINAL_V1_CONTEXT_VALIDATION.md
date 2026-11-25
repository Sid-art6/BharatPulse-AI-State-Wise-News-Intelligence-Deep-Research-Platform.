# BharatPulse AI v1.0 — final context-QA candidate

This is a **release candidate**, not a public production release. The existing GitHub `main` branch is not changed by this package.

## Problems reproduced from the user's audit

- A police complaint is a complaint **filed with** police; it need not concern misconduct **by** police.
- In Indian policing, **FIR** means *First Information Report* (but it can mean *Finite Impulse Response* in an explicitly technical signal-processing context).
- In the selected Tamil Nadu news context, **TVK** means *Tamilaga Vettri Kazhagam*, not a person.
- **BJP** is correctly expanded as *Bharatiya Janata Party*. The answer avoids unverified changing claims about who governs.
- “Why was the Tamil Nadu BJP chief detained?” must not turn “on the way to a ceremony” into a reason for detention.
- “What is BJP doing?” and “What is the police complaint about?” must route as article questions, not generic acronym definitions.
- Publisher RSS metadata is **not** full-text evidence. Related articles cannot establish causation or independent confirmation on their own.

## Tests executed in the package-building environment

- `python -m pytest -q` — **126 passed, 6 skipped**. The six skipped integration tests require `langgraph`, unavailable in this environment.
- `python -m compileall -q app` — passed.
- `node --check app/static/app.js` — passed.
- FastAPI local HTTP smoke test — `/api/health`, `/api/meta`, `/api/news?demo=true`, `/api/weather/cities`, the homepage and security headers returned expected responses; `/.env` returned 404.
- An attempted Chromium browser test was **blocked by the execution environment's browser policy**. Do not describe this as passed end-to-end UI verification.
- No live Groq call was made: no user API key was copied into this environment. The glossary and REST scenarios used isolated test fixtures.

## Windows verification before GitHub release

1. Extract into a **new directory**; do not overwrite the old v0.10 Git working tree.
2. Copy the private `.env` from your last local candidate to this directory, never to GitHub.
3. Run `python -m pytest -q` with your fully installed project virtual environment; the six LangGraph tests must **run and pass** rather than skip.
4. Start the FastAPI server. GET `/api/health`; verify `validation_revision = v1.0-final-context-audit`.
5. On the Tamil Nadu article, ask: `What is a police compliant?`, `What is FIR?`, `Who is TVK?`, `What is BJP?`, and `Why was the Tamil Nadu BJP chief detained?`.
6. Verify search with multiple terms, category changes, reset controls, real RSS sources, one actual LangGraph research report, and city/weather changes.
7. If an answer fails, capture the **full question, model response, selected article headline, and `/api/health` revision**. Do not paste API keys.
8. Only after the local acceptance tests, publish the final candidate to GitHub and require green CI before deploying to Render.

## Public demo limitations

- Render free service sleeps when idle; `/tmp` SQLite is ephemeral. RSS polling stops during sleep.
- Public AI stays off by default. Enabling it exposes a limited budget managed by process-local quotas, **not** a guaranteed cloud spend limit.
- Live news correctness, source independence, article facts and weather forecast accuracy cannot be certified by a synthetic test suite.
- The README's screenshots are genuine previously captured frontend **fixture views** and are labelled as such, not captures of a deployed service or live article investigation.

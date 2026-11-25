# Release QA and evidence boundary

This is an **RSS-headline-and-excerpt research assistant**, not a full-text search engine or an independent fact checker. The news publishing source might be wrong or incomplete. Automatic semantic reviewers are AI judgments and may produce false positives or false negatives.

## Behavioural policy

* Keep questions about the selected article in the quoted-evidence path, including names and named operations. Standalone dictionary definitions are explicitly separate from article claims.
* Never use a loosely related article as evidence for what happened in the chosen incident. Context headlines are indexed and labelled, but only possible-same-story articles can contribute to additional claims.
* Evidence-based claims must cite a literal title or excerpt quotation with a valid source index; numeric and semantic validations still apply.
* Later-event, conviction, causation and reported-risk questions must not be answered from assumptions or timestamps.
* Planner, Discovery, Retriever, Synthesis, Quality Reviewer and Report Builder always appear in the LangGraph execution trace. A skipped node is NOT a successful LLM execution.
* Public-mode middleware offers baseline request-size, origin, rate, and security-header checks; not enterprise-grade identity, moderation, or multi-worker distributed quotas.

## Manual acceptance tests (live provider required)

1. Select 3 unrelated live reports (legal, wildlife, technology). For each, ask a direct headline fact, a question whose answer is absent, an unrelated definition, and a publisher-identification question.
2. Ask a follow-up such as 'What happened next?' and make sure the output does not infer chronology from publication times.
3. Run Deep Research with one indexed source and with multiple sources; verify all six statuses are explicit and that topic-context links are not used as proof of one incident.
4. Deliberately disconnect Groq/Ollama; the fallback should keep the source index and show skipped LLM stages.
5. Check the source quotes, numeric units, weather attribution, regional language rendering, HTTP security headers and UI on desktop/mobile.

**Do not upload:** `.env`, SQLite databases, `__pycache__`, `.venv`, local logs or keys. Set secrets only in local `.env` or the hosting service secret manager. Read deployment guidance before enabling public AI calls.

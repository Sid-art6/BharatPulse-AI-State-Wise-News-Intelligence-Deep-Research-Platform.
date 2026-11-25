# BharatPulse AI v1.0 — Second-pass accuracy fixes

This candidate follows the user's manual acceptance testing. It is **not yet a deployed public release** and has not been pushed to the project's GitHub `main` branch.

## Changes made

- **FIR and TVK contextual definitions:** In Indian criminal-justice reporting, FIR is **First Information Report** rather than a programming queue; in a selected Tamil Nadu TVK headline, TVK is **Tamilaga Vettri Kazhagam**. Both are labelled reference definitions, separate from article allegations, and avoid unnecessary calls to Groq.
- **Police complaint definition:** Recognises `police compliant` as a likely typo for `police complaint` in a definition request. A curated, legally cautious general definition distinguishes a complaint filed **with** the police from a complaint **against** an officer. This particular glossary answer is explicitly labelled as a definition, not a Groq-generated fact.
- **Relevant news context:** The general definition can include the *exact selected headline*, clearly separated from the concept explanation, only when the headline is relevant to that concept. The headline cannot establish the allegations or cause.
- **Mixed questions:** Corrected the question splitter so `What is Bali Jatra, and what does the article say President Murmu will do?` retains its article-specific half.
- **Source overviews:** Queries such as `What do the available news sources say about the Collector and the TVK MLA?` now return a short, indexed comparison of exact RSS headlines/excerpts, not an LLM-invented narrative.
- **Source deduplication:** Removes duplicate secondary headlines and prefers a direct publisher URL over a Google News RSS redirect when both secondary records have the same headline. The UI labels remaining Google News links correctly.
- **Stricter claim checks:** The local validation layer rejects claims that introduce role titles (for example, `Chief Minister`) or causal phrases absent from the exact supporting RSS quote. Independent semantic review is still required for other generated claims and is not proof of factual truth.
- **Useful abstention:** For an unanswered `why` question, the assistant gives the selected RSS headline, possibly one relevant related headline, and explicitly states that these items do not establish the reason. `Insufficient evidence` and `AI provider unavailable` now have different UI labels.
- **Regression tests:** Added `tests/test_chat_accuracy_pass2.py` with six focused tests. Existing API and research tests remain intact.

## Invariant trust boundary

BharatPulse indexes RSS headlines and excerpts, not publisher-licensed full text. A headline reporting that messages were sent to a Collector **does not, alone, prove why** a separate police complaint was filed. The application must not infer misconduct, event chronology or independent corroboration from a related headline. Source attribution indicates *what the indexed feed says*, not that a reported fact is proven.

## Validation required before the final GitHub release

1. Run `python -m pytest -q` on Windows with the full `requirements-dev.txt` environment, including LangGraph.
2. Verify the exact audit prompts: `What is a police compliant?`, `Why did the Collector file the police complaint?`, `What do the available news sources say about the Collector and TVK MLA?`, and a mixed Bali Jatra question.
3. Test the approved News, Research and Weather layouts in the browser. Check Google News versus publisher link labels.
4. Reconfirm public-mode budget controls and API secrets, then perform Render staging/smoke testing.
5. Replace README fixture screenshots with live captures only after verifying a live deployment. Until then, images remain honestly marked as offline interface fixtures.

The separate Deep Research capability remains an **RSS-limited research brief**, not independent full-article research. Publisher feed URLs may be unavailable, and a public Render free service may sleep or lose temporary SQLite data. Public AI access is disabled by default until controlled usage and budget settings are explicitly approved.


## Verification from the build environment

- Python 3.13, offline fixtures: **105 passed, 6 skipped** (`python -m pytest -vv --disable-warnings`). The skipped tests require optional runtime dependencies, including LangGraph, which are absent here.
- Frontend JavaScript syntax: `node --check app/static/app.js` passed.
- Tested the exact user questions `What is a police compliant`, `What is an FIR?`, `What is TVK?`, `Why did the Collector file the police complaint?`, and `What do the available news sources say?`, using offline controlled sources and monkeypatched provider calls.
- No live Groq invocation, real-time article-accuracy guarantee, or public Render verification was performed in this build environment. The user's Windows setup and public deployment require their own smoke tests.

## Validation before promoting to main

1. Copy your private `.env` locally only; never add it to Git.
2. Run `python -m pytest -q` with all dependencies installed, including LangGraph.
3. Verify the selected TVK headline and test `What is a police compliant`, `What is an FIR?`, `What is TVK?`, `Why did the Collector file a police complaint?`, and `What do the available news sources say?`.
4. Verify accurate status labels for missing evidence and real provider failures.
5. Check news filters, all UI screens, `/api/health`, and the Render public-mode restrictions.


## Third-pass targeted fixes (context and causal questions)

- Narrow acronym intent detection treats **"who is TVK"** as a glossary question
  instead of asking a news-evidence model who the acronym refers to.
- "Why" questions that have no explicit reason in the selected article's RSS
  headline/excerpt return a clearly labelled evidence limitation instead of
  restating *where the person was travelling* as the cause of an event.
- If a causal question reaches the reviewed AI path, any answer with no
  explicitly cited causal evidence is discarded.
- `/api/health` adds a non-secret `chat_revision` field so Windows users can
  confirm which candidate is actually serving port 8000. Earlier observed
  inaccurate FIR/TVK definitions were inconsistent with the previous
  candidate's glossary rules, suggesting a different folder or older server
  was running. Always stop the old server before switching candidates.

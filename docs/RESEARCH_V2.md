# BharatPulse AI — Deep Research v2 (what it actually does)

This is an **evidence-grounded RSS research brief**, not full-text investigative reporting, independent fact-checking, or a deployed multi-agent system. The source of truth is the publisher headline and description as returned by an RSS provider.

## Six beginner-friendly stages

1. **Select a story.** The user clicks **Research** on a live article card. The browser posts its article ID and the selected answer language to `/api/research/{article_id}`.
2. **Discover related reporting.** FastAPI searches Google News RSS by the headline (fixed provider origin) and reads the already-indexed SQLite stories. The system does not fetch or execute arbitrary article URLs.
3. **Compare available snippets.** Overlapping headlines are selected using deterministic relevance scoring and deduplicated by headline fingerprint. Publisher labels are recorded, **but separate outlets do not automatically establish independent corroboration**.
4. **Request an evidence map.** Groq (or Ollama) is asked for JSON findings. Each finding must cite an indexed source **and quote an exact continuous passage** from that source's headline or RSS excerpt. It also emits an English paraphrase for basic multilingual alignment checks.
5. **Validate before display.** `app/research_v2.py` checks source indexes, exact substring quotations, overlap with the quoted text, and whether numeric claims introduce figures missing from their quoted evidence. Findings failing these automated checks are excluded. **These checks do not prove semantic entailment or factual truth.** If no finding passes, the app shows an insufficient-evidence message and the source index.
6. **Render a research brief.** The browser renders headings, findings, clickable numbered source references, exact quotes, an RSS **publication** timeline, unknowns, questions for future reporting, and limitations. It escapes source/model text to prevent HTML injection. Model-generated Markdown/HTML is never rendered directly.

## Two kinds of dates

- **Publication date:** From the RSS `<pubDate>` field when provided and parseable. The timeline labels these as *publication timestamps* only.
- **Event date:** Not inferred from a publication timestamp. If the feed does not provide a date, the app says **Not supplied by feed** rather than assigning today's date.

Existing news records from earlier builds may contain historical fallback timestamps assigned when original RSS dates were missing. Re-fetching may not overwrite them because the store deduplicates articles. Treat timestamps inherited from v0.5 as unverified unless checked against the publisher.

## Security and honest boundaries

- No model-supplied URL fetching or browser-supplied URL proxying; source URLs remain for users to open manually.
- No unlimited model retries (protects free Groq quotas).
- Only retrieved RSS headlines and excerpts are used for research synthesis. **The model does not independently browse full articles.**
- Quotations are checked for existence, **not** for full semantic support; translated claims are particularly difficult to verify mechanically.
- The response can distinguish Groq/Ollama, insufficient evidence, model unavailable, and demo mode.
- Multiple sources may be syndicated duplicates, and the application does not rate publishers' trustworthiness or determine whether their reporting is true.

## Key files

| File | Purpose |
|---|---|
| `app/main.py` | API routes; the discover → retrieve → evidence check → report workflow |
| `app/research_v2.py` | Model JSON request, exact-quote validation and publication-only timeline |
| `app/ai.py` | Groq/Ollama adapter and prompts; `.env` controls which provider |
| `app/core.py` | RSS parsing, local news database, source retrieval and deduplication |
| `app/static/app.js` | Source-safe structured report renderer in the article drawer |
| `tests/test_research_v2.py` | Bad citations, fabricated figures, multilingual quotes, dates and API fallback tests |

## Test examples

**Supported test:** A source headline says `Karnataka panel reviews fuel testing`. An AI finding using that exact quote and a limited claim about the Karnataka review can pass the *anchor screening*, but still requires the human to check the original article.

**Unsupported test:** The model invents `₹900 crore loss` but no cited excerpt contains `900`. The backend rejects the finding. If all claims are rejected, the report shows no supported findings.

## Next milestone (not implemented in v0.6)

Authorized full-text retrieval with publisher-specific licences, semantic claim verification, contradiction detection, optional LangGraph orchestration with checkpoints, editorial approval, and research PDF export. These require substantially more engineering and genuine content access agreements.

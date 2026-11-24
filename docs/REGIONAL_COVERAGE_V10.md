# BharatPulse AI v0.10 — Regional Source Coverage and Research Evidence

## Scope

v0.10 extends the **existing** Python/FastAPI/SQLite/RSS/real-LangGraph system; no Node.js, Docker or new API key is required. The user's Groq key remains in their untracked local `.env`. Optional LangSmith stays disabled.

### 1. New direct publisher RSS section feeds

- A small, fixed registry of **29** curated publisher-hosted RSS sections (25 The Indian Express, 4 The Hindu) is in `app/regional_sources_v10.py`. Registry sources: [The Indian Express publisher's own RSS directory](https://indianexpress.com/rss/) and a [Feeder-maintained directory of The Hindu RSS endpoints](https://feeder.co/knowledge-base/rss-content/the-hindu-rss-feeds/) (reviewed 23 Nov 2026). The Hindu endpoints are candidate publisher-hosted feeds, not confirmed by live HTTP checks in this build.
- Up to two fixed publisher RSS requests are made for watched regions with registry entries, alongside the current Google News English/regional-language requests (and BBC for All India).
- Google News is an **aggregator**; direct publisher RSS is separately labelled. These are **not 29 distinct publishers** or proof that all locations are covered, and direct feed availability requires live testing.
- A failing direct feed does not cancel successful Google News results, and vice versa. All sources failing still reports provider failure.
- URLs are fixed by the server. The user cannot supply an arbitrary fetch URL. The existing 5-minute scheduler is retained (not a push feed).
- When the text itself names a region, `region_confidence=explicit`. An item without an explicit location may inherit a **curated publisher section**, labelled `publisher_section`, rather than being presented as article-confirmed geography.

### 2. Source origin and backward-compatible storage

`articles.feed_origin` records one of `direct_publisher_rss`, `google_news_rss`, `bbc_publisher_rss`, `demo_fixture`, or `unclassified_legacy`. Existing databases are migrated in place by `core.init_db()`.

**Deduplication limitation:** The existing unique fingerprint suppresses identical titles, even if they appear in different feeds. The stored feed origin reflects the indexed article entry, not a complete historical list of every feed where the headline appeared. A future per-feed observation table is needed to make exact cross-feed provenance claims.

### 3. Research coverage signals

The v0.10 LangGraph research report includes a deterministic `coverage` field even when it abstains:

- number of indexed RSS entries and **publisher labels** (not independently verified outlets);
- possible repeated wording groups when informative title-token Jaccard overlap is high (0.70 or above);
- source-indexed literal numeric spans in RSS text: percentages, money amounts, crore/lakh/million/billion quantities.

For example, the phrase `162.5% duty` appearing in an RSS title is shown as a **reported numerical detail**, never as a verified tax rate or primary legal document. Different amounts may describe different goods/dates and are **not automatically treated as contradictions**. Model-generated findings still need exact quotations, number checks and a separate semantic-review call before approval.

### 4. Retrieval diversity

The related-item selector applies a conservative lexical relevance filter, then modestly prefers distinct publisher labels while deprioritising near-identical headline wording. These are retrieval ranking heuristics, not evidence of independent corroboration. No semantic embeddings, paywalled article crawling, unbounded web search or new user-triggered URL fetchers have been introduced.

### 5. Rights, reliability and ethics

- Feed metadata access does **not** grant permission to scrape, redistribute or train on full publisher articles. Show attribution and click through to the originating link; review the publisher's current terms, robots policy, licensing and commercial permissions before launch.
- The original RSS feed might contain excerpts with article content. Limit stored/reproduced text to the minimum necessary and do not present it as a licence for reuse.
- Provider and Google News RSS availability, localisation and rate limits are not guaranteed. Inspect each live source's response on Windows after installing v0.10.
- The feed section is a *routing hint*, not a guaranteed geographic event label. No automated fake-news detection or official fact verification exists.
- No LangSmith key is required. If disabled with `LANGSMITH_TRACING=false`, v0.10 does not rely on external tracing services.

### 6. Manual smoke tests

1. Select **Karnataka** → Fetch live news; ensure the refresh works if at least one provider is reachable and direct RSS entries, when returned, are labelled **Direct publisher RSS**.
2. Select **All India** and research a news story with several related sources. Check the **Coverage and numerical claims** section and click source indices to inspect evidence.
3. Confirm that duplicate/overlap labels never claim independent verification and that numbers are marked as *reported* rather than independently established.
4. Switch to **Weather Intelligence**, choose a city and verify that the map follows the selection, preserving v0.8 behaviour.
5. Check `/api/health` → `0.10.0`, `/api/meta` → `direct_publisher_feed_sections: 29`, and `/api/news` → `feed_origin` field.

**Test boundary:** Offline tests mock RSS and Groq. Live publisher RSS and real LangGraph integration must be checked on Windows before GitHub release.

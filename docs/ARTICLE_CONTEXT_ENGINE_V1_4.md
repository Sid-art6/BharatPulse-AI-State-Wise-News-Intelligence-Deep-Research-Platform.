# Article Context Engine — v1.4

## Product behaviour

- Opening Ask AI displays a greeting and schedules `POST /api/article-context/{article_id}/prepare`.
- The browser polls `GET /api/article-context/{article_id}` to show only `loading`, `ready` or `limited` and a source-quality status. It does not show an unsolicited news summary or the cached article body.
- A chat question calls the normal `/api/chat` endpoint. A request arriving mid-prefetch awaits the existing task for at most 22 seconds, then falls back to saved RSS evidence if unresolved.
- Context is stored in SQLite `article_context` under the indexed article ID. Retrieved body text and verified source URL are reused for follow-ups; user-facing citations remain tied to the source.
- Switching articles isolates contexts by article ID; clearing the chat clears session conversation history but deliberately leaves the shared factual source cache.

## Retrieval and provenance

1. Fetch only indexed HTTPS URLs from configured/curated publisher hostnames.
2. Reject IP literals, private/non-global DNS, custom ports, user-info and unapproved redirects; never fetch browser-supplied URLs.
3. Check robots.txt and honour access restrictions. There are no browser automation, subscription, CAPTCHA or anti-bot bypasses.
4. Attempt a legacy Google News link decode (when an original public URL is embedded), then normal HTTPS redirects or exposed page links. Opaque modern Google News links often cannot be resolved; report `limited` instead.
5. Prefer `NewsArticle.articleBody` JSON-LD then `<article>`/`main` content; strip navigation and boilerplate. Require a minimum meaningful text length and approximate story-title match.
6. Keep the extracted material as untrusted evidence. Select literal paragraphs by question terms; do not use AI to manufacture new source passages.
7. Claim generation and reviews remain bounded and require exact supporting quotes and numerical consistency. General definitions are labelled separately; document-specific biographies and allegations must use source evidence.

## API response example (no body)

```json
{"article_id":"<id>","status":"ready","evidence_origin":"publisher_article","word_count":520,"retrieved_at":"<UTC timestamp>"}
```

## Safety and limits

- `12` hour source cache TTL, `35` minute retry cooldown on blocked sources.
- `3` concurrent retrieval jobs, `4` redirects, `1.8MB` max fetched HTML, `32k` stored source characters and `6.5k` selected passage characters per question.
- Optional administrator-only env `BHARATPULSE_ARTICLE_DOMAINS` permits additional source hosts. Never set this to arbitrary/unsafe domains.
- In multi-worker deployment, per-process task maps and semaphores are not distributed. The durable SQLite cache prevents some duplicate work, but for scaling use a real job queue and shared quotas.
- Robots checks and allowlists are defence-in-depth, not a comprehensive SSRF security certification. Network egress restrictions are recommended for public production deployment.
- Not all publicly accessible pages may be stored or scraped under a publisher's terms. Honour applicable licensing and terms; keep only legally permitted content.

## Testing

`tests/test_article_context_v14.py` includes local extraction, long-article passage selection, URL denial, cache reuse, story-identity mismatch rejection, and a prefetch-to-chat API test. The full test suite is offline; no tests require live publisher or Groq connections.

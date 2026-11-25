# Public demo security controls (v1.0)

The v1.0 changes are designed for a **single-process, low-traffic portfolio demo**. They reduce common and cost-related risks but **do not constitute a full penetration test or certification**.

## Protections implemented

| Layer | Behaviour | Limitations |
|---|---|---|
| FastAPI request middleware | Checks `Content-Length` where provided and streams API write bodies with a 16 KiB upper bound; returns 413 on excess | Edge/infrastructure request limits are still needed against large or slow network attacks |
| Cross-origin writes | Blocks unexpected browser `Origin` headers for public-mode API changes | Non-browser clients do not necessarily send Origin; this is not authentication |
| Expensive Groq endpoints | Disabled in public mode by default; controlled by `BHARATPULSE_PUBLIC_AI_ENABLED` | Direct calls from a malicious client may still use the quota once enabled |
| Rate limiting | 6 AI requests/client/hour **and** 30 AI requests total per hour per worker; 24 RSS writes/client and 120 globally; read quotas also apply | In-memory state resets after restart and can share a reverse-proxy IP; provider billing limits remain necessary |
| Host validation | Restricts hosts when `BHARATPULSE_ALLOWED_HOSTS` is set | Deployment domains must be configured intentionally |
| Browser headers | CSP, no framing, MIME-nonsniff, privacy restrictions, referrer policy | Review third-party CDN usage and upgrade dependencies periodically |
| Data | Headlines/excerpts and source origins are stored in SQLite | SQLite in `/tmp` on free hosting is not persistent; do not store confidential content |
| Source provenance | Publisher and RSS origin metadata shown with source citations | Neither an LLM nor publisher name verifies that a claimed event occurred |

## Deployment defaults

`render.yaml` uses public mode and keeps **public AI disabled**. The Groq key is not present in the Blueprint. If public AI is enabled, set the key privately in Render, enable account-level provider cost/rate alerts, and test with a separate limited-use key. This one-worker limiter reduces accidental cost but cannot ensure a strict monthly spending ceiling; it resets when the service restarts. LangSmith tracing remains off by default per project preference.

## Before higher-stakes production use

Add a persistent database, edge/WAF-level request filtering, authenticated accounts with quotas, distributed rate limiting, external dependency scanning, secret-rotation policy, security event monitoring, CI vulnerability checks, and a professional security assessment. RSS providers' rights/terms and rate limits also require evaluation before commercial use.

## Local audit correction notes

- News search supports multiple literal terms across title, excerpt, publisher, region and topic. The browser ignores stale responses when filters change rapidly.
- General AI answers are labelled as general model knowledge and are not falsely cited to RSS. Article answers continue to require RSS evidence; mixed questions separate background and reporting.
- A research report now includes a source-by-source RSS evidence inventory even when only one reviewed factual finding is available. This does **not** make it equivalent to licensed full-article research.
- The UI displays AI provider setup/readiness; connection checks cost a bounded model call and are disabled along with public AI by default.

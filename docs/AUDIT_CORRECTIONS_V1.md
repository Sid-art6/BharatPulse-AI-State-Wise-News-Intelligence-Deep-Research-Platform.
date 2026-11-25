# BharatPulse AI v1.0 — Consolidated audit corrections

This is a **release candidate**, not a published or verified public deployment. The existing GitHub `main` release remains unchanged until local acceptance checks pass.

## Audit finding → implemented correction

| Audit item | Finding | v1.0 candidate change | Remaining validation |
|---|---|---|---|
| N1 | Regional feeds passed | Existing ingestion retained | Confirm live provider behaviour on Windows/Render |
| N2 | Search/filter multiple unspecified failures | Visible search box; multi-word matching against title/excerpt/publisher/topic/region; explicit reset; stale browser response suppression; clear empty state | Reproduce your previous failing searches and check browser behaviour |
| A1 | “What is a passport?” answered from unrelated article | General-knowledge route with no article input or RSS citations | Test real Groq response |
| A2 | Summary repeated headline | Explicit RSS-level synopsis; explains full text is unavailable | Inspect whether extra source excerpts provide detail |
| A3 | Evidence response did not address evidence request | Direct publisher-headline and excerpt evidence route with exact source index and attribution; says this is not independent verification | Compare citation link to actual publisher |
| A4 | Mixed Bali Jatra question abstained entirely | Separate general background + strict article reporting sections; only reviewed article claims get RSS citations | Test real Groq background answer and source handling |
| A5 | Repeated disclaimer / insufficient-evidence behaviour | Correct display labels and a single caveat per article-chat session; conservative fallback retained | Test repeat submissions and chat reset |
| R1 | LangGraph completed with only 1 reviewed finding | Source-by-source RSS headline/excerpt inventory with detail-level labels, richer evidence constraints, and preserved quality gates | Full-article access is not included; deep context cannot be promised from headline-only feeds |
| W1 | Passed | Weather data and interactive map preserved | Confirm after deployment |
| U1 | Passed | Approved photo-matched visual language preserved; visible search and local AI status control added | Confirm responsive layout on Windows |
| S1 | Passed | Error/recovery logic preserved | Manual retry/refresh check |
| S2 | Partial | Body-size cap on streamed API writes, same-origin browser checks, CSP and other headers, per-client and global quotas, public AI off by default, `.env` protection | Provider-side budget alerts, dependency/security scans, distributed rate limiting not included |
| D1 | Health and deployment configuration passed locally | Render Blueprint retained; single worker; ephemeral storage and sleeping service limitations documented | Real Render deployment, HTTPS, live API and latency checks remain pending |

## Security boundaries

- Model API keys belong in `.env` locally or private Render environment variables; **never** in ZIP, Git or a public README.
- AI requests are disabled by default on a Render public demo; enabling them requires setting `BHARATPULSE_PUBLIC_AI_ENABLED=true` and configuring private Groq credentials and account-side spending safeguards.
- The in-memory limiter runs on one process and resets on restart. It is not a cryptographic abuse control, authentication, an edge WAF or a binding monthly cost ceiling.
- RSS records are publisher metadata, not licensed full articles, independently verified reporting or forecasts.
- Render free's temporary `/tmp` SQLite database may reset between deployments/restarts; visitor-triggered fetches repopulate available news.

## Release gate

1. Run `python -m pytest -q` on the Windows setup with LangGraph installed; **all tests must pass**, including the integration tests skipped in some minimal environments.
2. Run real Groq prompts for general, evidence, mixed and article-specific questions.
3. Check search, reset and rapid filter switching in the browser; verify the three approved screens and weather map.
4. Review secrets, quotas and provider spending alerts, then publish a single final `main` commit and require green GitHub Actions.
5. Deploy to Render, inspect `/api/health`, enable paid AI only after safeguards, smoke-test the public URL, and add **real hosted** screenshots and demo link to the README if applicable.

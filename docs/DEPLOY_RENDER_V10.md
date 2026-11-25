# BharatPulse AI v1.0 — Render public-demo deployment

## Prerequisites

- A GitHub repository containing the **tested v1.0** commit on `main`.
- A Render account connected to GitHub, with permission to read the repository.
- **No public GROQ_API_KEY** in source control or documentation.

## Set up the free service

1. In the Render dashboard, create a new **Blueprint** from the connected GitHub repository. Render reads the root [`render.yaml`](../render.yaml).
2. Confirm it creates one Python web service with a free instance, build command `python -m pip install -r requirements.txt`, and start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`.
3. Wait for a successful build. Use the supplied `https://...onrender.com` hostname; a paid `.com` domain is not required.
4. Visit `<your-url>/api/health`: expect `{"status":"ok","service":"BharatPulse AI","version":"1.0.0"}`.
5. Open the app, select **Live RSS**, and wait for the first available feed check. Provider timeouts or an empty regional feed are not equivalent to an application crash.
6. Validate the city selector, seven-day forecast, mapped city markers, and that the source links open publisher pages.
7. Add the **actual verified URL** to the README only after those smoke tests. Capture fresh live screenshots with clearly disclosed demo/live status.

## Public AI configuration — optional and guarded

By default, `BHARATPULSE_PUBLIC_AI_ENABLED=false`. Users can browse news and forecasts without a public Groq expense. If you deliberately want the public demo to run research and AI chat:

1. In **Render → Service → Environment**, add `GROQ_API_KEY` as a **secret** (never to Git).
2. Keep `LLM_PROVIDER=groq`, `ENABLE_LLM_FILTER=false`, and `LANGSMITH_TRACING=false` for this deployment.
3. Set `BHARATPULSE_PUBLIC_AI_ENABLED=true` and redeploy. This permits at most **6 AI POST requests per IP per hour per process**; external providers still enforce their own quotas.
4. Monitor usage and set provider-level budget alerts. For meaningful public traffic, add stronger authentication and abuse protection before leaving AI switched on.
5. Turn the flag back to `false` if requests or expenses are unexpected.

## Free hosting trade-offs

- Free web services may sleep after inactivity and require a cold start; do not claim 24/7 updates.
- SQLite is stored under `BHARATPULSE_DATA_DIR=/tmp/bharatpulse`. Its contents are ephemeral across instance replacement and deployments. Cached headlines can be repopulated from RSS.
- Background polling runs **only while the web process is awake**; no external scheduler is included.
- Keep the service at one worker. The limiter and cache are in-process; a persistent database and distributed rate-limit store are needed for multi-instance production.
- Only point city temperatures are mapped. The app has no weather radar or nationwide continuous temperature layer.

## Smoke test and rollback

- Confirm the GitHub Actions test workflow passed for the v1.0 commit.
- Confirm `/api/health`, `/api/meta`, live RSS, and a city forecast from the public URL.
- Check that an unauthenticated `POST /api/ai/check` returns **503** when public AI is disabled.
- If deployment breaks, revert to the last green commit through GitHub and redeploy; never copy `.env` into Git.

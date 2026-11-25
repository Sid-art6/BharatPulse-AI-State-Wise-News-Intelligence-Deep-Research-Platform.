# BharatPulse AI v1.6 — Deploy portfolio preview to Render

This deployment intentionally leaves public Ask AI and Deep Research **disabled** until their live quality has been validated. It publishes the live-news dashboard, regional browser, and weather endpoints.

## 1. Publish the source to your existing GitHub repository

In PowerShell, inside `BharatPulse-AI-v1.6` (the extracted project root):

```powershell
# Confirm Git is installed and accessible
git --version

# Preview exactly which files would be changed, without pushing
.\DEPLOY_GITHUB.ps1 -StageOnly
```

If you are ready to publish, remove the **temporary clone** created in the sibling folder `bharatpulse-github-publish` (do not remove your project folder). Then run:

```powershell
.\DEPLOY_GITHUB.ps1
```

Type `PUBLISH` when prompted. The script clones your **existing** repository, replaces old tracked project files with v1.6, checks that no `.env` or database is staged, commits, and pushes to `main` without a force push. Git/GitHub authentication must already be configured in Windows. Do not share a token in ChatGPT.

Existing repo URL (note the trailing period in the repository name):

`https://github.com/Sid-art6/BharatPulse-AI-State-Wise-News-Intelligence-Deep-Research-Platform.`

If you prefer using GitHub Desktop, upload the contents of `BharatPulse-AI-v1.6` to the **root** of that same existing repository; do not upload the outer ZIP directory. Exclude `.env`, `.venv`, `data/` and database files.

## 2. Create the Render service

1. Sign in at https://dashboard.render.com/ and connect your GitHub account if requested.
2. Select **New > Blueprint**.
3. Select the existing BharatPulse AI repository; it must now contain `render.yaml` at the repository root.
4. Review the single service configured as `bharatpulse-ai`, plan `free`, runtime `python`, and health endpoint `/api/health`.
5. Apply the Blueprint / deploy the service. Render assigns the actual public `*.onrender.com` URL; don't assume its hostname beforehand.
6. Open the deployed hostname, then `/api/health` and `/api/meta` for basic verification.

Render config already supplies the start command:

`uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`

No `.env` file should be uploaded to Render. Do **not** paste the Groq API key into the repository or a public page. This public preview intentionally has:

```
BHARATPULSE_PUBLIC_MODE=true
BHARATPULSE_PUBLIC_AI_ENABLED=false
ENABLE_LLM_FILTER=false
ENABLE_OLLAMA=false
BHARATPULSE_DATA_DIR=/tmp/bharatpulse
```

## 3. Verify after deployment

- `/api/health` should return status `ok` and version `1.6.0`.
- `/api/meta` should report `public_demo: true` and `public_ai_enabled: false`.
- Opening the homepage should load the News dashboard and static assets.
- Select All India or a state; the first RSS refresh can be slow.
- News and weather endpoints must work. Public Ask AI requests will deliberately return 503 until enabled.

Render free web services spin down after idle periods, and files in `/tmp` are not persistent. News/cache history will be lost on restarts. A continuously refreshed production service needs persistent storage and an always-on ingestion process.

**Do not turn on public AI** until real article-backed Ask AI, the six LangGraph research stages, and quota limits have been tested. When ready, set `GROQ_API_KEY` only as a Render secret and enable public AI deliberately after reviewing rate limits.

## Blockers and what they mean

- `git: command not found`: install Git for Windows.
- `Authentication failed`: sign in with your Git credential manager or GitHub CLI; never paste tokens here.
- `GitHub repository not found`: check repository access and the trailing dot in its name.
- Render says no Blueprint: confirm `render.yaml` is at GitHub repository root on `main`.
- Health check fails: inspect Render build/start logs and validate `PYTHON_VERSION`, `requirements.txt`, `uvicorn` start command and assigned `$PORT`.
- Public AI returns 503: **expected** under the initial security configuration.

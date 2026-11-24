# Windows Upgrade: BharatPulse AI v0.9 → v0.10

The existing **GitHub-connected** project is:

`C:\Users\Administrator\Downloads\a\bharatpulse-AI`

The older directory `C:\Users\Administrator\Downloads\BharatPulse-AI-v0.7\bharatpulse-ai` is **not** your Git repository. Continue in the `Downloads\a\bharatpulse-AI` folder.

## 1. Stop server and check git

Use `Ctrl+C` on the Uvicorn terminal, then:

```powershell
cd "C:\Users\Administrator\Downloads\a\bharatpulse-AI"
git status --short
```

If the working tree isn't clean, back up or commit your own changes first.

## 2. Apply the update ZIP

Download `BharatPulse-AI-v0.10-Update.zip` into Downloads:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\BharatPulse-AI-v0.10-Update.zip" -DestinationPath . -Force
```

The update archive does not contain `.env`, `.venv`, `.git`, or your local SQLite `data/` directory. Do **not** replace or delete these. The SQLite migration adds `feed_origin` automatically while preserving existing data.

## 3. Reinstall requirements and test

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -c "from langgraph.graph import StateGraph; print('LangGraph available')"
.\.venv\Scripts\python.exe -m pytest -q
```

Tests must have **zero failures** and should have **no LangGraph-related skips** when the real package is installed. Offline build tests had 6 LangGraph skips because package download was blocked; your machine previously ran the real LangGraph workflow in v0.9.

## 4. Launch v0.10

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` and test:

- `/api/health` returns `0.10.0`.
- Choose **Karnataka**, then **Fetch live news**: direct publisher RSS will be attempted as a complement to Google News (provider may be unavailable).
- Choose a reportable news item and **Research**: the **Coverage and numerical claims** section shows source labels, possible near-duplicate titles and source-linked amounts from RSS snippets, which are not independently verified.
- Choose a different city in **Weather Intelligence**; map should follow automatically.

**LangSmith:** not needed. Keep `LANGSMITH_TRACING=false` in your local `.env`; Groq stays enabled as before. Do not paste API keys into chat or GitHub.

## 5. Only after smoke testing: push to GitHub

```powershell
git status --short
git check-ignore -v .env
git ls-files .env
git add .
git diff --cached --check
git diff --cached --stat
git commit -m "feat: add v0.10 regional RSS coverage and evidence quality"
git push origin main
git status
```

`git ls-files .env` must return nothing. `LF will be replaced by CRLF` is a non-blocking Windows line-ending warning. The change is staged *only after* tests and review; this package does not automatically push to GitHub.

# Upgrade an existing BharatPulse AI GitHub checkout to v0.8 (Windows)

Use the **v0.8 Update ZIP** and your existing Git-connected repository. This keeps the Git history, Groq `.env`, `.venv` and local SQLite news data intact. **You do not need Node.js, Docker or WSL.**

## 1. Stop v0.7 and check your repo

In VS Code, press `Ctrl+C` in the FastAPI terminal. Then open a PowerShell terminal and run:

```powershell
cd "C:\Users\Administrator\Downloads\a\bharatpulse-AI"
git status --short
```

If you see unexpected existing changes, back them up or commit them first. Proceed only when the repository is clean.

## 2. Apply the small v0.8 update

Download `BharatPulse-AI-v0.8-Update.zip` into your Downloads directory. While **still in the Git-connected project root** run:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\BharatPulse-AI-v0.8-Update.zip" -DestinationPath . -Force
```

The update ZIP contains only application code, tests, README and documentation. It does **not** contain `.env`, `.git`, `.venv` or `data`. Your existing Groq API key and indexed news remain local.

## 3. Test

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

This release's offline suite passed **55 tests** in the authoring environment. Real weather API, map tile and Groq connectivity must be checked on your Windows laptop.

## 4. Run v0.8

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` and select **Weather Intelligence**. Try Bengaluru, another Indian city, the 7-day forecast, weather map, weather-related news and **Ask Weather AI**. Choose Hindi or another supported language in the main response-language selector if Groq is configured. News will continue refreshing every 5 minutes; weather forecasts are cached for 10 minutes.

## 5. Review before your next GitHub push

```powershell
git diff --check
git check-ignore -v .env
git ls-files .env
git status --short
```

`git ls-files .env` must print **nothing**. After local verification you can stage and review the changes:

```powershell
git add .
git diff --cached --check
git diff --cached --stat
```

If the staged files are expected and contain no secrets, commit with `feat: add v0.8 weather intelligence` and push to `main`.

## Separate full ZIP

`BharatPulse-AI-v0.8-Weather.zip` is a **complete standalone project** for fresh installs. Use the smaller update ZIP above for the existing GitHub folder to avoid copying a second complete app.

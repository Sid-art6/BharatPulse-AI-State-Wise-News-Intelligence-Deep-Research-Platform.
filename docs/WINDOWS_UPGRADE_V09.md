# Windows Upgrade — BharatPulse AI v0.8 → v0.9

**Starting point:** The GitHub-connected v0.8 project is at:

`C:\Users\Administrator\Downloads\a\bharatpulse-AI`

The other folder (`C:\Users\Administrator\Downloads\BharatPulse-AI-v0.7\bharatpulse-ai`) was used for local development. Do not confuse it with the Git repository (`.git`).

## 1. Stop old server and back up local changes

Use `Ctrl+C` in the terminal hosting Uvicorn. In a new PowerShell terminal:

```powershell
cd "C:\Users\Administrator\Downloads\a\bharatpulse-AI"
git status --short
```

If there are unexpected uncommitted changes, save or commit them before installing this update. Your existing data and credentials are not in the ZIP.

## 2. Extract the **v0.9 Update ZIP** over the GitHub folder

Download `BharatPulse-AI-v0.9-Update.zip` into Downloads, then from the Git repo root:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\BharatPulse-AI-v0.9-Update.zip" -DestinationPath . -Force
```

It overwrites only specified source, tests and documentation files. It does **not** touch `.git`, `.venv`, `.env`, or `data/`.

## 3. Install actual LangGraph and LangSmith

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -c "from langgraph.graph import StateGraph; import langsmith; print('Real packages available')"
```

## 4. Configure your LangSmith key locally

Open `.env` in VS Code. **Do not replace the whole file or erase your existing Groq settings.** Add:

```ini
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=YOUR_PRIVATE_LANGSMITH_API_KEY
LANGSMITH_PROJECT=BharatPulse-v09-Research
```

Generate the key at https://smith.langchain.com/ . If you don't have the key yet, use `LANGSMITH_TRACING=false` and set it later. Never send a key in chat or commit it to GitHub. Tracing sends prompts/news excerpts/research questions/model outputs to LangSmith; it is not on-device-only.

## 5. Verify tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

All tests should run with **no skipped LangGraph integration tests**, and zero failures. This release has **not** yet been tested with installed LangGraph in this isolated build container, so do not assume a specific pass count until you run the command on Windows.

## 6. Start v0.9

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. In News Intelligence choose a real (not demo) article → **Research** → optionally write a research angle → **Run multi-agent research**. Inspect the LangGraph execution stages. In LangSmith, inspect project `BharatPulse-v09-Research` for a matching trace. **Do not push before testing.**

## 7. GitHub (after verification)

```powershell
git status --short
git check-ignore -v .env
git ls-files .env
git add .
git diff --cached --check
git diff --cached --stat
git commit -m "feat: add v0.9 LangGraph research and LangSmith observability"
git push origin main
git status
```

`git ls-files .env` must be empty. The LF/CRLF warnings on Windows are normal and don't indicate a failed commit. **Docker and Node.js are not needed.**

# Upgrade v0.6 → v0.7 — Windows / VS Code

Your current Git checkout is presumed to be:
`C:\Users\Administrator\Downloads\a\bharatpulse-AI`

**Do not replace the `.git` folder** (commit history), `.env` (Groq secret), `.venv` (installed Python), or `data` (stored news). v0.7 does not change the SQLite schema or the RSS polling schedule.

## Recommended: apply the patch to your existing Git checkout

1. Download **BharatPulse-AI-v0.7-update.patch** and **BharatPulse-AI-v0.7.zip** from the deliverables. Keep the ZIP as a complete source backup.
2. Stop the FastAPI server with `Ctrl+C`. In VS Code PowerShell, run:

```powershell
cd "C:\Users\Administrator\Downloads\a\bharatpulse-AI"
git status --short
```

Your working tree should be clean. If it isn't, review your uncommitted work before applying changes.

3. If the patch is in your Downloads folder, run:

```powershell
git apply --check "C:\Users\Administrator\Downloads\BharatPulse-AI-v0.7-update.patch"
git apply "C:\Users\Administrator\Downloads\BharatPulse-AI-v0.7-update.patch"
```

Do **not** execute `git apply` when `--check` fails. Send the error output for targeted troubleshooting instead of discarding local modifications.

4. Install/update project dependencies, then test:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Expected in the test environment used for authoring: **49 tests passed**.

5. Start your application again:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`, click **Test AI connection**, open a live Karnataka story and ask the two manual questions in `docs/CHAT_V07.md`.

6. Check the changes before committing:

```powershell
git diff --stat
git status --short
git ls-files .env
```

`git ls-files .env` must produce no output. If tests and live Groq behaviour are satisfactory:

```powershell
git add README.md .gitignore app/main.py app/chat_v07.py app/static/app.js app/static/style.css tests docs
git commit -m "feat: add v0.7 excerpt-anchored multilingual chat verification"
git push origin main
```

**Important:** The ZIP is useful for a fresh copy; the **patch** is recommended for your existing Git repository because it preserves your local setup and history. Never put your actual Groq key into chat, screenshots or GitHub.

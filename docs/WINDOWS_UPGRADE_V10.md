# Upgrade to BharatPulse AI v1.0 on Windows

This is a **candidate** release. Retain a backup of the verified v0.10 GitHub checkout before replacing files.

```powershell
cd "C:\Users\Administrator\Downloads\a\bharatpulse-AI"
git status
# Confirm you are on a clean main branch before copying a v1.0 candidate.
```

Extract the v1.0 ZIP beside your repository, not inside it. Copy source files excluding `.venv`, `.env`, local `data`, `.git`, `__pycache__` and test caches. Then:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`, inspect News Intelligence, Deep Research, and Weather Intelligence, and run a live RSS test. Review the README screenshot captions: all supplied images were captured from the v1.0 UI using **illustrative fixtures** and are not live-provider evidence.

**Do not push to `main` until the local tests and user-facing flows have been checked.** After final review, stage tracked source/docs/tests, confirm secrets are absent, commit `feat: release BharatPulse AI v1.0`, push and verify GitHub Actions. Then deploy on Render using `render.yaml`.

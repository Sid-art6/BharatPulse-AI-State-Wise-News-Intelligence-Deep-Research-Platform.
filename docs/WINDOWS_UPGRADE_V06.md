# Upgrade from v0.5 to v0.6 — Windows + VS Code (no WSL or Docker)

**This is the upgrade path for an existing working v0.5 dashboard with a Groq key and live news.**

## 1. Stop the running v0.5 server

In the old VS Code terminal press **Ctrl+C**. Keep the old project folder intact as a backup.

## 2. Extract the v0.6 ZIP into a NEW folder

For example, extract it as:

`C:\Users\Administrator\Downloads\bharatpulse-v06\bharatpulse-ai`

You should see `app`, `requirements.txt`, `.env.example`, and `docs` inside this folder. Do not copy files on top of the old v0.5 directory.

## 3. Preserve your existing Groq settings and news history

Using File Explorer, copy these **locally** from the old `bharatpulse-ai` folder into the newly extracted project root:

- `.env` — contains your private Groq API key. Do not paste it into ChatGPT or share screenshots of it.
- `data` — optional, if you want to retain your indexed stories and feed check history. The folder may not exist if no local news was saved. Copy it while the server is stopped.

Do **not** copy `.venv` from the old installation. The new project will make its own environment.

**Note:** v0.6 leaves the SQLite schema compatible with v0.5. However, older articles might have inaccurate publication dates because v0.5 assigned a fallback timestamp when a feed supplied none. v0.6 fixes this for newly ingested stories.

## 4. Open the v0.6 folder in VS Code

**File → Open Folder**, select the new project root. Then **Terminal → New Terminal** (PowerShell).

Run these commands one at a time:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` and click **Test AI connection**. If your existing `.env` was copied correctly, Groq should be configured as before.

## 5. Test Deep Research v2

1. Use **Live RSS** and select **Karnataka** or any state with articles.
2. Open a real news card and click **Research** → **Build research brief**.
3. Confirm there are readable headings, evidence quotes, clickable references, *Publication timeline (UTC)*, uncertainty notes and further-reporting questions.
4. If the excerpts do not support a research claim, the app will show **no approved AI findings** instead of guessing. This is correct behaviour.
5. Change the response language (e.g. Hindi or Kannada) and test another article.

## 6. Run automated tests (optional)

Open a **second** terminal in the new project root, and run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

The test suite uses mocked provider/network responses. It cannot guarantee that external RSS sites or Groq will always be available on your laptop.

## Common issues

- **`No module named uvicorn`** → ensure dependencies were installed using the `\.venv\Scripts\python.exe` interpreter shown above.
- **`Address already in use`** → stop the old v0.5 server using Ctrl+C.
- **Groq unavailable** → confirm your `.env` was copied into the new project root and run the connection test. Never share the key.
- **No AI-approved findings** → the Groq response may not contain a literal, supporting RSS excerpt. You can still inspect original publisher links.
- **Blank timeline entry** → the RSS feed didn't provide a valid publication date; v0.6 intentionally does not invent one.

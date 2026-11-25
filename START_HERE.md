# BharatPulse AI 1.6 on Windows

Extract the ZIP into a new folder. In File Explorer, open the **BharatPulse-AI** folder that contains `requirements.txt`, then open PowerShell there.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

For AI-generated answers, enter your key on the `GROQ_API_KEY=` line and save. The default provider is Groq. Set `ENABLE_LLM_FILTER=true` if you also want the model to screen incoming news. For a local model, set `LLM_PROVIDER=ollama`, `ENABLE_OLLAMA=true` and `OLLAMA_MODEL` to a model installed on your running Ollama server.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Select a live article, click **Ask AI**, then ask who published it. Once evidence is ready, ask a question requiring a detail from its body. For a report, open **Research** on the same article and enter a multi-part question.

In a second PowerShell window in the project folder, run the checks below. The first exercises the local server, the second tries current publisher feeds and URLs in a temporary database. Results vary with feed contents, publisher permissions and network access.

```powershell
.\.venv\Scripts\python.exe scripts\verify_local.py
.\.venv\Scripts\python.exe -m scripts.check_publisher_access
```

Existing installations can reuse their private `.env` and point `BHARATPULSE_DATA_DIR` at their data directory. Stop the old server and back up the data directory before using it with the new release. The app migrates the database and refreshes old reader-cache entries. Run one Uvicorn worker locally so article preparation and in-memory passages are shared across requests.

### Reuse an existing .env (optional)

If your previous verified `.env` is in the v1.2 folder shown below, copy it into the new folder **after** extracting this ZIP:

```powershell
$old = "C:\Users\Administrator\Downloads\BharatPulse_AI_v1.2_Claude_Audit_Integrated_Full_Project\BharatPulse-AI-v1.2"
if (Test-Path "$old\.env") { Copy-Item "$old\.env" ".\.env" -Force }
.\.venv\Scripts\python.exe -c "from app import ai; print('Provider:', ai.active_provider())"
```

Never commit `.env` or paste the key into a chat. See [v1.6 QA and deployment gate](docs/V16_QA_AND_DEPLOYMENT.md) before enabling public Groq access. [Earlier repair notes](docs/REPAIR_AND_VERIFICATION.md) remain available.

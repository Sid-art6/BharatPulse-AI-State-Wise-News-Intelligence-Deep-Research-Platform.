# BharatPulse AI v0.5 — Groq setup on Windows (VS Code)

This guide assumes that Python **3.11**, VS Code and BharatPulse v0.4 already worked on your Windows laptop. You do **not** need Docker or WSL.

## Stage 1 — Download and open the updated code

1. Download **BharatPulse-AI-v0.5-Groq.zip** from the ChatGPT conversation.
2. In File Explorer, right-click ZIP → **Extract All**. Extract into a new directory (don't delete your working v0.4 folder).
3. Open **VS Code → File → Open Folder** and choose the new extracted `bharatpulse-ai` directory, the one containing `requirements.txt`.
4. Open **Terminal → New Terminal**. Select PowerShell.

**Keep your old data (optional):** First stop the old FastAPI terminal with `Ctrl+C`. Copy the old project's `data` folder (including `news.db`) into the new project's directory. If you skip this, the new installation begins with an empty live-news database and automatically downloads new headlines. Your previously indexed data remain in the old folder.

## Stage 2 — Install Python libraries

Run these one at a time in the **new** VS Code project terminal:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The installation includes `python-dotenv`, which lets BharatPulse read your secret configuration from a `.env` file.

## Stage 3 — Add the Groq API key safely

In the same terminal run:

```powershell
Copy-Item .env.example .env
```

Open the new file called **`.env`** in VS Code. Edit only this line:

```ini
GROQ_API_KEY=your_actual_groq_key_here
```

Replace `your_actual_groq_key_here` with the real Groq key you generated at https://console.groq.com/keys. **Keep the value private. Do not paste your key into ChatGPT, GitHub, screenshots or public documents.**

Leave these lines as supplied:

```ini
LLM_PROVIDER=groq
GROQ_MODEL=openai/gpt-oss-20b
ENABLE_LLM_FILTER=true
BHARATPULSE_POLL_SECONDS=300
```

Groq can be used without installing Ollama or downloading any model on your laptop.

## Stage 4 — Start the server

If the previous BharatPulse server is still running on port 8000, press `Ctrl+C` in its VS Code terminal. Then in your **new** project terminal run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In Chrome open **http://127.0.0.1:8000**.

## Stage 5 — Verify Groq and try real news

1. Click **Test AI connection** (under AI RESEARCH on the dashboard). It sends a tiny test prompt.
2. If successful, it shows **GROQ READY**. The key is never displayed in the browser.
3. Choose **Live RSS**, select **Karnataka**, and verify headlines appear.
4. Choose the response language (English default or another supported language).
5. Open a headline → click **Ask AI** → ask, for example, *“What does the available news excerpt actually say?”*
6. Open the same headline → **Research → Start research**. It searches available RSS results and, when there are relevant sources, requests a cited brief.

**Important:** The chatbot uses *only the selected story and retrieved RSS evidence*, not open-ended model knowledge. If the sources cannot answer the question, the app must abstain and show a polite insufficient-information message. A citation number does not prove factual accuracy; verify publisher links. News filtering is an assistive relevance screen, not an official fact-check.

## Stage 6 — What the project is doing

- **RSS ingestion:** Takes a list of recent story titles, snippets, publishers and URLs from connected feeds.
- **Deduplication:** Checks stored headline fingerprints; stories already indexed are not sent repeatedly for LLM filtering.
- **Groq relevance filter:** Up to 20 new feed entries are screened for plausible India current-affairs relevance, not political viewpoint. If the API is unavailable, a deterministic-only fallback keeps the news explorer running.
- **Multilingual preview:** If an RSS excerpt is not English, Groq can translate a limited batch. The original text remains stored.
- **Retrieval:** Finds relevant stored or freshly discovered RSS excerpts for an individual article.
- **Chat / Research:** Sends a bounded source list to Groq, asks it to answer only from those sources, and checks source reference numbers. Insufficient evidence yields a no-information answer.
- **Refresh:** The backend polls sources at most once every five minutes per active region, even if the webpage is opened several times.

## Common problems

| Problem | What to do |
|---|---|
| **SOURCE MODE** | Check `.env` exists beside `requirements.txt`, has `LLM_PROVIDER=groq`, and contains a real key. Restart FastAPI. |
| **Groq API key rejected (401)** | Check key was copied correctly and is active. Never share it. |
| **Groq API rate limit (429)** | Wait for your account's limit reset, then retry. Avoid repeatedly clicking the AI buttons. |
| **Groq HTTP 400** | The model or parameters may have changed. Verify the current model ID at https://console.groq.com/docs/models. |
| **No AI synthesis** | The model may be unavailable, the API limit reached, or the RSS evidence insufficient. Check the original article links. |
| **Live news empty** | Inspect Last Success / Last Attempt; verify internet and news RSS access. Demo mode is not real news. |
| **Port 8000 already in use** | Stop the old FastAPI process with `Ctrl+C`. |
| **ModuleNotFoundError: dotenv** | Run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` in the project folder. |

This is a local **MVP**, not a fully production-deployed news intelligence service. X API, Google Trends, licensed regional publisher connectors, semantic vector search and LangGraph multi-agent processing are future development stages.

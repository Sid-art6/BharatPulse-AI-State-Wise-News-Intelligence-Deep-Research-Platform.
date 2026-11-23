# BharatPulse AI v0.9 — LangGraph & LangSmith

## What changed

Research runs as a **real LangGraph `StateGraph`**, not a hand-written fake or simulated coordinator. The graph is compiled once per application process and invoked with isolated state for each request. It does **not** persist conversations, create a durable checkpoint, or grant external tool execution. News ingestion, chat and weather remain intact.

```text
Selected REAL RSS article + optional research angle
    → Planner (deterministic bounded query from stored headline)
    → Discovery (Google News RSS metadata; safe cached fallback)
    → Retriever (selected article + related stored RSS entries)
          ├── inadequate sources / no model → Report Builder (source index, abstention)
          └── sources + available LLM
                    → Synthesis (JSON claims + literal quote/number validation)
                    → Quality Reviewer (separate conservative semantic judgement)
                    → Report Builder (approved claims or abstention)
```

**Source limits:** RSS titles, excerpts, publisher labels, timestamps and links only. The graph cannot independently verify factual truth, publisher independence, event dates or entire articles. Prompt injection in RSS metadata is an attack surface; snippets are treated as *data*, never as privileged instructions. The reviewer is a model, not an authoritative fact checker. No validated claims → no AI-derived findings.

## Configure real LangGraph

From the project folder in Windows VS Code PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -c "from langgraph.graph import StateGraph; import langsmith; print('LangGraph and LangSmith imports OK')"
.\.venv\Scripts\python.exe -m pytest -q
```

Do not install a lightweight replacement for LangGraph. Real-framework integration tests intentionally skip if the package is missing in an offline build environment; on your laptop, the package must be present for **all** integration tests to run.

## LangSmith API key (optional; opt-in)

1. Visit **https://smith.langchain.com/** and sign in. Open Settings to create a LangSmith API key. Do not paste it into chat or screenshots.
2. In your local **`.env`**, add these lines (replace the placeholder locally):

```ini
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=PASTE_YOUR_OWN_KEY_HERE
LANGSMITH_PROJECT=BharatPulse-v09-Research
# If required for an organisation-scoped key:
# LANGSMITH_WORKSPACE_ID=YOUR_WORKSPACE_ID
```

3. Restart FastAPI and open `/api/meta`; `langsmith_tracing` should report `configured` (this checks settings, **not connectivity**).
4. Open a **real** news item (not Demo data), choose **Research**, optionally enter an angle, and click **Run multi-agent research**.
5. Open the LangSmith project and inspect the run titled **BharatPulse v0.9 Deep Research**. Nodes are labelled by stage; Groq/Ollama completion steps are recorded as nested traces where supported by the SDK. LangSmith needs internet access; remote delivery is not verified by local automated tests.

To stop tracing, change `LANGSMITH_TRACING=false` and restart. A key by itself does not enable tracing. `LANGSMITH_API_KEY` stays only in `.env` and is never returned in API responses. Never commit `.env`.

### Privacy and cost

**Enabling tracing uploads research questions, RSS titles/excerpts, prompts and model outputs to LangSmith.** Do not submit confidential or personal content until you have the necessary permissions. LangSmith is a third-party cloud service; review its pricing, retention and data-processing terms. LangGraph orchestration is local and does not itself need a cloud API key. Groq model API usage may have limits and costs. Leave tracing disabled when working with sensitive material.

## Diagnostics

- **503 from `/api/research/{id}`**: install `requirements.txt` in the same virtual environment that runs Uvicorn; verify `from langgraph.graph import StateGraph`.
- **No LangSmith runs**: verify key, `LANGSMITH_TRACING=true`, internet, and workspace/project permissions, then restart Uvicorn. The API metadata only checks the configuration, not connectivity.
- **Insufficient evidence**: expected when sources are too short, fewer than two related RSS entries exist, a source quote is unsupported, a reviewer rejects findings or the LLM is unavailable.
- **429 / quota**: Groq provider limits may prevent synthesis and review; the workflow fails closed instead of showing unchecked assertions.
- **Weather map unchanged**: v0.8 map sync remains intact; select a supported city, not a research source.

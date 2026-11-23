> **v0.6 update:** BharatPulse supports GroqCloud as its primary, optional LLM provider and Ollama as a local alternative. Both use the same source-grounded RAG-style chat and research workflow. Groq setup is explained in [GROQ_WINDOWS_SETUP.md](GROQ_WINDOWS_SETUP.md).

# Two AI projects — explained from zero, stage by stage

This guide assumes zero background knowledge and builds the explanation one idea at a time. You can follow it after launching the apps.

## Project A: BharatPulse AI — the news investigator

**Very simple story:** Imagine thousands of newspaper headlines arriving at a desk. We want to pick the headlines relevant to a place, put them into labelled drawers, and help a researcher read the related evidence. BharatPulse is that desk.

### Stage A1 — What enters the system?
- **Input:** Google News RSS English and supported native-language queries, plus BBC India RSS for national coverage; each record includes headline, publisher, timestamp, original-language excerpt and link.
- **Why RSS?** It is a lightweight feed of article metadata. It is not a full article or proof that a claim is true.
- **Code:** `app/core.py` → `fetch_rss`, `fetch_news` and `parse_rss`.

### Stage A2 — Cleaning and organising
- **Cleaning:** Remove HTML markup, normalise whitespace, reject links that are not HTTPS.
- **Deduplication:** Convert a headline into a Unicode-preserving fingerprint so native-script headlines do not collapse into the same identifier.
- **Classification:** Scan headline/description for an explicitly named Indian state (English and selected native-script names), topic keywords and likely text script. This is heuristic, not a validated language classifier.
- **Honesty:** If no state is mentioned, tag **All India / not_verified** instead of guessing.
- **Optional AI screening:** If `ENABLE_LLM_FILTER=true` and a Groq or Ollama provider is configured, up to 20 newly discovered live headlines are screened for relevance; otherwise all items use the deterministic rules.
- **Code:** `app/core.py`, `app/regions.py`, `app/ai.py`.

### Stage A3 — Remember the information
- **SQLite** stores articles in `data/news.db` with their original language, and an optional separate English translation preview. Without a configured LLM, untranslated native-language excerpts remain labelled as original text.
- Think of a database as a table that survives after you shut the application down.
- **Code:** `app/core.py` → `init_db`, `save_articles`, `list_articles`.

### Stage A4 — Show a user-friendly dashboard
- The browser requests article data from **FastAPI**, and JavaScript builds the visible cards.
- The dashboard defaults to live news. On page opening it asks FastAPI to check the selected region; a feed fetch begins only if the last attempt was at least five minutes ago. A background loop repeats due checks while the backend is running. The browser checks for freshly stored stories every 20 seconds.
- A state dropdown and topic buttons filter stored stories; a response-language dropdown controls chat and research outputs (English by default).
- **Code:** `app/main.py` (routes), `app/static/` (interface).

### Stage A5 — One-click Deep Research v2
- Click **Research** on a real article.
- The backend searches RSS using the headline, compares candidate titles with the original, and prepares a linked **evidence index**.
- If Groq or Ollama is available, a constrained LLM proposes structured findings **with exact quotations** from RSS headlines/excerpts. The backend rejects bad source references and unsupported numbers. A separate publication-only timeline avoids confusing reporting date with event date.
- **Limitation:** This is not an independent verification engine and does not ingest full article text.
- **Code:** `app/main.py` → `deep_research`, `app/research_v2.py` → evidence screening, `app/core.py` → `find_related`, `app/ai.py` → LLM adapter, and `app/static/app.js` → report display.

### Stage A6 — Ask the article-specific chatbot
- A user sends a question.
- The backend retrieves the selected article and related local feed entries.
- If **a model provider** is configured, it uses these as limited context and answers with source numbers in the chosen response language. If the evidence is inadequate, it is instructed to abstain. Bad citation-number syntax triggers a deterministic fallback (citation syntax validation does not verify claim truth).
- If **no model provider** is available, it gives a polite **not enough information** notice in the selected language, then shows available sources **without pretending an AI answer exists**.
- **Code:** `app/main.py` → `chat`, `app/ai.py` → `ask_llm`.

### Stage A7 — Explain in an interview
> "I built a local-first regional news intelligence MVP. A FastAPI pipeline automatically polls Google News RSS in English and selected regional languages every five minutes, ingests metadata, normalises and deduplicates headlines, assigns explicit region and topic tags, and saves them in SQLite. The dashboard supports state-wise filtering. An investigation action retrieves related coverage, and an optional Groq or Ollama model generates cautious, source-referenced summaries or contextual Q&A. I deliberately separate verified metadata from hypothetical demo content and note that this is not full-text fact-checking."

**What to improve next:** production data licences, queues/scheduler, embeddings, evaluated classification, semantic event clustering, LangGraph research flow, source credibility scoring with human review, observability, RBAC and deployed infrastructure.

---

## Project B: Globalmove-AI — the document investigator

**Important:** These details are based on the publicly accessible `Sid-art6/Globalmove-AI` README as checked on November 23, 2026. Code-level claims should be verified when the project is running. Globalmove-AI is a separate repository and is not modified by BharatPulse.

**Very simple story:** Imagine someone gives an immigration caseworker several forms: a passport scan, an offer letter and supporting documents. The caseworker needs to find key details and see whether names and dates agree. Globalmove-AI assists with review using **evidence quotes**.

### Stage B1 — Upload the documents
- Upload PDF, DOCX, TXT or an image into a case workspace.
- The API accepts the files and stores case information.

### Stage B2 — Read the pages
- Text is extracted from digital PDFs and documents.
- **OCR** helps with scanned pages and pictures. OCR means *Optical Character Recognition*: converting words in a picture into machine-readable text.

### Stage B3 — Identify facts
- The pipeline classifies documents and proposes structured values such as a person's name or a passport-expiry date.
- It checks every proposed fact against an actual quotation on a page.
- If evidence is missing, it says **Not found** rather than filling in a guess.

### Stage B4 — Review consistency
- Rules look for mismatched names, missing passport evidence, unreadable documents and expiry issues.
- Those flags are **review prompts**, not legal decisions about immigration eligibility.

### Stage B5 — Explore and export
- A **Next.js** dashboard displays the document comparison grid, citations and flagged issues.
- A user can inspect source evidence, ask a source-based question and export PDF/CSV reports.

### Stage B6 — Explain in an interview
> "I built a local document-review workflow for immigration evidence, combining Python document parsing, optional OCR, deterministic field extraction, page-level quote verification and review rules. A FastAPI API serves a Next.js interface with evidence inspection, Q&A and report exports. The system defaults to local extractive retrieval, and optional LLM proposals are accepted only when corroborated by source quotations. It is a review assistant, not an immigration eligibility or legal advice engine."

### Stage B7 — Run Globalmove-AI separately
In its repository, start the backend from the `backend` directory on port **8000**, then start the Next.js frontend from `frontend` on port **3000** (see its own README). **Stop BharatPulse AI first**, because BharatPulse also uses port 8000 by default. Open `http://localhost:3000` for Globalmove-AI. Never use actual personal documents in a demo.

---

## The difference in one sentence

**BharatPulse** finds and compares **public news metadata**; **Globalmove-AI** extracts and checks **private document evidence**. Both use retrieval/evidence-grounding, but have different data types, risks and user interfaces.

## Your practice routine

1. Run BharatPulse in demo mode and point to the input, cleaning, database and interface stages.
2. Switch to Live RSS, fetch a real region, open a source link and run a research request.
3. Enable Groq or Ollama only after understanding the non-LLM evidence index; compare the two behaviours.
4. Stop BharatPulse. Start Globalmove-AI and load its synthetic sample documents.
5. Compare the **news metadata citation** in BharatPulse with the **page and verbatim quote citation** in Globalmove-AI.
6. In interviews, state **what is implemented, what is optional, and what you would add for production**.

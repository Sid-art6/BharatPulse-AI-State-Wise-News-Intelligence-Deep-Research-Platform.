# Article follow-up and identity routing — candidate QA

## Changes

- A standalone named-person identity question such as `Who is Rajiv Gandhi?` is classified as **general background**, with the selected RSS report supplied for disambiguation only; it does not quote unrelated feed items as proof of a person's identity.
- A request such as `Give me context?` is routed to a direct RSS-based overview rather than presenting a single generated claim as complete context.
- A short `Why?` or `Why ?` is linked to the selected article's event. When an election security alert headline is accompanied by an RSS excerpt describing surveillance and security measures, the assistant reports those measures while clearly saying a specific triggering threat or incident is *not established*.
- Unexplained detentions and other unsupported causal claims still produce cautious abstention rather than invented motives. The old provider-unavailable label is not used when evidence alone is insufficient.
- No additional external LLM, paid search or embeddings service is required by these rules.

## Real-world examples modelled in offline tests

1. **Rajiv Gandhi identity:** `Who is Rajiv Gandhi?` takes general background, not article-only retrieval. A mocked model confirms exactly one general completion and selected article context in the prompt.
2. **Election alert:** `Rayalaseema on high alert ahead of panchayat polls` + RSS excerpt `Sensitive villages placed under surveillance as officials strengthen security and enforce election rules` + `Why ?` gives a partial source-based explanation without inventing a threat.
3. **TMC MPs:** `Give me context?` triggers a source overview using indexed headline and excerpt, with sources labelled as publisher reporting rather than independent confirmation.
4. **Detention control:** `Why was the BJP chief detained?` remains insufficient-evidence when the only fact is that the person was on the way to a ceremony.

## Boundaries

- Grounding is limited to RSS headlines and excerpts available at request time; the app does not claim access to paywalled publisher articles.
- The named-person general answer still depends on Groq's knowledge for unknown identities, so factual accuracy is not guaranteed by these offline tests.
- LangGraph-dependent tests and real Groq completion tests require a fully configured Windows environment.
- Do not push to GitHub or enable public paid AI until manual acceptance and abuse controls are verified.

## Windows checks

```powershell
$python = "C:\Users\Administrator\Downloads\a\bharatpulse-AI\.venv\Scripts\python.exe"
& $python -m pytest -q
& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a separate PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Look for `short_question_revision : v1.0-article-followup-qa`.

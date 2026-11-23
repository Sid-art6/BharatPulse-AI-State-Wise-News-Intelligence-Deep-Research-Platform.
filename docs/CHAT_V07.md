# Chat v0.7 — grounded claim checks

## Why this change

The v0.6 chatbot accepted prose when it contained in-range citations such as `[1]`. A citation number alone **does not prove that an article supports the claim**. Hindi test runs exposed unsupported details and a possible reversal of who questioned Karnataka's E20 fuel testing method. v0.7 replaces citation-only acceptance with a conservative evidence workflow.

## Pipeline (beginners' walkthrough)

1. **Retrieve** the selected news item and up to five related articles from the existing SQLite store. Each source has a stable numeric index from 1 to 6. Only RSS headline/description text is used; timestamps are metadata, not evidence of when an event happened.
2. **Draft atomic claims in English (Groq/Ollama):** Ask the model for JSON records `{claim_en, source, quote}`. Each quote must be a contiguous piece of the referenced article's actual RSS headline or excerpt. A question that cannot be answered should produce an empty `claims` array.
3. **Check locally (no model):** Reject invalid source indices, nonmatching quotations, extra numbers/currency/percentages, weak lexical overlap on English quotes and oversized/malformed claims. This is conservative and may reject a true paraphrase.
4. **Review meaning (second model call):** A separate prompt evaluates whether each claim is actually entailed by its quoted evidence, checking actor, polarity, attribution, modality, dates and causality. The full set of Boolean verdicts must parse correctly; incomplete or ambiguous output is rejected.
5. **Only if language differs from English:** Translate *approved* English claims and reject translations that introduce new numbers. Request a final semantic-equivalence review; reject altered attribution, negation or scope.
6. **Render:** The browser receives only approved claim text with fixed numeric citations, the exact supporting quote and the cited publisher link. If no claim survives, it returns a polite language-specific **insufficient evidence** response. An unavailable model never causes invented text to be shown.

## Why this is not verified fact-checking

- RSS headlines and descriptions may be inaccurate, incomplete or syndicated; we do not retrieve full article text or primary documents.
- Exact-source quotation checks confirm *provenance of text*, not that the publisher's claim is true.
- A second prompt using an LLM can itself make mistaken entailment and translation judgments; **there is no guarantee of zero hallucinations**.
- Multilingual translation is an additional potential error source. English claims remain the validation bridge. Users should inspect linked original reporting for consequential claims.
- Current stage is a conservative *source-anchored AI draft*. Independent fact-checking, editorial review, robust language-specific evaluation and licensed full-text access are still needed.

## Failure cases

| Issue | Behaviour |
|---|---|
| Answer includes source index `[99]` but only three sources were retrieved | Candidate rejected |
| Invented quote or ₹900 crore absent from RSS excerpt | Candidate rejected |
| Quote says testing method was questioned; answer says method was approved | Entailment review instructed to reject; test confirms rejection when reviewer identifies contradiction |
| Hindi translation inserts an unsupported `९०० करोड़` claim | Numeric gate rejects before translation verdict |
| Translation changes 'questioned' into 'confirmed safe' | Equivalence review instructed to reject; test simulates rejection |
| Provider returns malformed JSON, an incomplete verdict, or a rate-limit error | No unsupported draft displayed; controlled fallback |

## Run evaluation

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

All automated LLM responses in these tests are **mocked**. The suite validates system gating, **not real-world Groq model accuracy**. Run live manual checks after upgrading with your own Groq key (never share it). Key v0.7 module: [`app/chat_v07.py`](../app/chat_v07.py).

## Suggested manual evaluation

Use the Karnataka E20 story in Hindi and English:

- “What did Suresh Gopi say about Karnataka's testing method?” — Look for cautious source-backed attribution.
- “Did he say Karnataka's testing method is correct?” — The tool must not invert the source's stated position.
- “What is the exact rupee loss from the controversy?” — Unless the indexed quote contains a defensible figure, it should abstain.
- Translate one story into Hindi/Kannada and ensure the claim preserves names, speaker, negations and cited source.

**Cost note:** English chat may require two provider calls; translated responses may require four. The system does not automatically retry provider failures, and the 5-minute news refresh cadence is unchanged.

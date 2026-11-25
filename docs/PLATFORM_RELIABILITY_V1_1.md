# Platform-wide Reliability & Intelligence Upgrade (v1.0 portfolio reliability update)

This release addresses generic failure modes, not specific news stories. The RSS index remains the source-of-truth. No full-text journalism or independent fact-checking is claimed.

## Design decisions

- **Article-first routing**: Identifiers in the selected article and primary headline subjects do not enter ungrounded general-knowledge generation. Common stand-alone definitions can remain in the separate general route.
- **Deterministic provenance**: Questions asking which publishers reported an item return indexed publisher names and URLs, not a generic no-evidence message.
- **Chronology**: 'What happened next?' abstains on unseen later events; an article's publication timestamp is not an event timeline.
- **Six-stage LangGraph trace**: Planner, Discovery, Retriever, Synthesis, Quality Reviewer and Report Builder are all invoked. If a provider is offline, Synthesis/Review appear as *skipped*, not falsely completed.
- **Relationship labels**: Secondary headlines are labelled as topical context or possible same-story reporting; neither means independent corroboration.
- **Evidence boundary**: Quotes must match actual RSS title/excerpt text; numeric support and LLM semantic review remain mandatory for generated claims.
- **Security**: Existing public-demo request-size checks, quotas, session isolation, same-origin public-mode checks and security headers are retained. These are baseline controls, not a substitute for deployment hardening.

## Limits

A source-supported draft is not a verified fact. Models can still make semantic mistakes, and excerpts may omit important context. Live Groq, RSS, LangGraph and weather must be checked in the deployment environment. Do not claim zero hallucinations or independent validation.

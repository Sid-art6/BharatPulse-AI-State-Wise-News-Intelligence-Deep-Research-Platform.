"""KPSC acceptance regressions: all offline, no network or real LLM use."""
import asyncio
import json

from app import ai, core, coverage_v10, research_v2, research_agents_v09 as agents

KPSC = {
    "id": "kpsc-selected", "title": "KPSC scam: ED files chargesheet against four, relies on candidate statements and OMR sheet analysis",
    "description": "ED says the accused had demanded ₹3.5 crore from candidates for leaking question papers and answer keys but managed to collect ₹1.82 crore",
    "publisher": "The Hindu", "region": "All India", "published_at": "2026-11-24T15:32:00+00:00",
    "url": "https://source.example/kpsc", "fingerprint": "unique-kpsc", "is_demo": False,
}


def test_single_source_with_model_routes_to_synthesis(monkeypatch):
    monkeypatch.setattr(core, "list_articles", lambda **kw: [])
    monkeypatch.setattr(core, "find_related", lambda selected, candidates, limit: [])
    async def ready(): return True
    monkeypatch.setattr(ai, "llm_is_configured", ready)
    outcome = asyncio.run(agents.retrieve({"selected": KPSC, "discovered": []}))
    assert len(outcome["sources"]) == 1
    assert outcome["llm_ready"] is True
    assert agents.route_after_retrieval(outcome) == "synthesise"
    assert "corroboration" in outcome["trace"][0]["detail"]


def test_single_source_without_model_still_exposes_index(monkeypatch):
    monkeypatch.setattr(core, "list_articles", lambda **kw: [])
    monkeypatch.setattr(core, "find_related", lambda selected, candidates, limit: [])
    async def offline(): return False
    monkeypatch.setattr(ai, "llm_is_configured", offline)
    outcome = asyncio.run(agents.retrieve({"selected": KPSC, "discovered": []}))
    assert agents.route_after_retrieval(outcome) == "synthesise"  # Synthesis records skipped stage when no model
    result = asyncio.run(agents.assemble(outcome))
    assert result["mode"] == "source_index_no_llm"
    assert outcome["report"]["source_observations"][0]["headline"] == KPSC["title"]


def test_one_kpsc_source_can_generate_attributed_findings(monkeypatch):
    calls = []
    async def fake_llm(messages, *, json_mode, max_tokens):
        calls.append(messages)
        return json.dumps({"findings": [
            {"claim": "The Hindu reports that ED filed a chargesheet against four people.",
             "claim_en": "The Hindu reports that ED filed a chargesheet against four people.",
             "evidence": [{"source": 1, "quote": "ED files chargesheet against four"}]},
            {"claim": "The excerpt attributes a reported demand of ₹3.5 crore to the accused.",
             "claim_en": "The excerpt attributes a reported demand of ₹3.5 crore to the accused.",
             "evidence": [{"source": 1, "quote": KPSC["description"]}]},
        ]})
    monkeypatch.setattr(ai, "_complete", fake_llm)
    report = asyncio.run(research_v2.generate_report([KPSC]))
    assert len(calls) == 1
    assert report["status"] == "anchored_excerpt_claims"
    assert len(report["findings"]) == 2
    assert report["source_observations"][0]["source"] == 1


def test_single_source_still_requires_semantic_review(monkeypatch):
    proposed = research_v2.build_report(json.dumps({"findings": [
        {"claim": "The four filed a chargesheet against ED in the KPSC case.",
         "claim_en": "The four filed a chargesheet against ED in the KPSC case.",
         "evidence": [{"source": 1, "quote": "KPSC scam: ED files chargesheet against four"}]}
    ]}), [KPSC])
    assert proposed["findings"]  # mechanical quote matching is NOT a verdict
    async def reject(messages, *, json_mode, max_tokens):
        return '{"decisions":[{"id":1,"supported":false}]}'
    monkeypatch.setattr(ai, "_complete", reject)
    outcome = asyncio.run(agents.semantic_review({"report": proposed, "sources": [KPSC]}))
    assert outcome["review_status"] == "review_completed"
    assert outcome["report"]["findings"] == []
    assert outcome["report"]["source_observations"]


def test_second_query_is_bounded_and_only_title_derived(monkeypatch):
    query = agents.fallback_query(KPSC["title"])
    assert "KPSC" in query and "chargesheet" in query and query.endswith("when:30d")
    assert "candidate statements and OMR sheet analysis" not in query
    assert "https" not in query
    seen = []
    extra = dict(KPSC, id="other-report", url="https://source.example/other", fingerprint="other",
                 title="KPSC scam ED investigation reviewed", publisher="Second Publisher")
    async def fake_rss(q):
        seen.append(q)
        return b"<rss><channel/></rss>"
    def parse_rss(data, region):
        return [KPSC] if len(seen) == 1 else [extra]
    monkeypatch.setattr(core, "fetch_rss", fake_rss)
    monkeypatch.setattr(core, "parse_rss", parse_rss)
    monkeypatch.setattr(core, "save_articles", lambda items: len(items))
    result = asyncio.run(agents.discover({"query": agents.safe_query(KPSC["title"]), "selected": KPSC}))
    assert len(seen) == 2
    assert len(result["discovered"]) == 2
    assert result["discovered"][1]["id"] == "other-report"


def test_secondary_search_failure_keeps_primary(monkeypatch):
    seen = []
    async def fake_rss(q):
        seen.append(q)
        if len(seen) == 2:
            raise ValueError("synthetic RSS provider timeout")
        return b"<rss><channel/></rss>"
    monkeypatch.setattr(core, "fetch_rss", fake_rss)
    monkeypatch.setattr(core, "parse_rss", lambda data, region: [KPSC])
    monkeypatch.setattr(core, "save_articles", lambda items: len(items))
    result = asyncio.run(agents.discover({"query": agents.safe_query(KPSC["title"]), "selected": KPSC}))
    assert len(seen) == 2
    assert result["discovered"][0]["id"] == "kpsc-selected"
    assert result["trace"][0]["status"] == "completed"


def test_money_contexts_start_at_word_boundaries():
    amounts = coverage_v10.analyse_coverage([KPSC])["reported_numbers"]
    wanted = [row for row in amounts if "₹1.82" in row["value"]]
    assert len(wanted) == 1
    assert not wanted[0]["context"].startswith("apers")
    assert wanted[0]["source"] == 1


def test_one_source_pipeline_reaches_semantic_review_and_assembly(monkeypatch):
    """The exact path skipped by the original KPSC report now executes."""
    monkeypatch.setattr(core, "list_articles", lambda **kw: [])
    monkeypatch.setattr(core, "find_related", lambda selected, candidates, limit: [])
    async def ready(): return True
    monkeypatch.setattr(ai, "llm_is_configured", ready)
    monkeypatch.setattr(ai, "active_provider", lambda: "groq")
    calls = []
    async def fake_completion(messages, *, json_mode, max_tokens):
        prompt = messages[-1]["content"]
        calls.append("review" if "INPUT:" in prompt else "generate")
        if "INPUT:" in prompt:
            return '{"decisions":[{"id":1,"supported":true}]}'
        return json.dumps({"findings": [{
            "claim": "The report says the ED filed a chargesheet against four.",
            "claim_en": "The report says the ED filed a chargesheet against four.",
            "evidence": [{"source": 1, "quote": "ED files chargesheet against four"}],
        }]})
    monkeypatch.setattr(ai, "_complete", fake_completion)
    initial = asyncio.run(agents.retrieve({"selected": KPSC, "discovered": []}))
    assert agents.route_after_retrieval(initial) == "synthesise"
    draft = asyncio.run(agents.synthesise({**initial, "language": "English", "question": "What happened?"}))
    assert len(draft["report"]["findings"]) == 1
    reviewed = asyncio.run(agents.semantic_review({**initial, **draft}))
    assembled = asyncio.run(agents.assemble({**initial, **draft, **reviewed}))
    assert calls == ["generate", "review"]
    assert reviewed["review_status"] == "review_completed"
    assert assembled["mode"] == "groq"


def test_single_source_unsupported_numeric_claim_remains_blocked():
    report = research_v2.build_report(json.dumps({"findings": [{
        "claim": "The ED proved the accused collected ₹900 crore.",
        "claim_en": "The ED proved the accused collected ₹900 crore.",
        "evidence": [{"source": 1, "quote": KPSC["description"]}],
    }]}), [KPSC])
    assert not report["findings"]
    assert report["rejected_claims"] == 1

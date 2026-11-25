"""BharatPulse QA hotfix: all tests are offline and use synthetic RSS data.

Run: python -m pytest -q tests/test_final_qa_repair.py
"""
import asyncio
import json

from app import ai, chat_v07, core, research_v2


def story(id_, title, description, publisher="Regional desk"):
    return {
        "id": id_, "title": title, "description": description, "publisher": publisher,
        "region": "Karnataka", "published_at": "2026-11-23T05:00:00+00:00",
        "url": "https://example.org/story/" + id_, "fingerprint": id_,
        "is_demo": False,
    }


SELECTED = story(
    "selected", "BJP leaders demand action against author Ravi Hanj",
    "Leaders demanded action against author Ravi Hanj over allegedly insulting remarks about Basavanna.",
    "Karnataka Regional Desk",
)
RELATED = story(
    "related", "Complaint filed following remarks by Ravi Hanj",
    "Police received a complaint about remarks attributed to author Ravi Hanj.",
    "Another Karnataka Outlet",
)
UNRELATED = story(
    "unrelated", "BJP leaders launch campaign in Assam",
    "A political campaign was announced in Assam without any connection to the Karnataka author.",
    "Other Newspaper",
)


def test_generic_party_coverage_does_not_pollute_selected_article():
    found = core.find_related(SELECTED, [UNRELATED, RELATED], limit=5)
    assert [item["id"] for item in found] == ["related"]


def test_original_rss_observations_survive_even_without_approved_findings():
    report = research_v2.initial_report([SELECTED, RELATED])
    assert report["status"] == "insufficient_evidence"
    assert report["findings"] == []
    assert len(report["source_observations"]) == 2
    assert report["source_observations"][0] == {
        "source": 1, "publisher": "Karnataka Regional Desk",
        "headline": SELECTED["title"], "excerpt": SELECTED["description"],
    }
    assert report["publication_timeline"][0]["source"] == 1


def test_exact_quote_candidate_is_not_prematurely_rejected_for_paraphrase():
    payload = {"findings": [{
        "claim": "The author was criticised over remarks described as insulting Basavanna.",
        "claim_en": "The author was criticised over remarks described as insulting Basavanna.",
        "evidence": [{"source": 1,
                      "quote": "Leaders demanded action against author Ravi Hanj over allegedly insulting remarks about Basavanna."}],
    }]}
    report = research_v2.build_report(json.dumps(payload), [SELECTED, RELATED])
    assert len(report["findings"]) == 1
    # This pre-review validation is NOT independent semantic or factual verification.


def test_nonexistent_quote_or_unsupported_number_stays_rejected():
    payload = {"findings": [
        {"claim": "The author was sentenced to 2027 years in prison.",
         "claim_en": "The author was sentenced to 2027 years in prison.",
         "evidence": [{"source": 1, "quote": SELECTED["title"]}]},
        {"claim": "All allegations were confirmed by a court.",
         "claim_en": "All allegations were confirmed by a court.",
         "evidence": [{"source": 1, "quote": "This quote is not present in the RSS article."}]},
    ]}
    report = research_v2.build_report(json.dumps(payload), [SELECTED, RELATED])
    assert report["findings"] == []
    assert report["rejected_claims"] == 2
    assert len(report["source_observations"]) == 2


def test_second_synthesis_pass_still_requires_exact_quote(monkeypatch):
    count = 0
    async def model(messages, *, json_mode, max_tokens):
        nonlocal count
        count += 1
        if count == 1:
            return '{"findings":[]}'
        return json.dumps({"findings": [{
            "claim": "The leaders demanded action against author Ravi Hanj.",
            "claim_en": "The leaders demanded action against author Ravi Hanj.",
            "evidence": [{"source": 1, "quote": SELECTED["title"]}],
        }]})
    monkeypatch.setattr(ai, "_complete", model)
    report = asyncio.run(research_v2.generate_report([SELECTED, RELATED]))
    assert count == 2
    assert len(report["findings"]) == 1
    assert report["findings"][0]["evidence"][0]["source"] == 1


def test_second_synthesis_failure_preserves_source_index(monkeypatch):
    count = 0
    async def model(messages, *, json_mode, max_tokens):
        nonlocal count
        count += 1
        if count == 1:
            return '{"findings":[]}'
        raise ai.LLMServiceError("Simulated API quota")
    monkeypatch.setattr(ai, "_complete", model)
    report = asyncio.run(research_v2.generate_report([SELECTED, RELATED]))
    assert count == 2
    assert not report["findings"]
    assert len(report["source_observations"]) == 2


def test_chat_candidate_may_enter_semantic_review_with_safe_exact_quote():
    raw = json.dumps({"claims": [{
        "claim_en": "The leaders asked officials to take action against author Ravi Hanj.",
        "source": 1,
        "quote": "Leaders demanded action against author Ravi Hanj over allegedly insulting remarks about Basavanna.",
    }]})
    accepted, rejected = chat_v07.validate_candidate_claims(raw, [SELECTED, RELATED])
    assert len(accepted) == 1 and rejected == 0


def test_semantic_reviewer_alone_controls_final_approval(monkeypatch):
    from app import research_agents_v09 as agent
    report = research_v2.build_report(json.dumps({"findings": [{
        "claim": "Author Ravi Hanj demanded action against the leaders.",
        "claim_en": "Author Ravi Hanj demanded action against the leaders.",
        "evidence": [{"source": 1, "quote": SELECTED["title"]}],
    }]}), [SELECTED, RELATED])
    assert len(report["findings"]) == 1
    async def reviewer(messages, *, json_mode, max_tokens):
        return '{"decisions":[{"id":1,"supported":false}]}'
    monkeypatch.setattr(ai, "_complete", reviewer)
    outcome = asyncio.run(agent.semantic_review({"sources": [SELECTED, RELATED], "report": report}))
    assert outcome["report"]["findings"] == []
    assert outcome["report"]["source_observations"][0]["source"] == 1
    assert outcome["report"]["status"] == "insufficient_evidence"

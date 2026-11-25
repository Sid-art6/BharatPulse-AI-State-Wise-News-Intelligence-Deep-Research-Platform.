"""Offline v0.9 tests. External RSS/LLM services are always mocked."""
import asyncio
import json

import pytest

from app import ai, core, research_agents_v09 as agents, research_v2


SOURCES = [
    {"id": "one", "title": "Karnataka panel reviews fuel testing", "description": "Panel reviews fuel testing methods in Karnataka.",
     "region": "Karnataka", "publisher": "Local Paper", "published_at": "2026-11-20T08:00:00+00:00",
     "url": "https://news.example/one", "is_demo": False},
    {"id": "two", "title": "Karnataka testing report draws attention", "description": "Fuel testing report and panel review noted.",
     "region": "Karnataka", "publisher": "Another Outlet", "published_at": "2026-11-21T08:00:00+00:00",
     "url": "https://news.example/two", "is_demo": False},
]


def test_query_is_bounded_to_server_stored_title():
    result = agents.safe_query('Karnataka: fuel testing! https://evil.example/run?token=123')
    assert result.endswith('when:30d')
    assert 'https:' not in result
    assert len(result) <= 120
    assert agents.safe_query('!!!') == ''


@pytest.mark.parametrize('raw', [
    'bad json', '[]', '{"decisions":[]}',
    '{"decisions":[{"id":1,"supported":"true"}]}',
    '{"decisions":[{"id":0,"supported":true}]}',
    '{"decisions":[{"id":1,"supported":true},{"id":1,"supported":true}]}',

])
def test_malformed_semantic_review_never_approves(raw):
    assert agents.parse_review(raw, [{"claim": "a"}, {"claim": "b"}]) == set()


def test_unknown_reviewer_id_does_not_approve_that_id():
    assert agents.parse_review('{"decisions":[{"id":1,"supported":true},{"id":999,"supported":true}]}',
                               [{"claim":"a"},{"claim":"b"}]) == {1}


def test_semantic_review_accepts_only_explicit_positive_id():
    raw = json.dumps({'decisions': [{'id': 1, 'supported': True}, {'id': 2, 'supported': False}]})
    assert agents.parse_review(raw, [{"claim": "a"}, {"claim": "b"}]) == {1}


def test_review_failure_fails_closed(monkeypatch):
    async def failed(_messages, *, json_mode, max_tokens):
        raise ai.LLMServiceError('simulated quota failure')
    monkeypatch.setattr(ai, '_complete', failed)
    report = research_v2.build_report(json.dumps({'findings':[{
        'claim':'Karnataka panel reviews fuel testing methods.',
        'claim_en':'Karnataka panel reviews fuel testing methods.',
        'evidence':[{'source':1,'quote':'Karnataka panel reviews fuel testing'}],
    }]}), SOURCES)
    assert len(report['findings']) == 1
    outcome = asyncio.run(agents.semantic_review({'report':report,'sources':SOURCES}))
    assert outcome['review_status'] == 'review_unavailable'
    assert not outcome['report']['findings']
    assert outcome['report']['status'] == 'insufficient_evidence'
    assert outcome['report']['rejected_claims'] == 1


def test_retrieval_without_model_routes_to_source_index(monkeypatch):
    monkeypatch.setattr(core, 'list_articles', lambda **kwargs: SOURCES)
    monkeypatch.setattr(core, 'find_related', lambda selected, candidates, limit: [SOURCES[1]])
    async def offline(): return False
    monkeypatch.setattr(ai, 'llm_is_configured', offline)
    state = asyncio.run(agents.retrieve({'selected':SOURCES[0], 'discovered':[]}))
    assert state['sources'][0]['id'] == 'one'
    assert agents.route_after_retrieval(state) == 'synthesise'  # six-stage graph records skipped AI work
    done = asyncio.run(agents.assemble({**state, 'review_status':'not_run'}))
    assert done['mode'] == 'source_index_no_llm'


def test_followup_failure_uses_cached_source_index(monkeypatch):
    async def failed(_query):
        raise ValueError('simulated RSS response failure')
    monkeypatch.setattr(core, 'fetch_rss', failed)
    result = asyncio.run(agents.discover({'query':'Karnataka fuel when:30d', 'selected':SOURCES[0]}))
    assert result['discovered'] == []
    assert 'RSS follow-up unavailable' in result['warning']
    assert result['trace'][0]['status'] == 'degraded'


def test_question_guides_synthesis_not_network_search(monkeypatch):
    captured = {}
    async def fake_generate(sources, language, question=''):
        captured.update({'sources':sources,'language':language,'question':question})
        return research_v2.initial_report(sources)
    monkeypatch.setattr(research_v2,'generate_report',fake_generate)
    result = asyncio.run(agents.synthesise({
        'sources':SOURCES, 'language':'Hindi', 'question':'What can the RSS evidence establish?',
    }))
    assert result['report']['findings'] == []
    assert captured['language']=='Hindi' and captured['question'].startswith('What can')


def test_real_langgraph_compiles_when_dependency_is_installed():
    pytest.importorskip('langgraph')
    compiled = agents.build_graph()
    assert compiled is not None
    assert hasattr(compiled,'ainvoke')


def test_langgraph_research_approves_only_reviewed_claims(monkeypatch):
    pytest.importorskip('langgraph')
    monkeypatch.setattr(core,'list_articles',lambda **kwargs:SOURCES)
    monkeypatch.setattr(core,'find_related',lambda selected,candidates,limit:[SOURCES[1]])
    monkeypatch.setattr(core,'save_articles',lambda items:0)
    async def empty_rss(_query): return b'<rss><channel/></rss>'
    monkeypatch.setattr(core,'fetch_rss',empty_rss)
    async def ready():return True
    monkeypatch.setattr(ai,'llm_is_configured',ready)
    monkeypatch.setattr(ai,'active_provider',lambda:'groq')
    async def fake_generate(sources,language,question=''):
        return research_v2.build_report(json.dumps({'findings':[{
            'claim':'Karnataka panel reviews fuel testing methods.',
            'claim_en':'Karnataka panel reviews fuel testing methods.',
            'evidence':[{'source':1,'quote':'Karnataka panel reviews fuel testing'}],
        }]}), sources)
    monkeypatch.setattr(research_v2,'generate_report',fake_generate)
    async def reviewer(messages,*,json_mode,max_tokens):
        return json.dumps({'decisions':[{'id':1,'supported':True}]})
    monkeypatch.setattr(ai,'_complete',reviewer)
    agents._graph = None
    result = asyncio.run(agents.run_research(SOURCES[0], 'English', 'What is confirmed?'))
    assert result['generated_by'] == 'groq'
    assert len(result['report']['findings']) == 1
    assert result['workflow']['engine'] == 'LangGraph StateGraph'
    assert result['workflow']['approved_findings'] == 1
    assert [node['agent'] for node in result['workflow']['trace']] == [
        'Planner','Discovery','Retriever','Synthesis','Quality Reviewer','Report Builder'
    ]
    assert result['report']['publication_timeline'][0]['source'] == 1


def test_langgraph_research_rejects_semantically_unsupported_claim(monkeypatch):
    pytest.importorskip('langgraph')
    monkeypatch.setattr(core,'list_articles',lambda **kwargs:SOURCES)
    monkeypatch.setattr(core,'find_related',lambda selected,candidates,limit:[SOURCES[1]])
    monkeypatch.setattr(core,'save_articles',lambda items:0)
    async def empty_rss(_query): return b'<rss><channel/></rss>'
    monkeypatch.setattr(core,'fetch_rss',empty_rss)
    async def ready(): return True
    monkeypatch.setattr(ai,'llm_is_configured',ready)
    monkeypatch.setattr(ai,'active_provider',lambda:'groq')
    async def fake_generate(sources,language,question=''):
        return research_v2.build_report(json.dumps({'findings':[{
            'claim':'Karnataka panel reviews fuel testing methods.',
            'claim_en':'Karnataka panel reviews fuel testing methods.',
            'evidence':[{'source':1,'quote':'Karnataka panel reviews fuel testing'}],
        }]}), sources)
    monkeypatch.setattr(research_v2,'generate_report',fake_generate)
    async def reviewer(messages,*,json_mode,max_tokens):
        return json.dumps({'decisions':[{'id':1,'supported':False}]})
    monkeypatch.setattr(ai,'_complete',reviewer)
    agents._graph = None
    result = asyncio.run(agents.run_research(SOURCES[0]))
    assert result['generated_by'] == 'insufficient_evidence'
    assert result['report']['findings'] == []
    assert result['report']['rejected_claims'] == 1
    assert result['workflow']['review_status'] == 'review_completed'


def test_langsmith_status_exposes_no_key(monkeypatch):
    from app.main import meta
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-secret-never-return")
    result = asyncio.run(meta())
    assert result["langsmith_tracing"] == "configured"
    assert "test-secret-never-return" not in json.dumps(result)


def test_langsmith_is_disabled_by_default(monkeypatch):
    from app.main import meta
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    assert asyncio.run(meta())["langsmith_tracing"] == "disabled"

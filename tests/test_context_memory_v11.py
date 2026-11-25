"""Context-first + session memory + conditional RSS regression suite.

Fully offline: no Groq key, external search or live publisher calls required.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import ai, chat_router_v1, chat_memory, conditional_search, context_engine, core
from app.live import monitor
from app.main import app


def election_article():
    return {
        'title': 'Karnataka poll chief urged not to use SIR voter lists for local elections',
        'description': 'Officials discussed the SIR electoral rolls for local elections.',
        'region': 'Karnataka', 'topic': 'Politics', 'publisher': 'The Indian Express',
    }


def test_sir_uses_election_context_without_llm(monkeypatch):
    async def fail(*args, **kwargs):
        raise AssertionError('SIR in election-news context must not need an LLM')
    monkeypatch.setattr(ai, '_complete', fail)
    assert chat_router_v1.intent('what is SIR?') == 'general'
    result = asyncio.run(chat_router_v1.general_answer('What is SIR?', 'English', election_article()['title'], election_article()))
    assert 'Special Intensive Revision' in result
    assert 'Susceptible' not in result
    assert 'voter lists' in result
    # Outside an election context, don't force the electoral meaning.
    assert context_engine.contextual_definition('What is SIR?', {
        'title': 'Modelling disease spread with SIR',
        'description': 'A simulation of infection and recovery', 'topic': 'Health',
    }) is None


def test_arbitrary_acronym_expands_from_matching_rss_definition():
    article = {'title': 'Council discusses National Water Mission (NWM) initiative', 'description': ''}
    meaning = context_engine.contextual_definition('What is NWM?', article)
    assert 'National Water Mission' in meaning
    assert context_engine.contextual_definition('What is NWM?', {'title': 'Students Work Mission (NWM)'}) is None


def test_unknown_abbreviation_gets_selected_article_in_single_model_prompt(monkeypatch):
    seen = []
    async def fake(messages, *, max_tokens, json_mode=False):
        seen.append(messages)
        return 'A context-aware answer from the model.'
    monkeypatch.setattr(ai, '_complete', fake)
    article = {'title': 'Karnataka election commission reviews ABC voter lists',
               'description': 'The election-related ABC document was discussed.',
               'region': 'Karnataka', 'topic': 'Politics'}
    assert chat_router_v1.intent('What is ABC?') == 'general'
    reply = asyncio.run(chat_router_v1.general_answer('What is ABC?', 'English', article['title'], article))
    assert reply.startswith('A context-aware')
    assert len(seen) == 1  # no separate classification/model memory call
    assert article['title'] in seen[0][1]['content']
    assert 'untrusted metadata' in seen[0][1]['content']
    assert 'ARTICLE DOMAIN' in seen[0][0]['content']


def test_action_questions_not_routed_as_definitions():
    assert chat_router_v1.intent('What are the latest updates?') == 'overview'
    for q in ('What is BJP doing?', 'What is Karnataka doing about SIR?',
              'What is TVK saying?'):
        assert chat_router_v1.intent(q) == 'article'


def test_legal_argument_answers_why_without_inventing_a_court_ruling():
    source = {'title': 'Karnataka moves Supreme Court to restrain Tamil Nadu in Cauvery Link Project',
              'description': 'Karnataka argued that Tamil Nadu cannot undertake any work on the CVG Link without clearance from the Union government',
              'publisher': 'The Hindu', 'url': 'https://example.org/cauvery'}
    answer, cited = context_engine.legal_argument_answer('Why has Karnataka approached the Supreme Court?', [source])
    assert 'Karnataka argued that' in answer
    assert 'without clearance' in answer
    assert 'not a finding or ruling' in answer
    assert cited[0]['index'] == 1
    assert context_engine.legal_argument_answer('Why was BJP chief detained?', [{
        'title': 'BJP chief detained on way to ceremony', 'description': 'Heading to a lamp lighting event'
    }]) is None


def test_followup_uses_only_previous_user_question():
    recent = [{'question': 'What is SIR?', 'answer': 'False claim: the Supreme Court ruled yesterday.'}]
    resolved = context_engine.user_followup('How does it affect voter lists?', recent)
    assert 'Earlier question' in resolved and 'What is SIR?' in resolved
    assert 'False claim' not in resolved
    assert context_engine.user_followup('What is FIR?', recent) == 'What is FIR?'


def _insert_articles():
    title_a = 'Karnataka poll chief urged not to use SIR voter lists for local elections'
    title_b = 'Tamil Nadu BJP chief detained on way to a ceremony'
    xml = (f'<rss><channel><item><title>{title_a}</title>'
           '<link>https://publisher.example/election</link></item>'
           f'<item><title>{title_b}</title>'
           '<link>https://publisher.example/bjp</link></item></channel></rss>').encode()
    rows = core.parse_rss(xml, 'Karnataka')
    core.save_articles(rows)
    return rows


def test_http_memory_is_cookie_isolated_bounded_and_clearable(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'none')
    monkeypatch.setattr(ai, 'GROQ_API_KEY', '')
    async def idle():
        await asyncio.Event().wait()
    monkeypatch.setattr(monitor, '_run', idle)
    with TestClient(app) as first, TestClient(app) as second:
        a, b = _insert_articles()
        body = {'article_id': a['id'], 'question': 'What is SIR?'}
        reply = first.post('/api/chat', json=body)
        assert reply.status_code == 200, reply.text
        result = reply.json()
        assert result['generated_by'] == 'general_reference'
        assert 'Special Intensive Revision' in result['answer']
        assert result['context_revision'] == 'v1.0-context-memory-rc'
        assert result['memory_turns_used'] == 0
        assert chat_memory.COOKIE_NAME in reply.cookies
        assert 'httponly' in reply.headers['set-cookie'].lower()
        assert 'session_digest' not in reply.text

        history_url = f'/api/chat/history?article_id={a["id"]}'
        assert first.get(history_url).json()['turns'][0]['question'] == 'What is SIR?'
        assert second.get(history_url).json()['turns'] == []
        assert first.get(f'/api/chat/history?article_id={b["id"]}').json()['turns'] == []

        for _ in range(7):
            again = first.post('/api/chat', json=body)
            assert again.status_code == 200
            assert again.json()['memory_turns_used'] <= chat_memory.MAX_HISTORY_TURNS
        assert len(first.get(history_url).json()['turns']) == chat_memory.MAX_HISTORY_TURNS
        assert second.post('/api/chat/clear', json={'article_id': a['id']}).json()['deleted_turns'] == 0
        assert len(first.get(history_url).json()['turns']) == chat_memory.MAX_HISTORY_TURNS
        assert first.post('/api/chat/clear', json={'article_id': a['id']}).json()['deleted_turns'] == chat_memory.MAX_HISTORY_TURNS
        assert first.get(history_url).json()['turns'] == []


def test_http_cauvery_argument_and_bjp_noncausal_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'none')
    async def idle(): await asyncio.Event().wait()
    monkeypatch.setattr(monitor, '_run', idle)
    with TestClient(app) as client:
        rss = (b'<rss><channel><item><title>Karnataka moves Supreme Court to restrain Tamil Nadu in Cauvery link project</title>'
               b'<description>Karnataka argued that Tamil Nadu cannot undertake any work on the CVG Link without clearance from the Union government</description>'
               b'<link>https://publisher.example/court</link></item>'
               b'<item><title>Tamil Nadu BJP chief detained on way to light ceremony near shrine</title>'
               b'<link>https://publisher.example/detained</link></item></channel></rss>')
        articles = core.parse_rss(rss, 'Karnataka')
        core.save_articles(articles)
        case = client.post('/api/chat', json={'article_id': articles[0]['id'],
                            'question': 'Why has Karnataka approached the Supreme Court?'})
        assert case.status_code == 200
        assert case.json()['generated_by'] == 'source_argument'
        assert 'Karnataka argued that' in case.json()['answer']
        assert case.json()['sources'][0]['url'] == 'https://publisher.example/court'
        detention = client.post('/api/chat', json={'article_id': articles[1]['id'],
                             'question': 'Why was the Tamil Nadu BJP chief detained?'})
        assert detention.status_code == 200
        assert detention.json()['generated_by'] == 'insufficient_evidence'
        assert detention.json()['evidence_status'] == 'reason_not_established_by_selected_rss'


def test_optional_rss_lookup_requires_explicit_freshness_and_caches(monkeypatch):
    monkeypatch.setenv('BHARATPULSE_ENABLE_ON_DEMAND_RSS_SEARCH', 'true')
    conditional_search._cache.clear()
    count = []
    async def fake_rss(query, language):
        count.append((query, language))
        return (b'<rss><channel><item><title>Karnataka Cauvery link project new update</title>'
                b'<description>Karnataka officials issued new comments on the Cauvery link project</description>'
                b'<link>https://provider.example/update</link></item></channel></rss>')
    monkeypatch.setattr(core, 'fetch_rss', fake_rss)
    selected = {'id': 'test-selected-conditional', 'title': 'Karnataka Cauvery link project dispute in court',
                'region': 'Karnataka', 'publisher': 'Test Publisher', 'url': 'https://example.org/original'}
    normal = asyncio.run(conditional_search.maybe_enrich('What is a river linking project?', selected, [selected]))
    assert normal == [selected] and not count
    latest = asyncio.run(conditional_search.maybe_enrich('What are the latest updates?', selected, [selected]))
    assert count and 'Karnataka' in count[0][0]
    assert len(latest) >= 1
    again = asyncio.run(conditional_search.maybe_enrich('Any recent news?', selected, [selected]))
    assert len(count) == 1 and again == latest
    monkeypatch.setenv('BHARATPULSE_ENABLE_ON_DEMAND_RSS_SEARCH', 'false')
    assert asyncio.run(conditional_search.maybe_enrich('What are the latest updates?', selected, [selected])) == [selected]

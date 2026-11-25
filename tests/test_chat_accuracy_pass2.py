"""Second-pass regression tests based on actual user audit failures.

Offline. Provider calls are mocked; these tests never use real Groq keys.
"""
from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from app import ai, chat_router_v1, chat_v07, core
from app.live import monitor
from app.main import app


def _source(title: str, url: str, *, publisher='The Hindu', description=''):
    return {'id': 'id-' + title[:12], 'title': title, 'description': description,
            'publisher': publisher, 'url': url, 'is_demo': 0, 'region': 'Tamil Nadu'}


def test_police_complaint_spelling_and_definition_are_correct(monkeypatch):
    async def must_not_use_llm(*args, **kwargs):
        raise AssertionError('The confirmed glossary definition should not need Groq')
    monkeypatch.setattr(ai, '_complete', must_not_use_llm)
    for question in ['What is a police compliant', 'What is a police complaint?',
                     'Define a police complaint']:
        assert chat_router_v1.intent(question) == 'general'
        answer = asyncio.run(chat_router_v1.general_answer(question, 'English')).lower()
        assert 'report made to the police' in answer
        assert 'not necessarily' in answer and 'police officer' in answer
        assert 'does not by itself prove' in answer


def test_source_overview_answer_keeps_selected_and_distinct_sources():
    selected = _source('Collector files complaint against Kallakurichi TVK MLA',
                       'https://www.thehindu.com/example')
    related = [
        _source('Stalin urges action against TVK MLA over messages to Collector',
                'https://news.google.com/rss/articles/abc'),
        _source('Stalin urges action against TVK MLA over messages to Collector',
                'https://www.thehindu.com/related'),
        _source('Other action against TVK MLA discussed', 'https://news.example/third'),
    ]
    indexed = chat_router_v1.dedupe_sources(selected, related)
    assert len(indexed) == 3
    assert indexed[0]['title'] == selected['title']
    assert indexed[1]['url'] == 'https://www.thehindu.com/related'
    overview, cited = chat_router_v1.source_overview(indexed)
    assert 'Collector files complaint' in overview
    assert 'messages to Collector' in overview
    assert 'Chief Minister' not in overview
    assert '[1]' in overview and '[2]' in overview
    assert len(cited) == 3


def test_unsupported_role_and_cause_never_reach_semantic_review():
    source = _source('Stalin urges Tamil Nadu government to act against Kallakurichi TVK MLA over messages to Collector',
                     'https://www.thehindu.com/news/tamil-nadu/related')
    raw = {'claims': [
        {'claim_en': 'Tamil Nadu Chief Minister Stalin urged the government to act against the TVK MLA over messages to the Collector.',
         'source': 1, 'quote': source['title']},
        {'claim_en': 'Collector filed the complaint because of the TVK MLA messages.',
         'source': 1, 'quote': source['title']},
    ]}
    approved, rejected = chat_v07.validate_candidate_claims(json.dumps(raw), [source])
    assert approved == [] and rejected == 2


def test_mixed_question_split_keeps_specific_article_question():
    question = 'What is Bali Jatra, and what does the article say President Murmu will do?'
    general, article = chat_router_v1.split_mixed(question)
    assert general == 'What is Bali Jatra?'
    assert 'President Murmu will do' in article
    assert chat_router_v1.intent(question) == 'mixed'
    assert chat_router_v1.intent('What do the available news sources say about the Collector and the TVK MLA?') == 'overview'


def test_insufficient_cause_answer_provides_context_without_inventing_reason():
    selected = _source('Collector files complaint against Kallakurichi TVK MLA',
                       'https://www.thehindu.com/example')
    related = _source('Stalin urges action against TVK MLA over messages to Collector',
                      'https://www.thehindu.com/related')
    answer, cited = chat_router_v1.limited_article_answer('Why did Collector file a complaint?', [selected, related])
    assert 'do not establish the exact reason' in answer
    assert 'messages to Collector' in answer
    assert 'does not prove the reason' in answer
    assert len(cited) == 2


def test_end_to_end_answer_modes_and_distinct_provider_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'groq')
    monkeypatch.setattr(ai, 'GROQ_API_KEY', 'mock-value-not-a-secret')
    async def idle():
        await asyncio.Event().wait()
    monkeypatch.setattr(monitor, '_run', idle)
    async def empty_claims(*args):
        return {'claims': [], 'rejected_claims': 0, 'reason': 'insufficient_evidence'}
    monkeypatch.setattr(chat_v07, 'answer_grounded', empty_claims)

    with TestClient(app) as client:
        xml = (b'<rss><channel><item><title>Collector files police complaint against Kallakurichi TVK MLA</title>'
               b'<description>Collector files complaint against MLA</description>'
               b'<link>https://www.thehindu.com/primary</link><source>The Hindu</source>'
               b'</item><item><title>Stalin urges action against Kallakurichi TVK MLA over messages to Collector</title>'
               b'<description>Stalin urges government to act over messages to Collector</description>'
               b'<link>https://www.thehindu.com/related</link><source>The Hindu</source></item>'
               b'</channel></rss>')
        records = core.parse_rss(xml, 'Tamil Nadu')
        core.save_articles(records)
        key = {'article_id': records[0]['id'], 'language': 'English'}
        general = client.post('/api/chat', json={**key, 'question': 'What is a police compliant?'})
        assert general.status_code == 200
        assert general.json()['generated_by'] == 'general_reference'
        assert 'report made to the police' in general.json()['answer']
        assert general.json()['sources'][0]['index'] == 1
        assert 'Selected RSS headline' in general.json()['answer']
        why = client.post('/api/chat', json={**key,
            'question': 'Why did the Collector file the police complaint against the MLA?'})
        assert why.status_code == 200
        assert why.json()['generated_by'] == 'insufficient_evidence'
        assert 'do not establish the exact reason' in why.json()['answer']
        assert len(why.json()['sources']) <= 2
        over = client.post('/api/chat', json={**key,
            'question': 'What do the available news sources say about the Collector and the TVK MLA?'})
        assert over.status_code == 200
        assert over.json()['generated_by'] == 'source_overview'
        assert 'Collector files police complaint' in over.json()['answer']
        assert len(over.json()['sources']) >= 1

        async def unavailable(*args):
            raise ai.LLMServiceError('Internal provider diagnostic, not for client')
        monkeypatch.setattr(chat_v07, 'answer_grounded', unavailable)
        res = client.post('/api/chat', json={**key, 'question': 'Tell me more about this event.'})
        assert res.status_code == 200
        assert res.json()['generated_by'] == 'ai_unavailable'
        assert 'Internal provider diagnostic' not in json.dumps(res.json())


def test_fir_and_tvk_are_resolved_in_the_selected_indian_news_context(monkeypatch):
    async def must_not_use_llm(*args, **kwargs):
        raise AssertionError('Known locally verified Indian-news glossary terms must not require Groq')
    monkeypatch.setattr(ai, '_complete', must_not_use_llm)
    selected_title = 'Collector files police complaint against Kallakurichi TVK MLA in Tamil Nadu'
    for question in ['What is an FIR?', 'What is F.I.R.?']:
        assert chat_router_v1.intent(question) == 'general'
        answer = asyncio.run(chat_router_v1.general_answer(question, 'English', selected_title))
        assert 'First Information Report' in answer
        assert 'First-In, First-Out' not in answer
        assert 'not automatically an FIR' in answer
    assert chat_router_v1.intent('what is TVK') == 'general'
    answer = asyncio.run(chat_router_v1.general_answer('what is TVK', 'English', selected_title))
    assert 'Tamilaga Vettri Kazhagam' in answer
    assert 'founded by Vijay' in answer
    assert 'allegation' in answer
    assert chat_router_v1.reference_definition('What is TVK?', 'What is TVK on television?') is None


def test_fir_and_tvk_endpoint_keep_article_claims_separate(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'none')
    monkeypatch.setattr(ai, 'GROQ_API_KEY', '')
    async def idle():
        await asyncio.Event().wait()
    monkeypatch.setattr(monitor, '_run', idle)
    async def must_not_use_llm(*args, **kwargs):
        raise AssertionError('No configured provider; reference definition must be standalone')
    monkeypatch.setattr(ai, '_complete', must_not_use_llm)
    with TestClient(app) as client:
        xml = (b'<rss><channel><item><title>Collector files police complaint against Kallakurichi TVK MLA in Tamil Nadu</title>'
               b'<link>https://www.thehindu.com/example</link></item></channel></rss>')
        records = core.parse_rss(xml, 'Tamil Nadu')
        core.save_articles(records)
        for question, keyword in [('What is an FIR?', 'First Information Report'),
                                  ('What is TVK?', 'Tamilaga Vettri Kazhagam')]:
            response = client.post('/api/chat', json={'article_id': records[0]['id'], 'question': question})
            assert response.status_code == 200
            body = response.json()
            assert body['generated_by'] == 'general_reference'
            assert keyword in body['answer']
            assert body['claims'] == []
            assert 'Selected RSS headline' in body['answer']

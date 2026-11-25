"""Final portfolio release acceptance checks from real user-reported AI failures.

All headline data is synthetic; no API key, network access or model completions
are needed to run these tests.  This is NOT a live Groq acceptance test.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import ai, chat_router_v1 as router, chat_v07, core
from app.live import monitor
from app.main import app


COLLECTOR = 'Collector files police complaint against Kallakurichi TVK MLA in Tamil Nadu'
BJP = 'Tamil Nadu BJP chief detained on way to light ceremony near Muslim shrine'


@pytest.mark.parametrize(('question', 'expected'), [
    ('What is a police compliant?', 'report made to the police'),
    ('What is a police complaint?', 'report made to the police'),
    ('What is FIR', 'First Information Report'),
    ('What is an FIR in this article?', 'First Information Report'),
    ('What is F.I.R.?', 'First Information Report'),
    ('Who is TVK?', 'Tamilaga Vettri Kazhagam'),
    ('Explain TVK in this article', 'Tamilaga Vettri Kazhagam'),
    ('What does TVK stand for?', 'Tamilaga Vettri Kazhagam'),
    ('What is BJP', 'Bharatiya Janata Party'),
])
def test_indian_news_context_and_typos(question, expected):
    title = BJP if 'BJP' in question else COLLECTOR
    assert router.intent(question) == 'general'
    response = asyncio.run(router.general_answer(question, 'English', title))
    assert expected in response
    assert 'Finite Impulse Response' not in response or 'filter' in question.lower()
    assert 'Chief Minister' not in response
    assert 'is an MLA named' not in response


def test_fir_has_separate_technical_meaning_when_technical_context_is_explicit():
    answer = router.reference_definition('What is an FIR filter?', 'Digital signal processing filters')
    assert 'Finite Impulse Response' in answer
    assert 'First Information Report' not in answer


def test_compound_question_stays_mixed_not_flat_general():
    for question in (
        'What is an FIR, and why did the Collector file a complaint?',
        'What is a police complaint, and what does the article say?',
        'What is Bali Jatra, and what does the article say President Murmu will do?',
    ):
        assert router.intent(question) == 'mixed'
        general, article = router.split_mixed(question)
        assert general and article and article != question


def test_why_requires_selected_headline_cause_not_travel_location():
    assert not router.selected_rss_has_cause([{'title': BJP, 'description': ''}])
    assert router.selected_rss_has_cause([{
        'title': 'Police detained a demonstrator for violating prohibitory orders',
        'description': ''
    }])


def test_headline_does_not_support_fabricated_identity_or_causality():
    source = [{'title': 'Stalin urges state government to act against MLA over messages to Collector',
               'description': '', 'publisher': 'Reporter', 'url': 'https://example.org/news'}]
    cases = {'claims': [
        {'claim_en': 'Tamil Nadu Chief Minister Stalin urged the government to act against MLA.',
         'source': 1, 'quote': source[0]['title']},
        {'claim_en': 'Police filed a complaint because the MLA sent harassing messages.',
         'source': 1, 'quote': source[0]['title']},
    ]}
    accepted, rejected = chat_v07.validate_candidate_claims(json.dumps(cases), source)
    assert accepted == [] and rejected == 2


def test_endpoint_full_regression_without_groq(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'none')
    monkeypatch.setattr(ai, 'GROQ_API_KEY', '')

    async def idle():
        await asyncio.Event().wait()

    async def no_llm(*args, **kwargs):
        raise AssertionError('Known glossary and no-cause questions must not call the AI provider')

    monkeypatch.setattr(monitor, '_run', idle)
    monkeypatch.setattr(ai, '_complete', no_llm)
    with TestClient(app) as client:
        health = client.get('/api/health')
        assert health.status_code == 200
        assert health.json()['validation_revision'] == 'v1.0-final-context-audit'
        assert client.get('/.env').status_code == 404
        assert client.get('/').headers['x-content-type-options'] == 'nosniff'
        xml = ('<rss><channel><item><title>' + COLLECTOR + '</title>'
               '<link>https://www.thehindu.com/test-collector</link></item>'
               '<item><title>' + BJP + '</title>'
               '<link>https://indianexpress.com/test-bjp</link></item>'
               '</channel></rss>').encode()
        articles = core.parse_rss(xml, 'Tamil Nadu')
        core.save_articles(articles)
        keys = {a['title']: a['id'] for a in articles}
        for question, expected in [
            ('What is FIR', 'First Information Report'),
            ('Who is TVK?', 'Tamilaga Vettri Kazhagam'),
            ('What is a police compliant', 'report made to the police'),
        ]:
            reply = client.post('/api/chat', json={'article_id': keys[COLLECTOR], 'question': question})
            assert reply.status_code == 200
            result = reply.json()
            assert result['intent'] == 'general'
            assert result['generated_by'] == 'general_reference'
            assert expected in result['answer']
        why = client.post('/api/chat', json={
            'article_id': keys[BJP],
            'question': 'Why was the Tamil Nadu BJP chief detained?',
        })
        assert why.status_code == 200
        body = why.json()
        assert body['generated_by'] == 'insufficient_evidence'
        assert body['evidence_status'] == 'reason_not_established_by_selected_rss'
        assert 'do not establish the exact reason' in body['answer']
        assert 'because he' not in body['answer'].lower()
        assert body['sources'][0]['url'] == 'https://indianexpress.com/test-bjp'
        assert 'AI UNAVAILABLE' not in body['answer']
        assert client.post('/api/chat', json={'article_id': 'missing', 'question': 'What is BJP?'}).status_code == 404


def test_public_mode_disables_ai_without_exposing_credentials(monkeypatch):
    monkeypatch.setenv('BHARATPULSE_PUBLIC_MODE', 'true')
    monkeypatch.setenv('BHARATPULSE_PUBLIC_AI_ENABLED', 'false')
    with TestClient(app) as c:
        response = c.post('/api/ai/check', json={})
        assert response.status_code == 503
        assert 'Public AI requests are disabled' in response.text
        assert 'GROQ_API_KEY' not in response.text

@pytest.mark.parametrize('question', [
    'What is BJP doing?',
    'What is the police complaint about?',
    'Who is TVK MLA?',
])
def test_followup_action_questions_are_not_mistaken_for_definitions(question):
    assert router.intent(question) == 'article'

"""Regression checks for real-world contextual acronyms and why questions.

No Groq/network calls. Synthetic RSS articles are used to check that the
assistant never manufactures a reason from event-location phrasing.
"""
import asyncio

from fastapi.testclient import TestClient

from app import ai, core, chat_router_v1, chat_v07
from app.live import monitor
from app.main import app


def test_exact_acronym_questions_are_contextual_definitions_without_provider(monkeypatch):
    async def unavailable(*args, **kwargs):
        raise AssertionError('Curated glossary must not call an LLM')
    monkeypatch.setattr(ai, '_complete', unavailable)
    title = 'Collector files police complaint against Kallakurichi TVK MLA in Tamil Nadu'
    for question in ('What is FIR', 'What is an FIR?', 'what is F.I.R'):
        assert chat_router_v1.intent(question) == 'general'
        answer = asyncio.run(chat_router_v1.general_answer(question, 'English', title))
        assert 'First Information Report' in answer
        assert 'Finite Impulse Response' not in answer
    for question in ('who is TVK', 'What is TVK?', 'What does TVK stand for?'):
        assert chat_router_v1.intent(question) == 'general'
        answer = asyncio.run(chat_router_v1.general_answer(question, 'English', title))
        assert 'Tamilaga Vettri Kazhagam' in answer
        assert 'MLA named' not in answer
    assert chat_router_v1.intent('Who is this MLA?') == 'article'


def test_causal_detection_distinguishes_event_from_reason():
    title = 'Tamil Nadu BJP chief detained on way to light ceremony near Muslim shrine'
    assert chat_router_v1.question_requires_cause('Why was the Tamil Nadu BJP chief detained?')
    assert not chat_router_v1.selected_rss_has_cause([{'title': title, 'description': title}])
    explicit = 'Police detained protester for violating prohibitory orders'
    assert chat_router_v1.selected_rss_has_cause([{'title': explicit, 'description': ''}])


def test_endpoint_specific_groq_context_and_causal_abstention(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'groq')
    monkeypatch.setattr(ai, 'GROQ_API_KEY', 'mock-non-secret')

    async def idle():
        await asyncio.Event().wait()

    async def fake_complete(*args, **kwargs):
        raise AssertionError('This question must not need the Groq network')

    async def fake_grounded(*args, **kwargs):
        raise AssertionError('No causal RSS evidence: do not call grounded LLM')

    monkeypatch.setattr(monitor, '_run', idle)
    monkeypatch.setattr(ai, '_complete', fake_complete)
    monkeypatch.setattr(chat_v07, 'answer_grounded', fake_grounded)

    with TestClient(app) as client:
        assert client.get('/api/health').json()['chat_revision'] == 'v1.0-pass3-context-why'
        b = core.parse_rss(
            b'<rss><channel><item>'
            b'<title>Collector files police complaint against Kallakurichi TVK MLA in Tamil Nadu</title>'
            b'<link>https://publisher.example/1</link></item></channel></rss>',
            'Tamil Nadu')
        core.save_articles(b)
        for question, phrase in [('What is FIR', 'First Information Report'),
                                 ('who is TVK', 'Tamilaga Vettri Kazhagam'),
                                 ('What is a police compliant', 'report made to the police')]:
            response = client.post('/api/chat', json={'article_id': b[0]['id'], 'question': question})
            assert response.status_code == 200
            payload = response.json()
            assert payload['generated_by'] == 'general_reference'
            assert phrase in payload['answer']

        news = core.parse_rss(
            b'<rss><channel><item>'
            b'<title>Tamil Nadu BJP chief detained on way to light ceremony near Muslim shrine</title>'
            b'<link>https://publisher.example/2</link></item></channel></rss>',
            'Tamil Nadu')
        core.save_articles(news)
        response = client.post('/api/chat', json={
            'article_id': news[0]['id'],
            'question': 'Why was the Tamil Nadu BJP chief detained?',
        })
        assert response.status_code == 200
        result = response.json()
        assert result['generated_by'] == 'insufficient_evidence'
        assert 'do not establish the exact reason' in result['answer']
        assert 'on way to light ceremony' in result['answer']
        assert 'because the chief' not in result['answer']
        assert result['evidence_status'] == 'reason_not_established_by_selected_rss'
        assert result['claims'] == []

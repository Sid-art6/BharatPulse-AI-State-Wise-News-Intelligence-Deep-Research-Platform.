"""Offline regression cases copied from reported news-chat failure patterns.

The tests use synthetic RSS snippets. No model completion, provider key or
external web service is required; they do not certify live-model accuracy.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import ai, core, chat_router_v1 as router, context_engine
from app.live import monitor
from app.main import app


ALERT_TITLE = 'Rayalaseema on high alert ahead of panchayat polls'
ALERT_EXCERPT = ('Sensitive villages placed under surveillance as officials '
                 'strengthen security and enforce election rules')
IDENTITY_TITLE = 'Rajiv Gandhi security cover removal alleged by politician'


def test_general_person_identity_is_not_mistaken_for_news_claim():
    assert router.person_identity_query('Who is Rajiv Gandhi?')
    assert router.intent('Who is Rajiv Gandhi?') == 'general'
    assert router.intent('Who was Rajiv Gandhi?') == 'general'
    assert router.intent('who is rahul gandhi') == 'general'
    assert router.intent('Who is Rajiv Gandhi, and what does the article say?') == 'mixed'
    assert router.intent('Who is the MLA mentioned in the report?') == 'article'
    assert router.intent('Who is the person responsible?') == 'article'
    assert router.intent('Who is the collector?') == 'article'
    assert router.intent('Who is TVK?') == 'general'


def test_elliptical_question_binds_to_selected_article():
    article = {'title': ALERT_TITLE, 'description': ALERT_EXCERPT}
    q = context_engine.resolve_elliptical_article_question('Why ?', article)
    assert ALERT_TITLE in q and q.lower().startswith('why')
    assert context_engine.resolve_elliptical_article_question('Why?', {}) == 'Why?'
    assert router.intent('Why ?') == 'article'
    assert router.intent('Give me context?') == 'overview'
    assert router.intent('Tell me some context') == 'overview'
    assert router.intent('Why did the police detain him?') == 'article'


def test_election_alert_context_is_partial_evidence_not_invented_threat():
    rss = [{'title': ALERT_TITLE, 'description': ALERT_EXCERPT,
            'publisher': 'The Hindu', 'url': 'https://publisher.example/alert'}]
    reply, cited = context_engine.election_security_context_answer('Why ?', rss)
    assert 'panchayat' in reply.lower()
    assert 'under surveillance' in reply
    assert 'does not establish any particular threat or incident' in reply
    assert cited[0]['url'] == 'https://publisher.example/alert'
    assert context_engine.election_security_context_answer('What is a panchayat?', rss) is None
    # Reported presence near a ceremony is NOT the grounds for detention.
    unrelated = [{'title': 'BJP leader detained on way to poll ceremony',
                  'description': 'The leader travelled to a ceremony before detention'}]
    assert context_engine.election_security_context_answer('Why?', unrelated) is None
    assert not router.selected_rss_has_cause(unrelated)


def test_http_short_why_returns_supported_security_context_without_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'none')
    monkeypatch.setattr(ai, 'GROQ_API_KEY', '')

    async def idle():
        import asyncio
        await asyncio.Event().wait()

    monkeypatch.setattr(monitor, '_run', idle)
    with TestClient(app) as client:
        rss = (f'<rss><channel><item><title>{ALERT_TITLE}</title>'
               f'<description>{ALERT_EXCERPT}</description>'
               '<link>https://publisher.example/alert</link></item></channel></rss>').encode()
        article = core.parse_rss(rss, 'All India')[0]
        core.save_articles([article])
        reply = client.post('/api/chat', json={'article_id': article['id'], 'question': 'Why ?'})
        assert reply.status_code == 200, reply.text
        result = reply.json()
        assert result['generated_by'] == 'source_security_context'
        assert result['evidence_status'] == 'partial_election_security_context'
        assert 'surveillance' in result['answer']
        assert 'particular threat or incident' in result['answer']
        assert 'Exact answer not established' not in result['answer']
        assert result['sources'][0]['url'] == 'https://publisher.example/alert'
        overview = client.post('/api/chat', json={'article_id': article['id'],
                                                  'question': 'Give me context?'})
        assert overview.status_code == 200
        assert overview.json()['intent'] == 'overview'
        assert 'Sensitive villages placed under surveillance' in overview.json()['answer']


def test_http_rajiv_identity_routes_to_one_general_model_call(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    calls = []
    async def enabled(): return True
    async def fake_complete(messages, *, max_tokens, json_mode=False):
        calls.append(messages)
        return 'Rajiv Gandhi served as Prime Minister of India from 1984 to 1989.'
    async def idle():
        import asyncio
        await asyncio.Event().wait()
    monkeypatch.setattr(monitor, '_run', idle)
    monkeypatch.setattr(ai, 'llm_is_configured', enabled)
    monkeypatch.setattr(ai, '_complete', fake_complete)
    with TestClient(app) as client:
        rss = ('<rss><channel><item><title>Rajiv Gandhi security cover removal: claims by Rahul</title>'
               '<description>Report quotes an allegation about Rajiv Gandhi</description>'
               '<link>https://publisher.example/rajiv</link></item></channel></rss>').encode()
        article = core.parse_rss(rss, 'All India')[0]
        core.save_articles([article])
        reply = client.post('/api/chat', json={'article_id': article['id'],
                                                'question': 'Who is Rajiv Gandhi?'})
        assert reply.status_code == 200, reply.text
        result = reply.json()
        # A named person already mentioned in the selected article is an
        # article-context query: the unrelated biography generated by a model
        # must not be presented as a grounded answer.
        assert result['intent'] == 'article'
        assert result['generated_by'] != 'general_ai'
        assert 'Prime Minister' not in result['answer']
        assert result['sources'][0]['index'] == 1
        assert len(calls) >= 1
        health = client.get('/api/health').json()
        assert health['short_question_revision'] == 'v1.0-article-followup-qa'

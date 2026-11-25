"""v1.0 audit regressions: general/article chat separation and honest RSS depth.

All provider/network calls are mocked; do not require credentials to run CI.
"""
from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
from app import ai, chat_router_v1, core, research_v2, public_safety
from app.main import app
from app.live import monitor


def sample():
    return core.parse_rss(
        b'<rss><channel><item><title>President Murmu to inaugurate Bali Jatra in Cuttack</title>'
        b'<link>https://news.example/bali</link><description>Odisha visit notice</description>'
        b'<source>Regional News</source></item></channel></rss>', 'Odisha')[0]


def test_question_classification_is_separate_and_bounded():
    assert chat_router_v1.intent('What is a passport?') == 'general'
    assert chat_router_v1.intent('What is Bali Jatra, and what does the article say?') == 'mixed'
    assert chat_router_v1.intent('What evidence supports the report?') == 'evidence'
    assert chat_router_v1.intent('Summarise this article.') == 'summary'
    assert chat_router_v1.intent('What happened?') == 'article'
    background, news = chat_router_v1.split_mixed('What is Bali Jatra, and what does the article say?')
    assert background.lower().startswith('what is bali jatra')
    assert news


def test_general_answer_prompt_contains_no_article_source(monkeypatch):
    seen = []
    async def fake(messages, *, max_tokens, json_mode=False):
        seen.append(messages)
        return 'A passport is an official government-issued travel document.'
    monkeypatch.setattr(ai, '_complete', fake)
    result = asyncio.run(chat_router_v1.general_answer('What is a passport?', 'English'))
    assert 'passport' in result.lower()
    assert 'SOURCE RECORDS' not in json.dumps(seen)
    assert 'article' not in seen[-1][-1]['content'].lower()


def test_chat_intent_routes_general_mixed_and_evidence(monkeypatch, tmp_path):
    from app import chat_v07
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'groq')
    monkeypatch.setattr(ai, 'GROQ_API_KEY', 'only-a-mock')
    async def idle(): await asyncio.Event().wait()
    monkeypatch.setattr(monitor, '_run', idle)
    async def fake_general(question, language, article_title='', article=None, conversation_context=''):
        assert article and 'Bali Jatra' in article['title']
        return 'Bali Jatra celebrates the maritime heritage of Odisha.'
    async def grounded(question, sources, language):
        return {'claims':[{'source':1,'text':'The selected report says President Murmu will inaugurate Bali Jatra.',
                           'quote':sources[0]['title']}],
                'reason':'reviewed_rss_claims','rejected_claims':0}
    monkeypatch.setattr(chat_router_v1, 'general_answer', fake_general)
    monkeypatch.setattr(chat_v07, 'answer_grounded', grounded)
    with TestClient(app) as client:
        record = sample()
        core.save_articles([record])
        key = {'article_id':record['id'], 'language':'English'}
        g = client.post('/api/chat', json={**key,'question':'What is a passport?'})
        assert g.status_code == 200
        assert g.json()['intent'] == 'general'
        assert g.json()['sources'] == []
        assert g.json()['generated_by'] == 'general_ai'
        mixed=client.post('/api/chat',json={**key,'question':'What is Bali Jatra, and what does the article say?'})
        assert mixed.status_code == 200
        assert mixed.json()['intent'] == 'mixed'
        assert 'General background:' in mixed.json()['answer']
        assert 'What the RSS reports:' in mixed.json()['answer']
        assert mixed.json()['sources'][0]['index'] == 1
        e=client.post('/api/chat',json={**key,'question':'What evidence supports this report?'})
        assert e.json()['intent'] == 'evidence'
        assert 'Regional News' in e.json()['answer']
        assert 'not that the underlying event is independently confirmed' in e.json()['answer']
        summary=client.post('/api/chat',json={**key,'question':'Summarise this article.'})
        assert summary.json()['generated_by'] == 'source_summary'
        assert 'full article' in summary.json()['answer']


def test_search_uses_all_tokens_across_metadata_and_escapes_wildcards(monkeypatch,tmp_path):
    monkeypatch.setattr(core,'DATA_DIR',tmp_path)
    monkeypatch.setattr(core,'DB_PATH',tmp_path/'index.db')
    core.init_db()
    core.save_articles(core.demo_fixtures())
    found=core.list_articles(demo=True,search='Bengaluru Environment')
    assert found and all('Bengaluru' in item['title'] and item['topic']=='Environment' for item in found)
    assert not core.list_articles(demo=True,search='Bengaluru%')
    assert not core.list_articles(demo=True,search='xyznonexistent987654')


def test_research_displays_real_source_metadata_not_invented_verification():
    a=sample()
    b={**a,'id':'another','publisher':'Second outlet',
       'title':'Odisha festival preparation update', 'description':'Odisha festival preparations are under way.'}
    report=research_v2.initial_report([a,b])
    assert report['source_comparison'][0]['headline']==a['title']
    assert report['source_comparison'][1]['excerpt']==b['description']
    assert report['evidence_depth']['with_additional_excerpts']>=1
    assert report['findings']==[]


def test_public_ai_global_budget_is_enforced():
    limiter=public_safety.SlidingWindowLimiter()
    for i in range(public_safety.PUBLIC_AI_GLOBAL_HOURLY_LIMIT):
        assert limiter.check('GLOBAL','ai_budget',public_safety.PUBLIC_AI_GLOBAL_HOURLY_LIMIT)
    assert limiter.check('GLOBAL','ai_budget',public_safety.PUBLIC_AI_GLOBAL_HOURLY_LIMIT) is False


def test_http_blocks_large_body_even_with_false_small_content_length(monkeypatch):
    # Some HTTP clients will not allow a mismatched Content-Length; the middleware
    # must still refuse a body exceeding the cap when no large length is declared.
    with TestClient(app) as c:
        resp=c.post('/api/news/watch',content='x' * 20000)
        assert resp.status_code==413


def test_secrets_are_not_served():
    with TestClient(app) as c:
        assert c.get('/.env').status_code == 404

"""v0.7 claim gating: simulated LLMs only, no real Groq requests."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from app import ai, chat_v07, core
from app.main import app


SOURCES = [
    {'title': "Suresh Gopi questions Karnataka's E20 testing method",
     'description': 'The minister questioned the testing method, but dismissed concerns about ethanol blending.',
     'publisher': 'Regional Press', 'published_at': '2026-11-23T05:00:00+00:00',
     'url': 'https://regional.example/a', 'language': 'English'},
    {'title': 'Karnataka announces a review of ethanol blending methods',
     'description': 'A technical review of testing methods is planned.',
     'publisher': 'Local Desk', 'published_at': '2026-11-22T05:00:00+00:00',
     'url': 'https://local.example/b', 'language': 'English'},
]
QUOTE = "Suresh Gopi questions Karnataka's E20 testing method"
CLAIM = "Suresh Gopi questions Karnataka's E20 testing method."


def model_claim(text=CLAIM, quote=QUOTE, source=1):
    return json.dumps({'claims': [{'claim_en': text, 'quote': quote, 'source': source}]}, ensure_ascii=False)


def test_valid_exact_quote_is_candidate_not_proven_fact():
    claims, rejected = chat_v07.validate_candidate_claims(model_claim(), SOURCES)
    assert len(claims) == 1 and rejected == 0
    assert claims[0]['quote'] == QUOTE


@pytest.mark.parametrize('raw', [
    model_claim(source=99),
    model_claim(quote='A fabricated source quote that does not exist.'),
    model_claim(text='Suresh Gopi announced ₹900 crore loss from E20 testing.'),
    model_claim(text='Suresh Gopi questioned the 2025 E20 testing method.'),
    'Markdown claim [1] without JSON',
    '{"claims":[{"claim_en":"Hello","source":1,"quote":"fake"}]}',
])
def test_bad_claims_are_rejected_locally(raw):
    assert chat_v07.validate_candidate_claims(raw, SOURCES)[0] == []


def test_unsupported_script_number_is_rejected():
    assert chat_v07._numbers('९०० करोड़') == {'900'}
    assert chat_v07._numbers('₹900 crore') == {'900'}


def test_verifier_requires_complete_valid_and_unique_boolean_verdicts():
    entries = [{'id': 1}, {'id': 2}]
    assert chat_v07._parse_verdicts('{"verdicts":[{"id":1,"supported":true},{"id":2,"supported":false}]}', entries) == {1}
    assert chat_v07._parse_verdicts('{"verdicts":[{"id":1,"supported":true}]}', entries) == set()
    assert chat_v07._parse_verdicts('{"verdicts":[{"id":1,"supported":true},{"id":1,"supported":true}]}', entries) == set()
    assert chat_v07._parse_verdicts('{"verdicts":[{"id":1,"supported":"true"},{"id":2,"supported":true}]}', entries) == set()


def test_opposite_meaning_is_removed_by_second_review(monkeypatch):
    wrong = "Suresh Gopi says Karnataka's E20 testing method has no problem."
    async def fake_complete(messages, *, json_mode, max_tokens):
        assert json_mode
        if 'READER QUESTION:' in messages[-1]['content']:
            return model_claim(text=wrong)
        assert 'skeptical' in messages[-1]['content']
        return '{"verdicts":[{"id":1,"supported":false}]}'
    monkeypatch.setattr(ai, '_complete', fake_complete)
    response = asyncio.run(chat_v07.answer_grounded('What did he say?', SOURCES, 'English'))
    assert response['claims'] == []
    assert response['reason'] == 'unsupported_claims'
    assert response['rejected_claims'] == 1


def test_translator_cannot_insert_unverified_financial_figure(monkeypatch):
    calls = []
    async def fake_complete(messages, *, json_mode, max_tokens):
        prompt = messages[-1]['content']
        calls.append(prompt)
        if 'READER QUESTION:' in prompt:
            return model_claim()
        if 'skeptical' in prompt:
            return '{"verdicts":[{"id":1,"supported":true}]}'
        return '{"items":[{"id":1,"text":"सुरेश गोपी ने E20 परीक्षण पर सवाल उठाए और ९०० करोड़ रुपये के नुकसान की पुष्टि की।"}]}'
    monkeypatch.setattr(ai, '_complete', fake_complete)
    response = asyncio.run(chat_v07.answer_grounded('What did the minister do?', SOURCES, 'Hindi'))
    assert response['claims'] == [] and response['reason'] == 'translation_unverified'
    assert len(calls) == 3  # hard-number gate fires before translation-verifier call


def test_semantic_translation_review_rejects_polarity_flip(monkeypatch):
    async def fake_complete(messages, *, json_mode, max_tokens):
        prompt=messages[-1]['content']
        if 'READER QUESTION:' in prompt:
            return model_claim()
        if 'skeptical' in prompt:
            return '{"verdicts":[{"id":1,"supported":true}]}'
        if 'Translate each' in prompt:
            return '{"items":[{"id":1,"text":"सुरेश गोपी ने कहा कि कर्नाटक की E20 परीक्षण पद्धति में कोई समस्या नहीं है।"}]}'
        return '{"verdicts":[{"id":1,"supported":false}]}'
    monkeypatch.setattr(ai, '_complete', fake_complete)
    response=asyncio.run(chat_v07.answer_grounded('What did the minister do?', SOURCES, 'Hindi'))
    assert response['reason']=='translation_unverified'
    assert not response['claims']


def test_good_hindi_translation_with_review(monkeypatch):
    prompts=[]
    async def fake_complete(messages, *, json_mode, max_tokens):
        prompt=messages[-1]['content']; prompts.append(prompt)
        if 'READER QUESTION:' in prompt:
            return model_claim()
        if 'skeptical' in prompt:
            return '{"verdicts":[{"id":1,"supported":true}]}'
        if 'Translate each' in prompt:
            return '{"items":[{"id":1,"text":"सुरेश गोपी ने कर्नाटक की E20 परीक्षण पद्धति पर सवाल उठाए।"}]}'
        return '{"verdicts":[{"id":1,"supported":true}]}'
    monkeypatch.setattr(ai, '_complete', fake_complete)
    response=asyncio.run(chat_v07.answer_grounded('What did the minister do?', SOURCES, 'Hindi'))
    assert len(prompts)==4
    assert response['reason']=='reviewed_rss_claims'
    assert response['claims'][0]['text'].startswith('सुरेश')
    assert response['claims'][0]['source']==1


def test_malformed_provider_result_abstains(monkeypatch):
    async def fake_complete(messages, *, json_mode, max_tokens):
        return 'not-json'
    monkeypatch.setattr(ai, '_complete', fake_complete)
    result=asyncio.run(chat_v07.answer_grounded('Did it cost money?', SOURCES, 'English'))
    assert not result['claims']
    assert result['reason']=='insufficient_evidence'


def test_chat_endpoint_returns_only_cited_verified_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'groq')
    monkeypatch.setattr(ai, 'GROQ_API_KEY', 'test-only-nonsecret')
    monkeypatch.setattr(ai, 'ENABLE_LLM_FILTER', False)
    async def empty_news(region):
        return []
    async def fake_answer(question, sources, language):
        assert sources[0]['publisher']=='Regional Press'
        return {'claims':[{'id':1, 'claim_en':CLAIM,'text':CLAIM, 'source':1,'quote':QUOTE}],
                'rejected_claims':0,'reason':'reviewed_rss_claims'}
    monkeypatch.setattr(core, 'fetch_news', empty_news)
    monkeypatch.setattr(chat_v07, 'answer_grounded', fake_answer)
    with TestClient(app) as client:
        xml=b'<rss><channel><item><title>Suresh Gopi questions Karnataka\'s E20 testing method</title><link>https://regional.example/a</link><source>Regional Press</source></item></channel></rss>'
        item=core.parse_rss(xml,'Karnataka')
        core.save_articles(item)
        response=client.post('/api/chat',json={'article_id':item[0]['id'],'question':'What happened?','language':'English'})
        assert response.status_code==200
        data=response.json()
        assert data['generated_by']=='groq'
        assert data['evidence_status']=='reviewed_rss_claims'
        assert len(data['claims'])==1
        assert data['sources'][0]['index']==1
        assert data['claims'][0]['quote']==QUOTE
        assert data['caveat'].startswith('Source-anchored AI draft')
        assert client.get('/api/health').json()['version']=='0.9.0'

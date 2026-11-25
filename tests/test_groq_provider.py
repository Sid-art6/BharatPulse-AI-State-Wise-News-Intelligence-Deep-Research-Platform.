"""Offline Groq adapter tests: no real API key or network is needed."""
import asyncio
import json

import httpx
import pytest

from app import ai, core, chat_v07


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'groq')
    monkeypatch.setattr(ai, 'GROQ_API_KEY', 'test-only-no-real-key')
    monkeypatch.setattr(ai, 'GROQ_MODEL', 'openai/gpt-oss-20b')
    monkeypatch.setattr(ai, 'ENABLE_LLM_FILTER', True)


def mock_httpx_client(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(ai.httpx, 'AsyncClient', lambda *a, **kw: original(transport=httpx.MockTransport(handler), **kw))


def test_groq_request_does_not_expose_api_key(monkeypatch):
    def handler(request):
        assert request.url == 'https://api.groq.com/openai/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer test-only-no-real-key'
        sent = json.loads(request.content)
        assert sent['model'] == 'openai/gpt-oss-20b'
        assert sent['messages'][0]['role'] == 'system'
        assert sent['response_format'] == {'type': 'json_object'}
        return httpx.Response(200, json={'choices':[{'message':{'content':'{"items":[]}'}}]})
    mock_httpx_client(monkeypatch, handler)
    text = asyncio.run(ai._complete([{'role':'system','content':'Test'}], json_mode=True))
    assert json.loads(text) == {'items': []}


def test_groq_401_is_safe_and_not_leaked(monkeypatch):
    mock_httpx_client(monkeypatch, lambda request: httpx.Response(401, json={'error':{'message':'API key not valid'}}))
    with pytest.raises(ai.LLMServiceError, match=r'401') as caught:
        asyncio.run(ai._complete([{'role':'user','content':'Ping'}]))
    assert 'test-only-no-real-key' not in str(caught.value)


def test_groq_429_is_safe(monkeypatch):
    mock_httpx_client(monkeypatch, lambda request: httpx.Response(429, json={'error': 'limit'}))
    with pytest.raises(ai.LLMServiceError, match=r'429'):
        asyncio.run(ai._complete([{'role':'user','content':'Ping'}]))


def test_placeholder_key_never_counts_as_configured(monkeypatch):
    monkeypatch.setattr(ai, 'GROQ_API_KEY', 'PASTE_YOUR_GROQ_KEY_HERE')
    assert ai.active_provider() == 'none'
    assert asyncio.run(ai.llm_is_configured()) is False


def test_groq_relevance_filter_and_multilingual_preview(monkeypatch):
    async def fake_complete(messages, *, json_mode, max_tokens):
        assert json_mode is True
        prompt = messages[-1]['content']
        if 'relevance filter' in prompt:
            return json.dumps({'items':[{'id':'one','keep':True}, {'id':'two','keep':False}]})
        return json.dumps({'items':[{'id':'three','summary_en':'A road was closed in Karnataka.'}]})
    monkeypatch.setattr(ai, '_complete', fake_complete)
    rows = [
        {'id':'one','title':'Karnataka transport announcement','description':'New plan announced'},
        {'id':'two','title':'Spam advertisement','description':'Buy now'},
    ]
    selected, mode = asyncio.run(ai.optional_llm_filter(rows))
    assert [r['id'] for r in selected] == ['one']
    assert mode == 'groq_filtered_first_2'
    native = [{'id':'three','title':'ಕರ್ನಾಟಕ ರಸ್ತೆ ಸುದ್ದಿ','description':'ಕರ್ನಾಟಕದಲ್ಲಿ ರಸ್ತೆ ಮುಚ್ಚಲಾಯಿತು','language':'Kannada','is_demo':0}]
    assert asyncio.run(ai.english_previews(native)) == {'three':'A road was closed in Karnataka.'}


def test_rejected_headlines_do_not_refilter(monkeypatch, tmp_path):
    monkeypatch.setattr(core,'DATA_DIR',tmp_path)
    monkeypatch.setattr(core,'DB_PATH',tmp_path / 'test.db')
    core.init_db()
    xml = b'<rss><channel><item><title>Karnataka transport update</title><link>https://news.example/1</link><description>Update</description></item><item><title>Spam advertisement</title><link>https://news.example/2</link><description>Sale</description></item></channel></rss>'
    incoming = core.parse_rss(xml, 'Karnataka')
    assert len(core.unseen_articles(incoming)) == 2
    core.remember_rejected_headlines(incoming, incoming[:1])
    core.save_articles(incoming[:1])
    assert core.unseen_articles(incoming) == []


def test_chat_uses_groq_provider_with_cited_evidence(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    monkeypatch.setattr(ai, 'ENABLE_LLM_FILTER', False)
    async def empty_news(region):
        return []
    monkeypatch.setattr(core, 'fetch_news', empty_news)
    async def answer(question, sources, language):
        assert language == 'Hindi'
        assert 'article report' in question.lower()
        assert sources[0]['publisher'] == 'Example Paper'
        return {'claims':[{'id':1,'text':'कर्नाटक परिवहन घोषणा प्रकाशित हुई।', 'claim_en':'Karnataka transport announcement was published.',
                          'source':1,'quote':'Karnataka transport announcement'}],
                'rejected_claims':0, 'reason':'reviewed_rss_claims'}
    monkeypatch.setattr(chat_v07, 'answer_grounded', answer)
    with TestClient(app) as client:
        source = core.parse_rss(b'<rss><channel><item><title>Karnataka transport announcement</title><link>https://news.example/rail</link><description>A transport announcement was published.</description><source>Example Paper</source></item></channel></rss>', 'Karnataka')
        core.save_articles(source)
        response = client.post('/api/chat', json={
            'article_id': source[0]['id'], 'question': 'What happened according to the article report?', 'language': 'Hindi',
        })
        assert response.status_code == 200
        data = response.json()
        assert data['generated_by'] == 'groq'
        assert '[1]' in data['answer']
        assert data['sources'][0]['publisher'] == 'Example Paper'
        metadata = client.get('/api/meta').json()
        assert metadata['llm_provider'] == 'groq'
        assert metadata['llm_configured'] is True
        assert 'GROQ_API_KEY' not in json.dumps(metadata)


def test_invalid_model_citation_is_rejected(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    async def empty_news(region):
        return []
    monkeypatch.setattr(core, 'fetch_news', empty_news)
    async def false_citation(question, sources, language):
        return {'claims':[], 'rejected_claims':1, 'reason':'unsupported_claims'}
    monkeypatch.setattr(chat_v07, 'answer_grounded', false_citation)
    with TestClient(app) as client:
        source = core.parse_rss(b'<rss><channel><item><title>Kerala coastal protection update</title><link>https://news.example/coast</link><description>Kerala coastal project proposed.</description><source>Test Publisher</source></item></channel></rss>', 'Kerala')
        core.save_articles(source)
        response = client.post('/api/chat', json={
            'article_id': source[0]['id'], 'question': 'What happened?',
        })
        data = response.json()
        assert data['generated_by'] == 'insufficient_evidence'
        assert 'An unsupported claim' not in data['answer']

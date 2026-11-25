"""v1.4 article preloading is tested offline; never contacts publishers or Groq."""
import asyncio
import json

from fastapi.testclient import TestClient

from app import article_context, core, chat_v07, ai
from app.main import app

TITLE = 'City council approves library improvement programme for local schools'
URL = 'https://www.thehindu.com/news/example/library-programme.html'
BODY = (
    'The city council approved the library improvement programme after a public consultation. '
    'The programme allocates funds to upgrade school libraries and provides new books for students. '
    'Officials stated that the first phase will begin after the annual budget is approved. '
    'The council discussed teacher training, access to books and improvements in reading facilities. '
    'This statement describes the decision taken during a council meeting. '
    'The financial allocation was not published in the announcement. '
) * 4


def test_safe_publisher_url_restrictions(monkeypatch):
    assert article_context._valid_url('http://www.thehindu.com/story') is False
    assert article_context._valid_url('https://127.0.0.1/private') is False
    assert article_context._valid_url('https://localhost/private') is False
    assert article_context._valid_url('https://unknown-example.attacker.net/private') is False
    monkeypatch.setattr(article_context, '_public_hostname', lambda host: host == 'www.thehindu.com')
    assert article_context._valid_url(URL)
    assert article_context._valid_url('https://www.thehindu.com:8443/private') is False
    assert article_context._valid_url('https://user:pass@www.thehindu.com/path') is False


def test_extract_real_article_body_not_navigation():
    document = ('<html><head><meta property="og:title" content="'+TITLE+'"></head>'
                '<body><nav><p>Hundreds of unrelated site navigation words</p></nav>'
                '<article><p>'+BODY.replace('. ', '.</p><p>')+'</p></article>'
                '<footer><p>Subscribe for more stories</p></footer></body></html>')
    title, body = article_context._select_body(document)
    assert title == TITLE
    assert 'library improvement programme' in body
    assert 'unrelated site navigation' not in body
    assert 'Subscribe for more' not in body


def test_json_ld_and_long_passages():
    html = '<html><script type="application/ld+json">'+json.dumps({'@type': 'NewsArticle',
             'articleBody': BODY})+'</script><title>'+TITLE+'</title></html>'
    _, body = article_context._select_body(html)
    assert len(body) > 500
    excerpts = article_context.relevant_passages(body, 'How will the library programme be funded?')
    assert 'financial allocation was not published' in excerpts
    assert 100 < len(excerpts) <= 6500


def test_cache_hit_and_article_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path/'news.db')
    core.init_db(); article_context.init_db()
    row = {'id': 'story-1', 'title': TITLE, 'url': URL, 'description': '', 'publisher': 'The Hindu'}
    calls=[]
    async def fake_fetch(url):
        calls.append(url)
        return URL, ('<html><head><meta property="og:title" content="'+TITLE+'"></head>'
                     '<body><article><p>'+BODY.replace('. ', '.</p><p>')+'</p></article></body></html>')
    monkeypatch.setattr(article_context, '_fetch_publisher_page', fake_fetch)

    async def scenario():
        first=await article_context.ensure(row)
        second=await article_context.ensure(row)
        return first, second
    first, second=asyncio.run(scenario())
    assert first['status']=='ready' and second['status']=='ready'
    assert calls==[URL]
    attached=article_context.attach(row,first,'What did the council approve?')
    assert attached['evidence_origin']=='publisher_article'
    assert 'The city council approved' in attached['description']
    assert attached['url']==URL
    assert article_context.get_cached('story-2')=={}


def test_denied_or_mismatched_page_never_becomes_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(core,'DATA_DIR',tmp_path)
    monkeypatch.setattr(core,'DB_PATH',tmp_path/'news.db')
    core.init_db();article_context.init_db()
    row={'id':'bad','title':TITLE,'url':URL,'description':'Existing RSS excerpt','publisher':'The Hindu'}
    async def denied(_url):
        raise ValueError('publisher_access_restricted')
    monkeypatch.setattr(article_context,'_fetch_publisher_page',denied)
    result=asyncio.run(article_context._retrieve(row))
    assert result['status']=='limited'
    assert article_context.attach(row,result,'question') is row
    async def unrelated(_url):
        return URL, '<html><head><title>Unrelated report about football tournaments</title></head><article><p>'+('International teams played a football game in the championship. '*15)+'</p></article></html>'
    monkeypatch.setattr(article_context,'_fetch_publisher_page',unrelated)
    result=asyncio.run(article_context._retrieve(row))
    assert result['status']=='limited'
    assert result['failure_code']=='publisher_story_mismatch'


def test_api_preload_keeps_text_hidden_but_chat_uses_it(monkeypatch, tmp_path):
    monkeypatch.setattr(core,'DATA_DIR',tmp_path)
    monkeypatch.setattr(core,'DB_PATH',tmp_path/'news.db')
    async def idle():
        await asyncio.Event().wait()
    from app.live import monitor
    monkeypatch.setattr(monitor,'_run',idle)
    async def fake_fetch(_url):
        return URL, ('<html><head><meta property="og:title" content="'+TITLE+'"></head>'
                     '<body><article><p>'+BODY.replace('. ', '.</p><p>')+'</p></article></body></html>')
    monkeypatch.setattr(article_context,'_fetch_publisher_page',fake_fetch)
    async def fake_grounded(question,sources,language):
        assert sources[0]['evidence_origin']=='publisher_article'
        assert 'The city council approved' in sources[0]['description']
        return {'claims':[{'id':1,'claim_en':'The city council approved the library improvement programme.',
                 'text':'The city council approved the library improvement programme.','source':1,
                 'quote':'The city council approved the library improvement programme after a public consultation.'}],
                'rejected_claims':0,'reason':'reviewed_article_claims'}
    monkeypatch.setattr(chat_v07,'answer_grounded',fake_grounded)
    async def llm_ready():return True
    monkeypatch.setattr(ai,'llm_is_configured',llm_ready)
    monkeypatch.setattr(ai,'active_provider',lambda: 'groq')
    with TestClient(app) as client:
        article=core.parse_rss(('<rss><channel><item><title>'+TITLE+'</title><link>'+URL+'</link>'
            '<source>The Hindu</source></item></channel></rss>').encode(),'Karnataka')[0]
        core.save_articles([article])
        start=client.post('/api/article-context/'+article['id']+'/prepare')
        assert start.status_code==200
        assert start.json()['status'] in {'loading','ready'}
        import time
        for i in range(60):
            status=client.get('/api/article-context/'+article['id']).json()
            if status['status']=='ready':break
            time.sleep(.03)
        assert status['status']=='ready',status
        assert 'body' not in status and 'article_title' not in status
        reply=client.post('/api/chat',json={'article_id':article['id'],
            'question':'What did the council approve?','language':'English'})
        assert reply.status_code==200
        assert reply.json()['generated_by'] in {'groq','ollama'}
        assert reply.json()['sources'][0]['url']==URL
        assert 'publisher article text' in reply.json()['caveat']

"""Offline regression coverage for Google News -> permitted publisher resolution."""
import asyncio
from urllib.parse import quote

from app import article_context, core


STORY = 'Regional science council approves new digital public library initiative'
PUB_URL = 'https://www.newindianexpress.com/example/digital-public-library'
GOOGLE_URL = 'https://news.google.com/rss/articles/CBMiOpaqueExample12345?oc=5'
BODY = ('The regional science council approved a new digital public library initiative '
        'after public consultation. It plans to open educational resources to students. '
        'The council said the project will start in the next financial year. ') * 8


def _article(article_id='resolve-1'):
    return {'id': article_id, 'title': STORY, 'url': GOOGLE_URL,
            'publisher': 'The New Indian Express', 'description': ''}


def test_google_aggregator_is_not_fetched_without_a_publisher_url(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'test.db')
    core.init_db(); article_context.init_db()

    async def unresolved(_article):
        return None

    async def forbidden_fetch(_url):
        raise AssertionError('Never fetch Google News as publisher article text')

    monkeypatch.setattr(article_context, '_resolve_google_rss', unresolved)
    monkeypatch.setattr(article_context, '_fetch_publisher_page', forbidden_fetch)
    result = asyncio.run(article_context._retrieve(_article()))
    assert result['status'] == 'limited'
    assert result['failure_code'] == 'publisher_url_not_resolved'


def test_direct_publisher_discovery_uses_story_and_publisher(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'test.db')
    core.init_db(); article_context.init_db()
    with core.db_conn() as db:
        db.execute('''INSERT INTO articles
            (id,fingerprint,title,description,url,publisher,published_at,region,
             region_confidence,topic,is_demo,created_at,language,summary_en,feed_origin)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            ('direct1', 'finger1', STORY+' announced', '', PUB_URL,
             'The New Indian Express', core.utcnow(), 'All India',
             'not_verified','Education',0,core.utcnow(),'English','', 'direct_publisher_rss'))
    monkeypatch.setattr(article_context, '_valid_url', lambda u: u == PUB_URL)
    found = asyncio.run(article_context._resolve_from_index(_article()))
    assert found == PUB_URL
    unrelated = dict(_article(), publisher='India Today')
    assert asyncio.run(article_context._resolve_from_index(unrelated)) is None


def test_bing_rss_resolver_only_trusts_matching_publisher_and_title(monkeypatch):
    destination = 'https://www.newindianexpress.com/example/digital-public-library'
    wrapped = ('https://www.bing.com/news/apiclick.aspx?ref=news&url='+quote(destination, safe=''))
    wrong_publisher = 'https://www.indiatoday.in/example/digital-public-library'
    rss = (f'<rss><channel>'
           f'<item><title>{STORY}</title><link>{wrong_publisher}</link></item>'
           f'<item><title>Celebrity gossip programme airs tonight</title>'
           f'<link>{wrapped.replace("&", "&amp;")}</link></item>'
           f'<item><title>{STORY}</title>'
           f'<link>{wrapped.replace("&", "&amp;")}</link></item>'
           f'</channel></rss>').encode()

    class Response:
        def __init__(self, content):
            self.content = content
            self.text = content.decode('utf-8')
            self.status_code = 200

    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return False
        async def get(self, url, **kwargs):
            if url.endswith('/robots.txt'):
                return Response(b'User-agent: *\nAllow: /news/search')
            assert 'bing.com/news/search' in url
            return Response(rss)

    monkeypatch.setattr(article_context.httpx, 'AsyncClient', lambda **kwargs: Client())
    monkeypatch.setattr(article_context, '_valid_url',
                        lambda u: u.startswith('https://www.bing.com/news/search') or
                                  u.startswith('https://www.bing.com/robots.txt') or
                                  u.startswith('https://www.newindianexpress.com/'))
    assert asyncio.run(article_context._resolve_from_bing_rss(_article())) == destination


def test_publisher_retrieval_after_resolution(monkeypatch, tmp_path):
    monkeypatch.setattr(core, 'DB_PATH', tmp_path/'test.db')
    core.init_db(); article_context.init_db()
    calls = []

    async def resolved(_article):
        return PUB_URL

    async def fake_publisher_fetch(url):
        calls.append(url)
        return PUB_URL, ('<html><head><meta property="og:title" content="'
                         + STORY + '"></head><body><article><p>'
                         + BODY + '</p></article></body></html>')

    monkeypatch.setattr(article_context, '_resolve_google_rss', resolved)
    monkeypatch.setattr(article_context, '_fetch_publisher_page', fake_publisher_fetch)
    result = asyncio.run(article_context._retrieve(_article()))
    assert calls == [PUB_URL]
    assert result['status'] == 'ready'
    assert result['source_url'] == PUB_URL
    assert result['reader_revision'] == article_context.READER_REVISION
    assert article_context._fresh(result)
    assert not article_context._fresh({**result, 'reader_revision': ''})


def test_unsafe_or_unmatched_bing_links_rejected():
    assert not article_context._publisher_host_matches('India Today',
        'https://www.indiatoday.in.attacker.org/story')
    assert article_context._publisher_host_matches('India Today',
        'https://www.indiatoday.in/story')
    assert article_context._unwrap_bing_news_link(
        'https://www.bing.com/news/apiclick.aspx?ref=1&url=https%3A%2F%2Fwww.indiatoday.in%2Fstory') == \
        'https://www.indiatoday.in/story'
    assert not article_context._headline_overlap(
        'Regional council opens a library in Mumbai',
        'Another court refuses to quash a bank fraud investigation')

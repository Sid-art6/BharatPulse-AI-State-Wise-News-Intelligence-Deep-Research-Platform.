"""Offline v0.10 feed, provenance and coverage regression tests."""
import asyncio
import sqlite3

import httpx
from fastapi.testclient import TestClient

from app import core, coverage_v10
from app.main import app
from app.regional_sources_v10 import REGION_FEEDS, HINDU_FEEDS, feeds_for_region, feed_for_region


def rss(title, link='https://publisher.example/one', description='', publisher_source=''):
    tag = f'<source>{publisher_source}</source>' if publisher_source else ''
    return (f'<rss><channel><item><title>{title}</title><link>{link}</link>'
            f'<description>{description}</description>{tag}</item></channel></rss>').encode()


def test_direct_publisher_list_has_only_allowlisted_fixed_hosts():
    assert len(REGION_FEEDS) >= 20
    for region, spec in REGION_FEEDS.items():
        assert spec.section_region == region
        assert spec.name == 'The Indian Express'
        assert spec.url.startswith('https://indianexpress.com/section/')
        assert spec.url.endswith('/feed/')
        assert '..' not in spec.url
    assert feed_for_region('Fake Region') is None
    assert len(HINDU_FEEDS) == 4
    assert len(feeds_for_region('Karnataka')) == 2
    assert all(item.url.startswith('https://www.thehindu.com/') for item in HINDU_FEEDS.values())


def test_section_metadata_is_weak_region_evidence():
    items = core.parse_rss(rss('Council debates transport funding'), 'Karnataka',
                           provider='The Indian Express', section_region='Karnataka')
    assert items[0]['region'] == 'Karnataka'
    assert items[0]['region_confidence'] == 'publisher_section'
    assert items[0]['publisher'] == 'The Indian Express'
    assert items[0]['feed_origin'] == 'direct_publisher_rss'


def test_explicit_place_overrides_section_hint():
    items = core.parse_rss(rss('Delhi council reviews transport funding'), 'Karnataka',
                           provider='The Indian Express', section_region='Karnataka')
    assert items[0]['region'] == 'Delhi'
    assert items[0]['region_confidence'] == 'explicit'


def test_bbc_google_and_direct_provenance_differ():
    payload = rss('Kerala coastal project', publisher_source='Example Publisher')
    assert core.parse_rss(payload, 'Kerala')[0]['feed_origin'] == 'google_news_rss'
    assert core.parse_rss(payload, 'Kerala', provider='BBC News')[0]['feed_origin'] == 'bbc_publisher_rss'
    assert core.parse_rss(payload, 'Kerala', provider='The Indian Express')[0]['publisher'] == 'The Indian Express'


def test_direct_rss_fetch_and_aggregated_feed_coexist(monkeypatch):
    requests = []
    async def google(query, lang='en'):
        requests.append(('google', lang))
        return rss('Karnataka council announces roads plan', 'https://google.example/one')
    async def fixed(url):
        requests.append(('fixed', url))
        return rss('Council announces local roads plan', 'https://indianexpress.com/news/council')
    monkeypatch.setattr(core, 'fetch_rss', google)
    monkeypatch.setattr(core, '_fetch_fixed_rss', fixed)
    rows = asyncio.run(core.fetch_news('Karnataka'))
    assert any(row['feed_origin'] == 'direct_publisher_rss' for row in rows)
    assert any(row['feed_origin'] == 'google_news_rss' for row in rows)
    assert ('fixed', REGION_FEEDS['Karnataka'].url) in requests


def test_direct_feed_failures_do_not_hide_google_results(monkeypatch):
    async def google(query, lang='en'):
        return rss('Karnataka announces rail project')
    async def blocked(url):
        raise httpx.ConnectTimeout('test-only network error')
    monkeypatch.setattr(core, 'fetch_rss', google)
    monkeypatch.setattr(core, '_fetch_fixed_rss', blocked)
    result = asyncio.run(core.fetch_news('Karnataka'))
    assert len(result) >= 1
    assert result[0]['feed_origin'] == 'google_news_rss'


def test_all_feeds_unavailable_raise(monkeypatch):
    async def blocked(*args, **kwargs):
        raise httpx.ConnectTimeout('test-only network error')
    monkeypatch.setattr(core, 'fetch_rss', blocked)
    monkeypatch.setattr(core, '_fetch_fixed_rss', blocked)
    try:
        asyncio.run(core.fetch_news('Karnataka'))
    except httpx.ConnectTimeout:
        pass
    else:
        raise AssertionError('All unavailable feeds should raise')


def test_feed_origin_is_saved_and_returned(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    core.init_db()
    rows = core.parse_rss(rss('Karnataka council meeting'), 'Karnataka',
                          provider='The Indian Express', section_region='Karnataka')
    assert core.save_articles(rows) == 1
    stored = core.get_article(rows[0]['id'])
    assert stored['feed_origin'] == 'direct_publisher_rss'


def test_schema_migrates_old_database_without_deleting_articles(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    # Re-create the pre-v0.10 articles schema; SQL migration must add the field.
    with sqlite3.connect(tmp_path / 'news.db') as db:
        db.execute('''CREATE TABLE articles (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
             title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
             publisher TEXT NOT NULL, published_at TEXT NOT NULL, region TEXT NOT NULL,
             region_confidence TEXT NOT NULL, topic TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0,
             created_at TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'Unknown',
             summary_en TEXT NOT NULL DEFAULT '', UNIQUE(fingerprint, is_demo))''')
        db.execute("INSERT INTO articles(id,fingerprint,title,publisher,published_at,region,region_confidence,topic,created_at) VALUES('old','old-fp','Old news','Example','','Delhi','explicit','General','')")
    core.init_db()
    row = core.get_article('old')
    assert row['title'] == 'Old news'
    assert row['feed_origin'] == 'unclassified_legacy'


def test_similarity_is_a_signal_not_independent_verification():
    sources = [
        {'title': 'UK raises concerns over high Scotch tariffs with India', 'publisher': 'Reuters', 'description': ''},
        {'title': 'UK raises concerns over high Scotch tariffs with India', 'publisher': 'Another Label', 'description': ''},
    ]
    signal = coverage_v10.analyse_coverage(sources)
    assert signal['publisher_label_count'] == 2
    assert signal['headline_overlap_groups'][0]['sources'] == [1, 2]
    assert 'Not established' in signal['independence_status']


def test_number_inventory_does_not_invent_or_compare_amounts():
    rows = [
        {'title': 'Publisher claims 162.5% duty on bulk Scotch', 'description': 'The amount ₹5 crore was reported', 'publisher': 'A'},
        {'title': 'Publisher cites 100% rate in a different category', 'description': '', 'publisher': 'B'},
    ]
    inventory = coverage_v10.analyse_coverage(rows)['reported_numbers']
    assert {(row['source'], row['value']) for row in inventory} >= {(1,'162.5%'), (1,'₹5 crore'), (2,'100%')}
    assert all('verified' not in item for item in inventory)


def test_numeric_inventory_preserves_source_citation_indices():
    rows = [{'title': 'No numbers', 'description': ''}, {'title': '₹125 crore announced', 'description': ''}]
    amounts = coverage_v10.analyse_coverage(rows)['reported_numbers']
    assert amounts[0]['source'] == 2
    assert amounts[0]['context'].startswith('₹125 crore')


def test_source_coverage_is_present_in_abstention_report():
    from app import research_v2
    report = research_v2.initial_report([{'title':'Rates rise 7%', 'publisher':'One'}])
    assert report['status'] == 'insufficient_evidence'
    assert report['coverage']['reported_numbers'][0]['value'] == '7%'


def test_api_version_and_public_source_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'test.db')
    with TestClient(app) as client:
        assert client.get('/api/health').json()['version'] == '0.10.0'
        data = client.get('/api/meta').json()
        assert data['direct_publisher_feed_sections'] == len(REGION_FEEDS) + len(HINDU_FEEDS)
        assert data['providers']['indian_express_direct_rss'] == 'implemented_curated_sections'
        assert data['providers']['the_hindu_direct_rss'] == 'implemented_selected_sections'


def test_related_search_rejects_single_keyword_overlap():
    selected = {'id':'selected', 'fingerprint':'first', 'title':'Karnataka rain school closure decision',
                'publisher':'Paper A'}
    candidates = [
        {'id':'weak', 'fingerprint':'weak', 'title':'Karnataka market meeting scheduled',
         'description':'', 'publisher':'Paper B', 'published_at':'2026-11-23'},
        {'id':'strong', 'fingerprint':'strong', 'title':'Karnataka rain leads school closure discussion',
         'description':'', 'publisher':'Paper C', 'published_at':'2026-11-23'},
    ]
    assert [row['id'] for row in core.find_related(selected, candidates)] == ['strong']


def test_distinct_publisher_label_can_receive_ranking_preference():
    selected = {'id':'start','fingerprint':'start','title':'India UK Scotch whisky tariff concern',
                'publisher':'Paper A'}
    candidates = [
        {'id':'a','fingerprint':'a','title':'India UK Scotch whisky tariff concern deepens',
         'description':'', 'publisher':'Paper A','published_at':'2026-11-23'},
        {'id':'b','fingerprint':'b','title':'India UK Scotch whisky tariff concern grows',
         'description':'', 'publisher':'Paper B','published_at':'2026-11-23'},
    ]
    result = core.find_related(selected, candidates, limit=2)
    assert {r['id'] for r in result} == {'a', 'b'}
    assert result[0]['publisher'] == 'Paper B'


def test_related_search_keeps_paraphrase_with_one_meaningful_topic_word():
    selected = {'id': 'selected', 'fingerprint': 'first',
                'title': 'Karnataka panel reviews fuel testing', 'publisher': 'Local Paper'}
    candidates = [
        {'id': 'related', 'fingerprint': 'second',
         'title': 'Officials request a technical review of fuel checks',
         'description': 'A technical review of fuel checks has been requested by officials.',
         'publisher': 'Another Paper', 'published_at': '2026-11-22'},
        {'id': 'unrelated', 'fingerprint': 'third',
         'title': 'Karnataka market meeting scheduled', 'description': '',
         'publisher': 'Local Paper', 'published_at': '2026-11-22'},
    ]
    assert [row['id'] for row in core.find_related(selected, candidates)] == ['related']

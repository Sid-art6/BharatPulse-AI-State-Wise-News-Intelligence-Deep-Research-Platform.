"""Deep Research v2: offline evidence and chronology invariants."""
import asyncio
import json

from fastapi.testclient import TestClient
from app import ai, core, research_v2
from app.main import app


def source(title, excerpt, date, publisher='Local Paper', idx='one'):
    return {
        'id': idx, 'title': title, 'description': excerpt,
        'publisher': publisher, 'region': 'Karnataka', 'language': 'English',
        'published_at': date, 'url': f'https://local.example/{idx}',
        'is_demo': 0, 'fingerprint': idx, 'topic': 'Policy', 'created_at': '',
        'summary_en': excerpt, 'region_confidence': 'explicit',
    }


SOURCES = [
    source('Karnataka panel reviews fuel testing',
           'The Karnataka panel said that an assessment of fuel testing methods is under way.',
           '2026-11-23T05:26:51+00:00'),
    source('Karnataka panel requests review of fuel testing methods',
           'A technical review of fuel checks has been requested by officials.',
           '2026-11-22T19:00:00+00:00', 'Another Paper', 'two'),
]


def test_valid_report_accepts_literal_quoted_source_excerpt():
    payload = {'findings': [{'claim': 'The Karnataka panel is reviewing fuel testing methods.',
                            'evidence': [{'source': 1, 'quote': 'Karnataka panel reviews fuel testing'}]}],
               'open_questions': ['What does the full official assessment conclude?']}
    report = research_v2.build_report(json.dumps(payload), SOURCES)
    assert report['status'] == 'anchored_excerpt_claims'
    assert report['findings'][0]['evidence'][0]['source'] == 1
    assert report['publication_timeline'][0]['source'] == 2
    assert 'publication timestamp' in ' '.join(report['not_verified']).lower()
    assert report['open_questions'] == ['What does the full official assessment conclude?']


def test_rejects_nonexistent_quotes_bad_sources_and_unsupported_numbers():
    raw = {'findings': [
        {'claim': 'The minister estimated ₹900 crore loss from fuel testing.',
         'evidence': [{'source': 1, 'quote': 'Karnataka panel reviews fuel testing'}]},
        {'claim': 'The Karnataka panel reviewed its testing method.',
         'evidence': [{'source': 77, 'quote': 'Karnataka panel reviews fuel testing'}]},
        {'claim': 'The Karnataka panel reviewed its testing method.',
         'evidence': [{'source': 1, 'quote': 'A report that never appeared in the RSS feed'}]},
    ]}
    report = research_v2.build_report(json.dumps(raw), SOURCES)
    assert report['status'] == 'insufficient_evidence'
    assert report['rejected_claims'] == 3
    assert report['findings'] == []
    assert '₹900' not in json.dumps(report)


def test_unknown_date_is_not_fabricated():
    missing = core.parse_rss(b'<rss><channel><item><title>Karnataka rail announcement</title>'
                             b'<link>https://news.example/id</link><description>Rail plan under review</description>'
                             b'</item></channel></rss>', 'Karnataka')
    assert missing[0]['published_at'] == ''
    timeline = research_v2.publication_timeline(missing)
    assert timeline[0]['published_at'] == 'Not supplied by feed'


def test_bad_llm_json_cannot_be_displayed_as_factual_research():
    report = research_v2.build_report('** Factual claim [1] invented **', SOURCES)
    assert report['findings'] == []
    assert report['status'] == 'insufficient_evidence'


def test_research_endpoint_uses_structured_evidence_and_safe_fallback(monkeypatch, tmp_path):
    import pytest
    pytest.importorskip("langgraph")  # Actual StateGraph integration.
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'groq')
    monkeypatch.setattr(ai, 'GROQ_API_KEY', 'test-only-key')
    monkeypatch.setattr(ai, 'ENABLE_LLM_FILTER', False)

    async def empty_news(_):
        return []

    async def empty_followup(_):
        return b'<rss><channel></channel></rss>'

    async def fake_report(entries, language):
        assert language == 'Hindi'
        assert len(entries) >= 2
        return research_v2.build_report(json.dumps({'findings': [
            {'claim': 'The Karnataka panel approved a ₹999 crore payout.',
             'evidence': [{'source': 1, 'quote': 'Karnataka panel reviews fuel testing'}]},
        ]}), entries)

    monkeypatch.setattr(core, 'fetch_news', empty_news)
    monkeypatch.setattr(core, 'fetch_rss', empty_followup)
    monkeypatch.setattr(research_v2, 'generate_report', fake_report)

    with TestClient(app) as client:
        core.save_articles(SOURCES)
        response = client.post('/api/research/one', json={'language': 'Hindi'})
        assert response.status_code == 200
        payload = response.json()
        assert payload['generated_by'] == 'insufficient_evidence'
        assert payload['report']['findings'] == []
        assert payload['report']['rejected_claims'] == 1
        assert payload['report']['publication_timeline'][0]['source'] == 2
        assert '₹999' not in json.dumps(payload['report'])
        assert payload['sources'][0]['publisher'] == 'Local Paper'
        assert 'not full-article research' in payload['caveat']


def test_hindi_claim_uses_english_bridge_without_adding_unsupported_figures():
    payload = {'findings': [{
        'claim': 'कर्नाटक पैनल ईंधन परीक्षण की समीक्षा कर रहा है।',
        'claim_en': 'The Karnataka panel reviews fuel testing methods.',
        'evidence': [{'source': 1, 'quote': 'Karnataka panel reviews fuel testing'}],
    }]}
    report = research_v2.build_report(json.dumps(payload, ensure_ascii=False), SOURCES)
    assert report['status'] == 'anchored_excerpt_claims'
    assert report['findings'][0]['claim'].startswith('कर्नाटक')
    assert 'claim_en' not in report['findings'][0]


def test_original_script_unsupported_number_is_rejected_despite_english_bridge():
    payload = {'findings': [{
        'claim': 'कर्नाटक पैनल ने 900 करोड़ रुपये दिए।',
        'claim_en': 'The Karnataka panel reviewed fuel testing methods.',
        'evidence': [{'source': 1, 'quote': 'Karnataka panel reviews fuel testing'}],
    }]}
    report = research_v2.build_report(json.dumps(payload, ensure_ascii=False), SOURCES)
    assert report['findings'] == []
    assert report['rejected_claims'] == 1


def test_native_language_quote_is_matched_without_forcing_english_tokens():
    native = [source('कर्नाटक में सड़क मरम्मत योजना की घोषणा', 'कर्नाटक में सड़क मरम्मत का काम शुरू होगा', '', idx='hindi')]
    payload = {'findings': [{
        'claim': 'कर्नाटक में सड़क मरम्मत योजना की घोषणा की गई।',
        'claim_en': 'Karnataka road maintenance plan was announced.',
        'evidence': [{'source': 1, 'quote': 'कर्नाटक में सड़क मरम्मत योजना की घोषणा'}],
    }]}
    report = research_v2.build_report(json.dumps(payload, ensure_ascii=False), native)
    assert len(report['findings']) == 1


def test_end_to_end_structured_groq_answer_uses_literal_quote(monkeypatch, tmp_path):
    import pytest
    pytest.importorskip("langgraph")  # Actual StateGraph integration.
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DB_PATH', tmp_path / 'news.db')
    monkeypatch.setattr(ai, 'LLM_PROVIDER', 'groq')
    monkeypatch.setattr(ai, 'GROQ_API_KEY', 'test-only-key')
    monkeypatch.setattr(ai, 'ENABLE_LLM_FILTER', False)

    async def no_news(_):
        return []

    async def no_followup(_):
        return b'<rss><channel></channel></rss>'

    async def mock_complete(messages, *, json_mode, max_tokens):
        assert json_mode is True
        if 'INPUT:' in messages[-1]['content']:
            return json.dumps({'decisions': [{'id': 1, 'supported': True}]})
        assert 'SOURCE DATA' in messages[-1]['content']
        assert 'English' in messages[-1]['content']
        return json.dumps({'findings': [{
            'claim': 'The Karnataka panel reviews fuel testing methods.',
            'claim_en': 'The Karnataka panel reviews fuel testing methods.',
            'evidence': [{'source': 1, 'quote': 'Karnataka panel reviews fuel testing'}],
        }], 'open_questions': ['What does the official technical note say?']})

    monkeypatch.setattr(core, 'fetch_news', no_news)
    monkeypatch.setattr(core, 'fetch_rss', no_followup)
    monkeypatch.setattr(ai, '_complete', mock_complete)
    with TestClient(app) as client:
        core.save_articles(SOURCES)
        result = client.post('/api/research/one', json={'language': 'English'})
        assert result.status_code == 200
        report = result.json()['report']
        assert result.json()['generated_by'] == 'groq'
        assert report['status'] == 'anchored_excerpt_claims'
        assert report['findings'][0]['evidence'][0]['source'] == 1
        assert report['publication_timeline'][0]['source'] == 2

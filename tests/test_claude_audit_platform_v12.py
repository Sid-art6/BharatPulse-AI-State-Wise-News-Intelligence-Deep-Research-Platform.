"""Cross-category guardrails derived from the Claude audit, no network/model calls."""
import asyncio
import json

import pytest

from app import ai, answer_policy, chat_v07, core, research_agents_v09, research_v2, weather
from app.evidence_utils import normalise, numbers, has_meaningful_excerpt, hedge_preserved
from app.regions import detect_language


def selected(title='District metro timetable revised after signal checks'):
    return {'id':'chosen','fingerprint':'chosen','title':title,'description':'',
            'publisher':'Independent City Journal','url':'https://example.org/selected',
            'region':'Karnataka','region_confidence':'explicit',
            'published_at':'2026-11-24T10:00:00+00:00','is_demo':0}


@pytest.mark.parametrize('question',["What is the death toll?", "What are the charges against him?",
                                    "What is the reason for the delay?", "What are the demands?",
                                    "What is the impact on commuters?"])
def test_generic_news_slots_never_enter_unverified_general_path(question):
    assert answer_policy.article_intent(question, selected(), 'general') == 'article'


def test_metadata_answer_uses_publisher_and_feed_time_not_model():
    story=selected()
    assert answer_policy.article_intent('Who published the report?',story,'general') == 'metadata'
    answer, rows=answer_policy.answer_metadata('Who published the report?', story)
    assert story['publisher'] in answer and story['published_at'] in answer
    assert 'RSS metadata' in answer and rows[0]['index']==1


def test_general_knowledge_cannot_copy_event_figures():
    story=selected('Local fire: 18 injuries reported after 5 km evacuation')
    assert not answer_policy.general_answer_firewall('What is evacuation?', 'Evacuation involves 18 injuries.', story)
    assert answer_policy.general_answer_firewall('What is evacuation?', 'Evacuation means moving people away from danger.', story)


def test_unicode_digits_and_pseudo_excerpt_consistent():
    assert normalise('India’s ₹९०० – report') == "india's ₹900 - report"
    assert numbers('९००') == numbers('900')
    assert not has_meaningful_excerpt('Metro reopens', 'Metro reopens Independent Desk', 'Independent Desk')
    assert has_meaningful_excerpt('Metro reopens', 'Service resumed after signal checks.', 'Independent Desk')
    assert detect_language('India’s ₹5 crore plan — today') == 'English'


def test_hedged_claim_is_not_asserted_as_court_fact():
    assert not hedge_preserved('Officials confirmed the accused committed the offence.', 'The suspect allegedly committed the offence.')
    assert hedge_preserved('Officials filed a report.', 'Officials filed a report about an allegedly false document.')


def test_review_parsers_preserve_only_valid_unique_ids():
    claims=[{'id':1},{'id':2}]
    raw='{"verdicts":[{"id":1,"supported":true},{"id":2,"supported":"true"}]}'
    assert chat_v07._parse_verdicts(raw, claims)=={1}
    duplicate='{"decisions":[{"id":1,"supported":true},{"id":1,"supported":true},{"id":2,"supported":true}]}'
    assert research_agents_v09.parse_review(duplicate,[{},{}])=={2}


def test_research_discovery_does_not_write_to_main_news(monkeypatch):
    story=selected()
    async def rss(query):
        return b'<rss><channel><item><title>District metro timetable revised after signal checks</title><link>https://example.org/news</link></item></channel></rss>'
    def fail_save(_items):
        raise AssertionError('Research discovery must not mutate dashboard news')
    monkeypatch.setattr(core,'fetch_rss',rss)
    monkeypatch.setattr(core,'save_articles',fail_save)
    result=asyncio.run(research_agents_v09.discover({'query':'metro when:30d','selected':story}))
    assert result['discovered'] and result['trace'][0]['status']=='completed'


def test_secondary_topic_only_not_eligible_for_finding():
    a=selected()
    b={**selected('Other city discusses general metro safety'), 'id':'topic',
       'relationship':'topic_context','description':'Officials discussed safety approaches for metro lines.'}
    raw={'findings':[{'claim':'Officials discussed safety approaches for metro lines.',
                      'claim_en':'Officials discussed safety approaches for metro lines.',
                      'evidence':[{'source':2,'quote':b['description']}]}]}
    report=research_v2.build_report(json.dumps(raw),[a,b])
    assert report['findings']==[]


def test_tomorrow_vs_day_after_tomorrow_and_weather_word_boundaries():
    days=[{'date':f'2026-11-{24+i}'} for i in range(4)]
    assert weather._days_for_question('day after tomorrow',days)==days[2:3]
    assert weather._days_for_question('tomorrow',days)==days[1:2]

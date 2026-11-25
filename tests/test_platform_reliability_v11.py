"""Platform-wide regression tests using invented articles, never live news requests."""
import asyncio
import json

import pytest

from app import ai, answer_policy, chat_router_v1, core, research_agents_v09, research_v2


def article(title="Operation Sagar: Rescue teams regroup near the coast"):
    return {"id":"s","title":title,"description":"The source reports a rescue operation.",
            "publisher":"Independent District News","url":"https://example.org/report",
            "published_at":"2026-11-24T12:00:00+00:00","region":"Karnataka","is_demo":0}


def test_primary_subject_does_not_enter_unrestricted_general_model():
    s=article()
    assert answer_policy.article_intent('What is Operation Sagar?',s,chat_router_v1.intent('What is Operation Sagar?')) == 'article'
    assert answer_policy.article_intent('What is Operation Sagar, and what happened?',s,'general') == 'article'
    assert answer_policy.article_intent('What is the purpose of Operation Sagar?',s,'general') == 'article'
    assert answer_policy.article_intent('What is an OMR sheet?',article('Exam case: officials analyse an OMR sheet'), 'general') == 'general'


def test_article_person_identity_cannot_invent_external_biography():
    a=article('Court hears petition filed by author Niraj Verma')
    assert answer_policy.article_intent('Who is Niraj Verma?',a,'general') == 'article'
    assert answer_policy.article_intent('Who is some unrelated person?',a,'general') == 'general'


def test_publisher_lookup_is_direct_and_source_attributed():
    s=article()
    assert answer_policy.article_intent('Which news sources reported this?',s,'evidence') == 'source_list'
    assert answer_policy.article_intent('What do available news sources say?',s,'overview') == 'overview'
    text, indexed=answer_policy.answer_source_list([s])
    assert 'Independent District News' in text and indexed[0]['index']==1
    assert 'independently' in text


def test_later_event_answer_does_not_transform_current_location_to_next_event():
    s=article('Wildlife team sees 18 animals at 5 km from a forest')
    intent=answer_policy.article_intent('What happened after they regrouped?',s,'article')
    assert intent == 'later_events'
    text, idx=answer_policy.answer_later_events([s])
    assert 'does not establish what happened after' in text
    assert idx[0]['publisher']=='Independent District News'


def test_no_llm_still_visits_review_stage_and_preserves_evidence():
    s=article()
    report=research_v2.initial_report([s])
    synth=asyncio.run(research_agents_v09.synthesise({'llm_ready':False,'report':report}))
    assert synth['trace'][0]['agent']=='Synthesis'
    assert synth['trace'][0]['status']=='skipped'
    review=asyncio.run(research_agents_v09.semantic_review({'report':synth['report'],'review_status':synth['review_status']}))
    assert review['trace'][0]['agent']=='Quality Reviewer'
    assert review['trace'][0]['status']=='skipped'
    assert synth['report']['source_observations'][0]['source']==1


def test_quote_and_unsupported_number_gate_is_not_removed():
    src=[article('Investigation: officials requested a review of assessment methods')]
    invalid={"findings":[{"claim":"Officials confirmed a 92 crore payment.",
                        "claim_en":"Officials confirmed a 92 crore payment.",
                        "evidence":[{"source":1,"quote":src[0]['title']}]}]}
    report=research_v2.build_report(json.dumps(invalid),src)
    assert report['status']=='insufficient_evidence'
    assert not report['findings']
    assert report['rejected_claims']==1


def test_source_comparison_explicitly_separates_topic_context():
    chosen=article()
    other={**article('Other district discusses general rescue safety'), 'id':'o',
           'relationship':'topic_context'}
    rows=research_v2.source_comparison([chosen,other])
    assert rows[0]['relationship']=='selected_story'
    assert rows[1]['relationship']=='topic_context'


def test_exact_six_nodes_when_langgraph_installed(monkeypatch):
    pytest.importorskip('langgraph')
    chosen=article()
    monkeypatch.setattr(core,'list_articles',lambda **kwargs: [])
    async def empty(_query): return b'<rss><channel/></rss>'
    monkeypatch.setattr(core,'fetch_rss',empty)
    monkeypatch.setattr(core,'save_articles',lambda items: 0)
    async def unconfigured():return False
    monkeypatch.setattr(ai,'llm_is_configured',unconfigured)
    research_agents_v09._graph=None
    result=asyncio.run(research_agents_v09.run_research(chosen))
    assert [x['agent'] for x in result['workflow']['trace']] == [
        'Planner','Discovery','Retriever','Synthesis','Quality Reviewer','Report Builder']
    assert [x['status'] for x in result['workflow']['trace']][-3:] == ['skipped','skipped','completed']
    assert result['generated_by']=='source_index_no_llm'


def test_reported_count_and_distance_are_literal_not_inferred():
    from app import coverage_v10
    s=article('Rescue update: 39 animals are 3.5 km from the boundary')
    values={r['value'] for r in coverage_v10.analyse_coverage([s])['reported_numbers']}
    assert '39 animals' in values
    assert '3.5 km' in values

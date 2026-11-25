"""Cross-category acceptance checks for objective-grounding and conservative fallback.

Synthetic article names deliberately differ from previous live incidents. No
model/network calls are required; tests should stay hermetic in CI.
"""
import asyncio

from app import chat_router_v1, coverage_v10, research_agents_v09, research_insights, research_v2


def source(title, description='', *, publisher='Regional Ledger', relation='selected_story'):
    return {'id': title[:25], 'title': title, 'description': description,
            'publisher': publisher, 'relationship': relation,
            'evidence_origin': 'publisher_article' if description else 'rss',
            'feed_origin': 'direct_publisher_rss', 'published_at': '2026-11-25T09:00:00+00:00'}


def test_objectives_recognise_event_date_and_official_response_from_real_passage():
    news = source('Ministry criticises attack on business district tower',
                  'Three visitors were injured in an attack on a tower in Central City on November 24, the ministry said. '
                  'Officials condemned the attack and called for an end to strikes.')
    q = ('Investigate the reported November 24 attack, what happened, the location, '
         'reported casualties, official response, responsibility and later developments.')
    objectives = {x['id'] for x in research_insights.requested_topics(q)}
    assert {'event_date', 'incident', 'location', 'casualties', 'official_response', 'outcome'} <= objectives
    approved = [{'claim':'Three visitors were injured in Central City on November 24.',
                 'evidence':[{'source':1, 'quote':'Three visitors were injured in an attack on a tower in Central City on November 24'}]}]
    focus = {x['id']:x for x in research_insights.build_insights([news],q,approved)['research_focus']}
    assert focus['event_date']['status'] == 'mentioned_in_rss'
    assert focus['event_date']['reviewed_findings'] == 1
    assert focus['official_response']['status'] == 'mentioned_in_rss'
    assert focus['outcome']['status'] == 'not_established_by_indexed_rss'


def test_research_assembler_cannot_call_approved_date_missing():
    item = source('Ministry responds to attack on tower',
                  'A tower was attacked on November 24. Officials condemned the incident.')
    quote = 'A tower was attacked on November 24.'
    report = research_v2.initial_report([item], 'When did the attack happen and how did officials respond?')
    report['findings'] = [{'claim': quote, 'evidence':[{'source':1,'quote':quote}],
                           'status':'reported_event'}]
    state = {'report':report, 'sources':[item], 'question':'When did the attack happen and how did officials respond?',
             'llm_ready': True, 'language':'English', 'objectives':['Date','Official response']}
    result = asyncio.run(research_agents_v09.assemble(state))
    assert result['report']['question_coverage']['event_date'] == 'mentioned_in_rss'
    assert 'date of the reported event' not in result['report']['key_takeaway'].lower()
    assert all('date of the reported event' not in q.lower() for q in result['report']['open_questions'])


def test_direct_quote_recovery_when_llm_cannot_approve_claim():
    item = source('Officials respond to airport disruption',
                  'Several departures were disrupted at the airport. '
                  'The transport ministry condemned the disruption and arranged assistance.')
    result = chat_router_v1.requested_passage('How did the government respond to the disruption?', [item])
    assert result is not None
    answer, citations = result
    assert 'ministry condemned the disruption' in answer
    assert '[1]' in answer and citations[0]['publisher'] == 'Regional Ledger'
    assert 'independently verified facts' in answer


def test_does_not_invent_cause_from_incident_passage():
    item = source('Agency investigates fire at industrial warehouse',
                  'A fire was reported at a warehouse on Tuesday. Investigators attended the site.')
    assert chat_router_v1.requested_passage('Why did the fire occur?', [item]) is None


def test_coverage_handles_injury_counts_but_ignores_unrelated_event():
    records = [source('Two tourists among 11 injured in coastal ferry incident'),
               source('11 injured after ferry incident; two tourists treated', relation='possible_same_story'),
               source('Court investigates Rs 50 lakh banking scandal',relation='topic_context')]
    coverage = coverage_v10.analyse_coverage(records)
    assert any('11 injured' in n['value'] for n in coverage['reported_numbers'])
    assert not any(n['source'] == 3 for n in coverage['reported_numbers'])


def test_official_response_is_not_confused_with_incident_summary():
    item=source('Government responds to coastal flooding',
                'The river flooded the market on Monday. The state government announced emergency shelters.')
    result=chat_router_v1.requested_passage('What did the government announce in response?', [item])
    assert result is not None
    assert 'announced emergency shelters' in result[0]

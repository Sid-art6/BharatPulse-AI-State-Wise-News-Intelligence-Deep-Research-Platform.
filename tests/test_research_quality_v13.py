"""Platform-wide quality regression tests. All names, sources and events are synthetic.

No provider credentials, network calls, article-specific exceptions or live feeds.
"""
import asyncio
import json

import pytest

from app import ai, answer_policy, chat_router_v1, core, research_agents_v09, research_insights, research_v2


def article(title='Rohan Sen assumes charge as Eastern Refinery CGM', index='1', publisher='Harbour Ledger'):
    return {'id':index, 'fingerprint':index, 'title':title, 'description':'',
            'publisher':publisher,'published_at':'2026-11-24T12:00:00+00:00',
            'region':'Kerala', 'region_confidence':'explicit','url':'https://example.org/'+index,
            'feed_origin':'test_rss', 'is_demo':0}


@pytest.mark.parametrize('question, expected', [
    ('Who is Rohan Sen, and what position has he assumed?', 'article'),
    ('Who is Rohan Sen?', 'article'),
    ('Which news publisher reported this appointment?', 'metadata'),
    ('Who published this article?', 'metadata'),
    ('What does CGM stand for in this report?', 'general'),
    ('What is known about his professional background?', 'article'),
    ('What are his responsibilities?', 'article'),
    ('When did he assume charge?', 'article'),
])
def test_generic_chat_routing(question, expected):
    selected = article()
    assert answer_policy.article_intent(question, selected, chat_router_v1.intent(question)) == expected


def test_context_free_biography_not_generated_for_selected_person(monkeypatch, tmp_path):
    from app.main import _chat_answer, ChatPayload
    selected = article()
    monkeypatch.setattr(core, 'get_article', lambda _: selected)
    monkeypatch.setattr(core, 'list_articles', lambda **kwargs: [])
    monkeypatch.setattr(core, 'candidate_articles', lambda _: [])
    async def no_model():return False
    monkeypatch.setattr(ai, 'llm_is_configured', no_model)
    response = asyncio.run(_chat_answer(ChatPayload(article_id='1', question='Who is Rohan Sen, and what position has he assumed?')))
    assert response['intent']=='article'
    assert response['generated_by'] != 'mixed_ai'
    assert 'Harbour Ledger' in response['answer']
    assert 'worked at' not in response['answer']


def test_publisher_lookup_directly_from_feed_metadata(monkeypatch):
    from app.main import _chat_answer, ChatPayload
    selected = article()
    monkeypatch.setattr(core, 'get_article', lambda _: selected)
    monkeypatch.setattr(core, 'list_articles', lambda **kwargs: [])
    monkeypatch.setattr(core, 'candidate_articles', lambda _: [])
    response = asyncio.run(_chat_answer(ChatPayload(article_id='1', question='Which news publisher reported this appointment?')))
    assert response['generated_by']=='source_metadata'
    assert 'Harbour Ledger' in response['answer']
    assert 'not enough' not in response['answer'].casefold()


@pytest.mark.parametrize('question', [
    'What is his professional background?', 'When did he assume charge?',
    'What responsibilities will he have?', 'Who was his predecessor?',
])
def test_true_but_irrelevant_headline_restatement_does_not_answer_question(question):
    claim={'text':'Rohan Sen assumed charge as the CGM of Eastern Refinery.',
           'quote':'Rohan Sen assumes charge as Eastern Refinery CGM'}
    assert not answer_policy.claim_answers_question(question, claim)


def test_no_unrelated_company_biography_in_general_prompt(monkeypatch):
    async def model(messages, **kwargs):
        system=messages[0]['content']
        assert 'Do NOT supply biographies' in system
        return 'CGM commonly stands for Chief General Manager; the RSS title does not expand it.'
    monkeypatch.setattr(ai, '_complete', model)
    outcome=asyncio.run(chat_router_v1.general_answer('What does CGM stand for?', 'English', article()['title']))
    assert 'Chief General Manager' in outcome


def test_research_question_creates_bounded_additional_search():
    query=research_insights.discovery_query(article()['title'], 'Identify the previous role and appointment date.')
    assert 'previous role' in query
    assert 'Rohan' in query and 'when:30d' in query
    assert 'https://' not in query
    assert not research_insights.discovery_query(article()['title'], 'What is reported?')


def test_secondary_same_story_is_visible_without_inventing_career():
    chosen=article()
    second=article('Leadership: APCL appoints Rohan Sen as CGM In-Charge at Eastern Refinery','2','Industry Watch')
    second['relationship']='possible_same_story'
    result=research_insights.build_insights([chosen, second],
        'Identify the previous position, appointment date, company, responsibilities and implications.')
    assert result['source_highlights'][0]['source']==2
    focus={row['id']:row['status'] for row in result['research_focus']}
    assert focus['previous_role']=='not_established_by_indexed_rss'
    assert focus['event_date']=='not_established_by_indexed_rss'
    assert focus['organisation']=='mentioned_in_rss'
    lead=research_insights.short_summary([chosen,second],result)
    assert 'APCL appoints' in lead
    assert 'does not establish' in lead
    assert '[1]' in lead and '[2]' in lead


def test_cross_incident_context_is_not_claim_support():
    chosen=article()
    other=article('Different port authority discusses general refinery safety','2','Coastal Daily')
    other['relationship']='topic_context'
    report=research_v2.initial_report([chosen,other], 'What are the responsibilities?')
    assert not report['source_highlights']
    assert report['topic_context_highlights'][0]['source']==2
    payload={'findings':[{'claim':'The authority discusses general refinery safety.',
                          'claim_en':'The authority discusses general refinery safety.',
                          'evidence':[{'source':2,'quote':other['title']}]}]}
    assert not research_v2.build_report(json.dumps(payload),[chosen,other])['findings']


def test_all_six_nodes_pass_actual_state_and_preserve_secondary_details(monkeypatch):
    first=article('District Water Unit launches a water filtration pilot','1','Local Ledger')
    second=article('District Water Unit pilot introduces filtration stations','2','Area Review')
    second['relationship']='possible_same_story'
    monkeypatch.setattr(core,'candidate_articles',lambda _selected: [])
    monkeypatch.setattr(core,'list_articles',lambda **kw: [])
    monkeypatch.setattr(core,'parse_rss',lambda *_args,**_kw: [second])
    async def rss(_query):return b'<rss/>'
    monkeypatch.setattr(core,'fetch_rss',rss)
    async def ready():return True
    monkeypatch.setattr(ai,'llm_is_configured',ready)
    monkeypatch.setattr(ai,'active_provider',lambda: 'groq')

    async def fake_model(messages, **kw):
        user = messages[-1]['content']
        if 'decisions' in user and 'supporting_quotes' in user:
            return json.dumps({'decisions':[{'id':1,'supported':True},{'id':2,'supported':True}]})
        return json.dumps({'findings':[
            {'claim':'District Water Unit launches a water filtration pilot.',
             'claim_en':'District Water Unit launches a water filtration pilot.',
             'evidence':[{'source':1,'quote':first['title']}]},
            {'claim':'District Water Unit pilot introduces filtration stations.',
             'claim_en':'District Water Unit pilot introduces filtration stations.',
             'evidence':[{'source':2,'quote':second['title']}]},
        ], 'open_questions':[]})
    monkeypatch.setattr(ai,'_complete',fake_model)

    async def run():
        state={'selected':first,'language':'English',
               'question':'What later outcomes or responsibilities are reported?', 'trace':[]}
        for fn in [research_agents_v09.plan,research_agents_v09.discover,
                   research_agents_v09.retrieve,research_agents_v09.synthesise,
                   research_agents_v09.semantic_review,research_agents_v09.assemble]:
            update=await fn(state)
            state.update({k:v for k,v in update.items() if k!='trace'})
            state['trace']+=update.get('trace',[])
        return state
    output=asyncio.run(run())
    assert [step['agent'] for step in output['trace']]==[
        'Planner','Discovery','Retriever','Synthesis','Quality Reviewer','Report Builder']
    assert len(output['sources'])==2
    assert len(output['report']['findings'])==2
    assert output['report']['source_highlights'][0]['source']==2
    assert output['report']['key_takeaway'].count('[1]')>=1
    assert output['report']['key_takeaway'].count('[2]')>=1

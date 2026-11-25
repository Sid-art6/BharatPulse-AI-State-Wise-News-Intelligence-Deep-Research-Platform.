"""Platform-wide fail-closed checks with synthetic stories, no live APIs."""
import json
from app import ai, answer_policy, chat_router_v1, chat_v07, research_v2


def source(title, description='', index=1, relation=None):
    obj = {'id': str(index), 'title': title, 'description': description,
           'publisher': f'Publisher {index}', 'url': f'https://local.example/{index}',
           'published_at': '2026-11-24T08:00:00+00:00', 'region': 'All India',
           'is_demo': False, 'fingerprint': str(index)}
    if relation:
        obj['relationship'] = relation
    return obj


def test_selected_subject_is_not_a_general_definition_for_multiple_domains():
    scenarios = [
        ('Task Saffron: rescue teams retrieve 12 boats', 'What is Task Saffron?'),
        ('Policy Prism: council approves planning review', 'Explain Policy Prism'),
        ('Project Cedar: schools resume classes', 'What was the purpose of Project Cedar?'),
    ]
    for title, question in scenarios:
        result = answer_policy.article_intent(question, source(title), chat_router_v1.intent(question))
        assert result == 'article'


def test_unrelated_generic_definition_keeps_its_own_route():
    selected = source('Exam audit: candidates challenge scoring methodology')
    question = 'What is an OMR sheet?'
    assert answer_policy.article_intent(question, selected, 'general') == 'general'


def test_source_list_distinguishes_publisher_from_topic_context():
    picked = source('Harbour rescue: 12 boats return', index=1)
    context = source('Marine conservation plan announced', index=2, relation='topic_context')
    result, index = answer_policy.answer_source_list([picked, context])
    assert 'Publisher 1' in result and 'Publisher 2' in result
    assert 'NOT evidence' in result
    assert [row['index'] for row in index] == [1, 2]


def test_topic_context_is_not_permitted_in_chat_claims():
    picked = source('Hospital board announces patient audit', index=1)
    unrelated = source('Other hospital introduces a new policy', index=2, relation='topic_context')
    raw = json.dumps({'claims': [{'source': 2, 'claim_en': 'Other hospital introduces a new policy.',
                                 'quote': 'Other hospital introduces a new policy'}]})
    claims, rejected = chat_v07.validate_candidate_claims(raw, [picked, unrelated])
    assert not claims and rejected >= 1


def test_topic_context_cannot_pass_deep_research_quote_gate():
    picked = source('Hospital board announces patient audit', index=1)
    unrelated = source('Other hospital introduces a new policy', index=2, relation='topic_context')
    payload = {'findings': [{'claim': 'Other hospital introduces a new policy.',
                            'claim_en': 'Other hospital introduces a new policy.',
                            'evidence': [{'source': 2, 'quote': 'Other hospital introduces a new policy'}]}]}
    report = research_v2.build_report(json.dumps(payload), [picked, unrelated])
    assert not report['findings'] and report['rejected_claims'] == 1
    assert report['source_comparison'][1]['relationship'] == 'topic_context'


def test_presupposing_followup_question_not_promoted_from_model():
    selected = source('Rescue operation: 12 boats wait near harbour')
    payload = {'findings': [], 'open_questions': [
        'What specific actions has the team taken to relocate the boats?',
        'What information is available in the official documents?'
    ]}
    report = research_v2.build_report(json.dumps(payload), [selected])
    assert not any('taken to relocate' in q for q in report['open_questions'])
    assert any('official documents' in q for q in report['open_questions'])


def test_later_event_abstains_without_event_timeline():
    selected = source('Council completes annual review')
    answer, cited = answer_policy.answer_later_events([selected])
    assert 'does not establish what happened after' in answer
    assert cited[0]['index'] == 1


def test_no_duplicate_source_numbers_are_generated():
    selected = source('Local newspaper announces scheme')
    answer, citations = answer_policy.answer_source_list([selected])
    assert '[1]' in answer and '[2]' not in answer
    assert len(citations) == 1

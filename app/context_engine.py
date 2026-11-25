"""Deterministic context selection and directly supported RSS answers.

One contextual Groq call remains the fallback for ambiguous concepts. This
module never treats feed headlines as proof and never claims full article text
was read. No paid search, network request or embeddings are needed.
"""
from __future__ import annotations

import re
from typing import Any

ABBREVIATION_QUERY = re.compile(
    r'^\s*(?:(?:what|who)\s+(?:is|are)|what\s+does|meaning\s+of|'
    r'full\s+form\s+of|define|expand|explain)\s+'
    r'(?:the\s+|an?\s+)?([A-Za-z][A-Za-z0-9.]{1,9})'
    r'(?:\s+(?:mean|stand\s+for))?\s*\??\s*$', re.I)
CONTEXTUAL_TERMS = re.compile(r'\b(?:election|electoral|poll|voter|voting|rolls?|SIR|revision)\b', re.I)
LEGAL_ARGUMENT = re.compile(r'\b(?:argu(?:ed|es|ing)|contend(?:s|ed)|maintain(?:s|ed)|assert(?:s|ed))\s+that\b', re.I)
COURT_ACTION = re.compile(r'\b(?:court|tribunal|petition|lawsuit|litigation|restrain|injunction)\b', re.I)
FOLLOWUP_REFERENCE = re.compile(r'\b(?:it|its|they|them|this|that|the same|those|the decision|the ruling)\b', re.I)


def abbreviation(question: str) -> str | None:
    match = ABBREVIATION_QUERY.fullmatch(question.strip())
    if not match:
        return None
    token = match.group(1).upper().replace('.', '')
    # Do not mistake an ordinary short word such as 'dam' for an acronym.
    original = match.group(1).replace('.', '')
    return token if original.isupper() and 2 <= len(token) <= 8 else None


def article_context(article: dict[str, Any]) -> str:
    """Bounded, explicitly unverified metadata for contextual inference."""
    title = str(article.get('title') or '')[:240]
    description = str(article.get('description') or '')[:650]
    region = str(article.get('region') or '')[:80]
    topic = str(article.get('topic') or '')[:80]
    # Title and description are *data*, never system instructions.
    return f'Region: {region}\nTopic: {topic}\nRSS headline: {title}\nRSS excerpt: {description}'


def is_electoral_article(article: dict[str, Any]) -> bool:
    snippet = ' '.join(str(article.get(k) or '') for k in ('title', 'description', 'topic'))
    return bool(re.search(r'\b(?:election|electoral|poll|voter|voting|elector|rolls?|revision)\b', snippet, re.I))


def expansion_in_rss(term: str, article: dict[str, Any]) -> str | None:
    """Resolve *any* acronym when an explicit full form occurs in RSS metadata.

    Require matching initials so a coincidental phrase before parentheses
    cannot be promoted into a definition. Never infer unknown expansions.
    """
    excerpt = ' '.join(str(article.get(k) or '') for k in ('title', 'description'))[:1200]
    escaped = re.escape(term)
    patterns = [
        re.compile(r'([A-Za-z][A-Za-z-]*(?:\s+(?:[A-Za-z][A-Za-z-]*)){1,7})\s*\(' + escaped + r'\)', re.I),
        re.compile(r'\b' + escaped + r'\s*\(([^()]{4,90})\)', re.I),
    ]
    stop = {'of', 'and', 'the', 'for', 'in', 'to', 'on', 'a', 'an'}
    for pattern in patterns:
        for match in pattern.finditer(excerpt):
            phrase = match.group(1).strip()
            words = re.findall(r'[A-Za-z][A-Za-z-]*', phrase)
            # First pattern can greedily capture unrelated preceding words;
            # test each suffix as a potential matching expansion.
            for offset in range(len(words)):
                candidate = words[offset:]
                initials = ''.join(w[0].upper() for w in candidate if w.casefold() not in stop)
                if initials == term and 2 <= len(candidate) <= 8:
                    return ' '.join(candidate)
    return None


def contextual_definition(question: str, article: dict[str, Any]) -> str | None:
    """Only safe, unambiguous *domain* expansions; not a per-story lookup."""
    term = abbreviation(question)
    if term:
        explicit = expansion_in_rss(term, article)
        if explicit:
            return (f'In the selected RSS report, {term} is expanded as {explicit}. '
                    'This identifies the term used by the source; the headline and excerpt '
                    'do not by themselves establish all details of the reported event.')
    if term == 'SIR' and is_electoral_article(article):
        return (
            'In this election-news context, SIR means Special Intensive Revision of '
            'electoral rolls. It is an exercise conducted by election authorities to '
            'review and update voter lists. The selected report discusses SIR voter '
            'lists; that headline alone does not establish whether those lists '
            'should be used for a particular election.'
        )
    return None


def user_followup(question: str, history: list[dict[str, Any]]) -> str:
    """Carry forward earlier *questions* only for genuine elliptical follow-ups."""
    if not history or not FOLLOWUP_REFERENCE.search(question) or len(question) > 250:
        return question
    previous = history[-1].get('question', '')[:260]
    if not previous:
        return question
    return f'Current user question: {question}\nEarlier question for pronoun resolution only (not evidence): {previous}'


def legal_argument_answer(question: str, sources: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]] | None:
    """Use reported legal arguments without upgrading them to court findings.

    Deliberately excludes non-legal detention questions: 'on way to' is
    context, not a causal explanation for police action.
    """
    if not re.search(r'\bwhy\b|\bwhat\s+(?:reason|prompted)\b', question, re.I):
        return None
    if not sources:
        return None
    selected = sources[0]
    title = str(selected.get('title') or '')
    if not COURT_ACTION.search(title):
        return None
    desc = str(selected.get('description') or '').strip()
    match = LEGAL_ARGUMENT.search(desc)
    if not match:
        return None
    statement = desc[:480].rstrip(' .')
    publisher = str(selected.get('publisher') or 'the selected publisher')
    response = (
        f'According to {publisher}\'s indexed RSS excerpt, the reported legal argument was: '
        f'“{statement}” [1].\n\n'
        'This describes an argument made in the dispute, not a finding or ruling by the court. '
        'The RSS excerpt may not contain every reason for the legal action.'
    )
    return response, [{'index': 1, **selected}]


# Operational responses: when RSS describes actual security precautions, these
# can be reported as context. "High alert ahead of polls" never by itself
# establishes a specific threat, police intelligence, or wrongdoing.
ELECTION_EVENT = re.compile(r"\b(?:polls?|elections?|voting|panchayat|ballots?)\b", re.I)
SECURITY_ALERT = re.compile(r"\b(?:high alert|heightened alert|security alert|security tightened|on alert)\b", re.I)
SECURITY_MEASURES = re.compile(
    r"\b(?:surveillance|patrol(?:s|ling)?|monitor(?:ed|ing)?|sensitive villages|"
    r"strengthen(?:ed|ing)? security|enforce election rules|security measures|"
    r"security deployment|security checks|police deployment)\b", re.I,
)


def election_security_context_answer(question: str, sources: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]] | None:
    """Describe documented election security precautions without inventing a trigger.

    This is intentionally conservative: a headline about a politician's
    detention during elections must never be taken as evidence for the
    police's *reason* for detaining them.
    """
    if not re.search(r"\b(?:why|reason|what prompted|what led to)\b", question, re.I):
        return None
    if not sources:
        return None
    chosen = sources[0]
    title = str(chosen.get('title') or '').strip()[:280]
    desc = str(chosen.get('description') or '').strip()[:550]
    if not (ELECTION_EVENT.search(title) and SECURITY_ALERT.search(title)
            and SECURITY_MEASURES.search(desc)):
        return None
    publisher = str(chosen.get('publisher') or 'The selected publisher')
    answer = (
        f'According to {publisher}, “{title}” [1]. The RSS excerpt describes '
        f'the reported security precautions: “{desc}”.\n\n'
        'This identifies the reported election-security context and precautions, '
        'but the excerpt does not establish any particular threat or incident '
        'that triggered the alert.'
    )
    return answer, [{'index': 1, **chosen}]


def resolve_elliptical_article_question(question: str, article: dict[str, Any]) -> str:
    """Supply selected article as referent for short questions, not as evidence.

    The selected RSS headline is context, so a bare 'Why?' refers to the
    headline's main reported event, not to a random previous chat response.
    """
    q = ' '.join(question.split())
    if re.fullmatch(r'why\s*[?.!]*', q, re.I):
        headline = str(article.get('title') or '').strip()[:230]
        if headline:
            return f'Why did this reported event happen: “{headline}”?'
    if re.fullmatch(r'(?:give me|provide|explain|tell me)\s+(?:(?:the|some|more)\s+)?context\s*[?.!]*', q, re.I):
        headline = str(article.get('title') or '').strip()[:230]
        if headline:
            return f'Give a source-grounded overview of the reported event: “{headline}”.'
    return question

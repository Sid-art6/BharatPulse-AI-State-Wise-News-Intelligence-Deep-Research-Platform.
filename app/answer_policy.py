"""Generic, evidence-first routing and deterministic answers for article chat.

A selected article is the anchor. Unknown entity biographies and named operations
must not slip into ungrounded general-answer generation. No article names or
news-specific answers are hardcoded here.
"""
from __future__ import annotations

import re
from typing import Any

from . import chat_router_v1
from .evidence_utils import numbers


def _words(value: str) -> list[str]:
    return re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE)


EVENT_SLOTS = re.compile(
    r"\b(?:death\s+toll|casualt(?:y|ies)|injur(?:ed|ies)|charges|allegations?|"
    r"reason|causes?|motives?|demands?|impact|outcome|what\s+happened|"
    r"arrested|convicted|investigation|how\s+many|when\s+did|why\s+did|"
    r"where\s+are|who\s+filed|what\s+steps|objective|purpose)\b", re.I)
METADATA_QUESTIONS = re.compile(
    r"\b(?:(?:who|which\s+(?:(?:news|media)\s+)?(?:publisher|publication|outlet|source))\s+(?:published|reported|covered)|"
    r"(?:who|which\s+(?:news\s+)?(?:publisher|outlet|publication))\s+(?:first\s+)?(?:reported|published|covered)\b|"
    r"(?:when|what\s+date)\s+(?:was|did)\s+(?:this|the)\s+(?:article|report|story)\s+publish(?:ed)?|"
    r"(?:publication\s+date|publisher\s+name|source\s+link|original\s+link))\b", re.I)

def article_intent(question: str, selected: dict[str, Any], proposed: str) -> str:
    """Never route an article event slot to source-free general generation."""
    q = " ".join(question.strip().split())
    title = str(selected.get("title") or "")
    if METADATA_QUESTIONS.search(q):
        return "metadata"
    # Pure acronym-expansion requests are explanations, not claims about
    # what the executive, organisation or investigation actually did.
    acronym_query = re.search(
        r"^\s*(?:what\s+does|what\s+is\s+the\s+full\s+form\s+of|expand)\s+([A-Za-z][A-Za-z0-9.]{1,8})"
        r"\s+(?:stand\s+for|mean)(?:\s+in\s+(?:this|the)\s+(?:report|article|context))?\s*[?.!]*$", q, re.I)
    if acronym_query and acronym_query.group(1).replace('.', '').isupper():
        return "general"
    # An identity question combined with a question about the SAME selected
    # article is NOT a license to improvise an external biography.
    identity = re.match(r"^\s*who\s+(?:is|was)\s+(.{3,90}?),?\s+and\s+(?:what|which|when|where|why|how)\b", q, re.I)
    if identity:
        person = identity.group(1).strip(" ,?.!")
        if person.casefold() in (title + ' ' + str(selected.get('description') or '')).casefold():
            return "article"
    # Named organisations, places and operations occurring in the selected
    # headline must not be answered with unverified organisation background.
    # Generic definitions such as "What is an OMR sheet?" stay separate.
    definition = re.match(r"^\s*what\s+(?:is|was|are)\s+(?:the\s+)?([^?!.]{3,90})\s*[?.!]*$", q, re.I)
    if definition and proposed == "general":
        subject = definition.group(1).strip().rstrip('?.!')
        words = subject.split()
        if (2 <= len(words) <= 7
                and all(w[0].isupper() for w in words if w and w[0].isalpha())
                and subject.casefold() in title.casefold()):
            return "article"
    if EVENT_SLOTS.search(q) and proposed in {"general", "mixed"}:
        # When the question names the selected headline subject, it is about
        # this article even when phrased as a compound definition request.
        primary = title.split(":", 1)[0].strip() if ":" in title else ""
        if primary and primary.casefold() in q.casefold():
            return "article"
        # Otherwise a compound definition + event question has two standards.
        if re.search(r"\band\s+(?:why|what|how|where|when|who)\b", q, re.I):
            return "mixed"
        return "article"
    if re.search(r"^\s*(?:which|list|name|show)\b.*\b(?:sources|publishers|outlets|source\s+links)\b|\b(?:who|which\s+outlet)\s+(?:reported|published|covered)\b", q, re.I):
        return "source_list"
    if re.search(r"\b(?:what happened (?:after|next|later)|any (?:subsequent|later) (?:updates?|developments)|what (?:then|next) happened)\b", q, re.I):
        return "later_events"
    # A named person occurring in the selected report is an *article identity*
    # query unless the user clearly asks for a source-independent definition.
    if chat_router_v1.person_identity_query(q):
        name = re.sub(r"^who\s+(?:is|was)\s+", "", q, flags=re.I).strip(" ?.!")
        if len(_words(name)) >= 2 and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", title + " " + str(selected.get("description") or ""), re.I):
            return "article"
    # A primary named subject in the selected headline is article-specific,
    # even when the question uses generic educational phrasing. General
    # definitions of terms merely mentioned in a report stay separate.
    primary_subject = title.split(":", 1)[0].strip() if ":" in title else ""
    if primary_subject and len(_words(primary_subject)) >= 2:
        if re.search(r"(?<!\w)" + re.escape(primary_subject) + r"(?!\w)", q, re.I):
            if re.search(r"\b(?:what|who|why|when|where|how|explain|describe|purpose|objective|happened|role|meaning)\b", q, re.I):
                return "article"
    # 'What is OMR sheet?' describes a concept mentioned in a headline;
    # 'What is Operation Gaja?' names the report's own subject. The prefix
    # clause before a colon is a strong topic boundary, not a news keyword list.
    if proposed in {"general", "mixed"}:
        match = re.fullmatch(r"\s*what\s+(?:is|was|are)\s+(.+?)\s*[?.!]*", q, re.I)
        if match:
            phrase = match.group(1).strip(" ?.!")
            leading = title.split(":", 1)[0].strip()
            subject = leading if ":" in title else " ".join(_words(title)[:4])
            target = _words(phrase)
            head = _words(subject)
            if len(target) >= 2 and head[:len(target)] == target:
                return "article"
            if (":" in title and len(head) >= 2 and
                    re.search(r"(?<!\w)" + re.escape(subject) + r"(?!\w)", q, re.I)):
                # The question explicitly mentions the selected named event,
                # including 'what is the purpose of <event>'.
                return "article"
        if match and subject and len(_words(subject)) >= 2 and re.match(r"^\s*what\s+(?:is|was|are)\s+" + re.escape(subject) + r"(?:\b|[,?.!])", q, re.I):
            return "article"
        # 'What is happening with the elephants?' is event-specific by grammar.
        if re.search(r"\b(?:what\s+is\s+happening|what\s+are\s+.+\s+doing|what\s+is\s+.+\s+doing)\b", q, re.I):
            return "article"
    return proposed


def answer_metadata(question: str, selected: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Publisher/date/link are first-party RSS fields; never run an LLM."""
    pub = str(selected.get('publisher') or 'Publisher not specified')
    date = str(selected.get('published_at') or '')
    origin = str(selected.get('feed_origin') or 'unclassified feed')
    source_url = str(selected.get('url') or '')
    # A feed timestamp is not proof of when the underlying event occurred.
    time = date if date else 'No feed publication time supplied'
    answer = f"Publisher: {pub} [1]. Feed origin: {origin}. Feed publication time: {time}."
    if source_url.startswith('https://'):
        answer += " The source link is available below [1]."
    answer += " This is RSS metadata, not independent verification of the news event."
    return answer, [{'index':1, **selected}]


def general_answer_firewall(question: str, background: str, selected: dict[str, Any]) -> bool:
    """Disallow new article figures or incident claims in a general definition."""
    excerpt = str(selected.get('description') or '') + ' ' + str(selected.get('title') or '')
    new_figures = numbers(excerpt) - numbers(question)
    if new_figures & numbers(background):
        return False
    # A definition must not create source-free relationships between real
    # corporations, people or government departments and the selected event.
    # Those questions belong in the article-evidence pipeline.
    if re.search(r"\b(?:operated|owned|managed|controlled|appointed|employed)\s+by\s+[A-Z]", background):
        return False
    subject = str(selected.get('title') or '').split(':',1)[0].strip()
    if len(subject.split()) >= 2 and subject.casefold() in background.casefold() and subject.casefold() not in question.casefold():
        return False
    return True


def answer_source_list(sources: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Return publisher names, not a fake 'no evidence' answer."""
    if not sources:
        return "No source records are indexed for this story.", []
    indexed = [{"index": i, **item} for i, item in enumerate(sources[:6], 1)]
    lines = ["Publisher identified for the selected RSS report (not independent verification):"]
    first = indexed[0]
    lines.append(f'[{first["index"]}] {first.get("publisher") or "Unlabelled publisher"} — {first.get("title") or "Untitled"}.')
    same = [x for x in indexed[1:] if x.get("relationship") == "possible_same_story"]
    context = [x for x in indexed[1:] if x.get("relationship") != "possible_same_story"]
    if same:
        lines.append("Other potentially same-story RSS headlines (incident identity not established):")
        for item in same:
            lines.append(f'[{item["index"]}] {item.get("publisher") or "Unlabelled publisher"} — {item.get("title") or "Untitled"}.')
    if context:
        lines.append("Topic-context links below are NOT evidence that these outlets reported the selected incident:")
        for item in context:
            lines.append(f'[{item["index"]}] {item.get("publisher") or "Unlabelled publisher"} — {item.get("title") or "Untitled"}.')
    lines.append("These publishers have not independently confirmed the selected event; one or several matching headlines do not prove independent confirmation.")
    return "\n".join(lines), indexed


def answer_later_events(sources: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    if not sources:
        return "No indexed source evidence establishes subsequent developments.", []
    selected = sources[0]
    publisher = selected.get("publisher") or "The selected source"
    return (f'{publisher} reports: “{str(selected.get("title") or "")[:280]}” [1]. '
            "The indexed metadata does not establish what happened after this reported development. "
            "A publication timestamp is not a timeline of later events."), [{"index": 1, **selected}]


def claim_answers_question(question: str, claim: dict[str, Any]) -> bool:
    """Evidence-slot guard: a true headline restatement is not always an answer.

    Only constrain slots where a generic news restatement is known to be
    misleading. Other queries still pass through the independent LLM reviewer.
    """
    q = question.casefold()
    evidence = (str(claim.get('quote') or '') + ' ' + str(claim.get('text') or '')).casefold()
    if re.search(r'\b(?:previous|formerly|prior\s+(?:role|job|position)|career|professional\s+background|experience)\b', q):
        return bool(re.search(r'\b(?:previously|previous|prior|earlier|formerly|before joining|served as|had been|career|experience)\b', evidence))
    if re.search(r'\b(?:predecessor|who\s+held\s+(?:this|the)\s+(?:role|position))\b', q):
        return bool(re.search(r'\b(?:succeeded|succeeds|replaced|replaces|predecessor|previously held)\b', evidence))
    if re.search(r'\b(?:when\s+did|exact\s+date|appointment\s+date|effective\s+date)\b', q):
        return bool(re.search(r'\b(?:20\d\d|19\d\d|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|yesterday|today|effective from)\b', evidence))
    if re.search(r'\b(?:responsibilit\w*|duties|what\s+(?:will|would)\s+(?:he|she|they)\s+do)\b', q):
        return bool(re.search(r'\b(?:responsible for|will oversee|will lead|tasked with|duties include|will manage|will supervise)\b', evidence))
    if re.search(r'\b(?:what\s+does\s+(?:his|her|their|this)\s+.*\b(?:mean|imply)|implications?|impact\s+of\s+(?:the|this))\b', q):
        return bool(re.search(r'\b(?:impact|implication|result in|expected to|will lead to|effects? on)\b', evidence))
    return True

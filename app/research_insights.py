"""Deterministic research-question coverage and transparent RSS comparison.

Never promotes RSS titles to verified facts. Every displayed evidence item is
literally present in an indexed publisher headline or meaningful RSS excerpt.
The labels describe evidence availability, not truth or independent corroboration.
"""
from __future__ import annotations

import re
from typing import Any
from .evidence_utils import has_meaningful_excerpt

# Generic information needs, not story names or particular named entities.
_FOCUS = (
    ('allegations', 'Allegations and attribution', r'\b(?:allegations?|charges?|accusations?)\b', r'\b(?:alleged|alleges|accused|charged|complaint)\b'),
    ('procedure', 'Procedural history', r'\b(?:procedural|proceedings|hearings?|appeal)\b', r'\b(?:filed|appealed|heard|petitioned|adjourned)\b'),
    ('reasoning', 'Judicial reasoning', r'\b(?:reasoning|grounds?|rationale)\b', r'\b(?:held that|reasoned|observed that|on the ground)\b'),
    ('decision', 'Decision and scope of the order', r'\b(?:judgment|judicial outcome|verdict|ruling|court outcome)\b', r'\b(?:dismissed|quashed|granted|upheld|overturned)\b'),
    ('evidence', 'Evidence cited by the sources', r'\b(?:evidence|testimony|documents)\b', r'\b(?:testified|affidavit|records show|cited|testimony)\b'),
    ('previous_role', 'Earlier positions and professional background', r'\b(?:previous|previously|prior|earlier|former|background|career|experience|career history)\b',
     r'\b(?:previously|previous|prior|earlier|formerly|served as|had been|before joining)\b'),
    ('event_date', 'Date of the reported event or appointment', r'\b(?:date|when|effective|assum(?:ed|ing) charge on|november|december|january|february|march|april|may|june|july|august|september|october)\b',
     r'\b(?:on\s+\d{1,2}\s+\w+|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:,?\s+20\d\d)?\b|effective from|with effect from)\b'),
    ('responsibilities', 'Specific actions, responsibilities or measures', r'\b(?:responsibilit|duties|measures|steps|actions|management|role|operations)\w*',
     r'\b(?:will oversee|will lead|responsible for|tasked with|measures include|introduced|taking steps|will manage)\b'),
    ('organisation', 'Organisation or institutional affiliation', r'\b(?:organisation|organization|company|institution|affiliation|operator|operated|refinery|department|agency|ownership)\b',
     r'\b(?:appoints|appointed|owned by|operated by|part of|under the|a unit of|subsidiary of|organisation|organization)\b'),
    ('reason', 'Stated cause, purpose or explanation', r'\b(?:why|reason|cause|motive|objective|purpose|trigger|prompted)\b',
     r'\b(?:because|due to|citing|in order to|the purpose|the reason|for the purpose|to address)\b'),
    ('outcome', 'Reported implications, results or later developments', r'\b(?:impact|implication|outcome|later|subsequent|afterwards|result|development|next)\b',
     r'\b(?:resulted in|following the|subsequently|later reported|as a result|has since|will result in)\b'),
    ('safety', 'Risks or public-safety implications', r'\b(?:risks?|danger|safety|residents|villages|communities|threat)\b',
     r'\b(?:warned|risk to|threatened|advised residents|evacuated|injured|safety alert)\b'),
    ('incident', 'What happened', r'\b(?:what\s+(?:exactly\s+)?happened|what\s+(?:occurred|took place)|(?:details\s+of|describe\s+the)\s+(?:incident|attack)|reported\s+attack|attack\s+on)\b',
     r'\b(?:attack(?:ed)?|incident|occurred|took place|happened|injured|condemned|announced|appointed|refused|reported)\b'),
    ('location', 'Location and target', r'\b(?:where|location|target|tower|district|city|place)\b',
     r'\b(?:in\s+[A-Z][a-z]+|at\s+(?:the|a)\s+|district|tower|city|region|village|refinery|forest)\b'),
    ('casualties', 'Casualties and medical status', r'\b(?:casualt(?:y|ies)|injur(?:y|ed|ies)|wounded|hospitali[sz]ed|medical|victims?|how\s+many\s+(?:people|indians))\b',
     r'\b(?:injur(?:ed|ies)|wounded|killed|casualties|deaths?|hospitali[sz]ed|\d+\s+(?:people|indians|persons)|(?:one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:people|indians|persons))\b'),
    ('attribution', 'Attribution and claimed responsibility', r'\b(?:who\s+(?:was\s+)?responsible|who\s+(?:carried\s+out|launched)|attribut(?:ion|ed)|responsibility|perpetrator|houthi|evidence\s+for)\b',
     r'\b(?:claimed responsibility|blamed|attributed|accused|alleged|houthi|reportedly|said|claimed)\b'),
    ('official_response', 'Official statements and response', r'\b(?:official|government|ministry|foreign\s+ministry|foreign\s+office|mea|condemn(?:ed|ation)?|respond(?:ed|se)?|statements?)\b',
     r'\b(?:condemn(?:s|ed|ation)?|ministry|official|government|stated|said|strongly condemn|embassy|called for|urged)\b'),
    ('assistance', 'Assistance to affected people', r'\b(?:assist(?:ance|ed|ing)?|help(?:ed|ing)?|support|embassy|families|consular)\b',
     r'\b(?:assist(?:ance|ed|ing)?|help(?:ed|ing)?|support(?:ing|ed)?|embassy|famil(?:y|ies)|consular)\b'),
    ('numbers', 'Numerical figures or distances', r'\b(?:how many|number|count|amount|distance|figures|kilometres?|km|percent|percentage)\b',
     r'\d[\d,.]*\s*(?:%|km|crore|lakh|elephants|people|persons|candidates|cases|years|million|billion)\b'),
)


def requested_topics(question: str) -> list[dict[str, str]]:
    """Translate natural-language research intent into generic, auditable slots."""
    result = [{'id': code, 'label': label, 'evidence_signal': evidence_signal}
              for code, label, trigger, evidence_signal in _FOCUS if re.search(trigger, question, re.I)]
    return result[:12]  # Generic objectives; independent of any named incident.


def _real_text(source: dict[str, Any]) -> str:
    title = str(source.get('title') or '')
    excerpt = str(source.get('description') or '')
    if has_meaningful_excerpt(title, excerpt, str(source.get('publisher') or '')):
        return title + ' ' + excerpt
    return title


def build_insights(sources: list[dict[str, Any]], question: str = '', findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Additional source observations and evidence gaps, without LLM inference."""
    sources = sources[:8]
    additional = []
    context = []
    for index, source in enumerate(sources[1:], 2):
        observation = {
            'source': index,
            'publisher': str(source.get('publisher') or 'Unlabelled publisher')[:100],
            'headline': str(source.get('title') or '')[:270],
            'excerpt': str(source.get('description') or '')[:450]
                if has_meaningful_excerpt(str(source.get('title') or ''), str(source.get('description') or ''), str(source.get('publisher') or '')) else '',
            'relationship': str(source.get('relationship') or 'relation_unverified'),
        }
        if observation['relationship'] == 'topic_context':
            context.append(observation)
        else:
            additional.append(observation)

    # Detect the presence of *specific* information rather than assigning any
    # person, role or cause ourselves. For a source without an additional
    # excerpt, the exact headline is still inspectable but does not gain a
    # higher confidence label.
    disputes = []
    for index, source in enumerate(sources, 1):
        if source.get("relationship") == "topic_context":
            continue
        sentences = re.split(r"(?<=[.!?।])\s+|\n+", _real_text(source))
        for statement in sentences:
            if len(statement) <= 420 and re.search(r"\b(?:disputed|denied|contested|contradicted|rejected the claim)\b", statement, re.I):
                disputes.append({"source": index, "quote": statement.strip()})
                break
    focus = []
    findings = findings or []
    for topic in requested_topics(question):
        signal = topic['evidence_signal']
        matching = [i for i, src in enumerate(sources, 1)
                    if (i == 1 or src.get('relationship') != 'topic_context')
                    and re.search(signal, _real_text(src), re.I)]
        # IMPORTANT: a topic cannot be declared absent if an approved finding
        # already supplies evidence for it. This is the contract between
        # Quality Review and Report Builder, not a separate guess by regex.
        reviewed = [f for f in findings if re.search(signal, str(f.get('claim') or ''), re.I)
                    or any(re.search(signal, str(e.get('quote') or ''), re.I)
                           for e in f.get('evidence', []))]
        for finding in reviewed:
            for e in finding.get('evidence', []):
                i = e.get('source')
                if type(i) is int and 1 <= i <= len(sources) and i not in matching:
                    matching.append(i)
        matching.sort()
        focus.append({'id': topic['id'], 'label': topic['label'],
                      'status': 'mentioned_in_rss' if matching else 'not_established_by_indexed_rss',
                      'sources': matching[:5],
                      'reviewed_findings': len(reviewed),
                      'note': ('Supported by an approved, quoted finding; see its source.' if reviewed else
                               'The cited source contains a potentially relevant passage; this alone does not establish the full answer.'
                               if matching else 'No qualifying information was identified in the selected incident evidence.')})
    return {'reported_disputes': disputes, 'source_highlights': additional[:6], 'topic_context_highlights': context[:4],
            'research_focus': focus}


def discovery_query(title: str, question: str) -> str:
    """One optional query from a stored title plus a WHITELISTED research slot.

    Never puts arbitrary client free text, URLs or instructions into RSS search.
    """
    topic_ids = {x['id'] for x in requested_topics(question)}
    keywords = {
        'allegations': 'allegations', 'procedure': 'proceedings', 'reasoning': 'reasoning',
        'decision': 'order', 'evidence': 'evidence',
        'previous_role': 'previous role',
        'event_date': 'date',
        'responsibilities': 'responsibilities',
        'organisation': 'company',
        'reason': 'reason',
        'outcome': 'updates',
        'safety': 'safety',
        'numbers': 'figures', 'incident': 'incident', 'location': 'location',
        'casualties': 'injured', 'attribution': 'responsibility', 'official_response': 'statement', 'assistance': 'assistance',
    }
    chosen = next((keywords[k] for k in keywords if k in topic_ids), None)
    if not chosen:
        return ''
    title_tokens = [w for w in re.findall(r'[^\W_]{2,}', title, re.UNICODE)
                    if w.casefold() not in {'the', 'and', 'for', 'from', 'with', 'after', 'near'}]
    if len(title_tokens) < 2:
        return ''
    return (' '.join(title_tokens[:7]) + ' ' + chosen)[:115].strip() + ' when:30d'


def short_summary(sources: list[dict[str, Any]], report: dict[str, Any]) -> str:
    """Attribution-preserving lead. No paraphrased news claims are invented."""
    if not sources:
        return 'No RSS evidence was indexed for the selected article.'
    first = sources[0]
    publisher = first.get('publisher') or 'the selected publisher'
    headline = str(first.get('title') or '').strip()[:240]
    parts = [f'{publisher} reports: “{headline}” [1].']
    if report.get("findings"):
        finding = report["findings"][0]
        parts = [finding["claim"] + " " + " ".join(f"[{a['source']}]" for a in finding["evidence"])]
    highlights = report.get('source_highlights', [])
    if highlights:
        s = highlights[0]
        parts.append(f'An additional potentially matching headline from {s["publisher"]} reads: “{s["headline"]}” [{s["source"]}].')
    missing = [x['label'].lower() for x in report.get('research_focus', [])
               if x['status'] == 'not_established_by_indexed_rss']
    if missing:
        parts.append('The available evidence does not establish: ' + '; '.join(missing[:3]) + '.')
    parts.append('These are attributed publisher passages or feed headlines, not independently verified facts.' if any(
        s.get('evidence_origin') == 'publisher_article' for s in sources) else
        'These are publisher feed statements, not independently verified facts.')
    return ' '.join(parts)

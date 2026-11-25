"""Deterministic RSS-evidence quality signals; never a fact-checker.

Source labels, text overlap and quantities are observations about the fetched
RSS *metadata*. They do not prove publisher independence, factual correctness,
primary sourcing, or that two figures describe the same measurement.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

STOP = {"the", "and", "for", "are", "from", "into", "about", "after", "says", "said", "with", "over", "news", "india", "latest", "has", "its", "new", "was", "that", "this", "more"}

# Exact literal numeric spans; no computed figures or interpretation.
_QUANTITY = re.compile(
    r"(?<![\w])(?:₹|Rs\.?|INR|US\$|USD|£|\$)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:crore|lakh|million|billion|trillion))?"
    r"|(?<![\w])\d+(?:\.\d+)?\s*%"
    r"|(?<![\w])\d[\d,]*(?:\.\d+)?\s*(?:crore|lakh|million|billion|trillion)\b"
    r"|(?<![\w])\d[\d,]*(?:\.\d+)?\s*(?:km|kilomet(?:er|re)s?|m(?:et(?:er|re))s?|hectares?|tonnes?|"
    r"people|persons|elephants|animals|families|villages|vehicles|students|candidates|days|hours)\b"
    r"|(?<![\w])\d[\d,]*\s+(?:injured|wounded|killed|dead|missing|hospitali[sz]ed)\b"
    r"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:indians|people|persons|injured|killed|students|families)\b",

    flags=re.IGNORECASE,
)


def title_tokens(title: str) -> set[str]:
    normal = unicodedata.normalize("NFKC", title).casefold()
    chars = "".join(c if unicodedata.category(c)[0] in {"L", "M", "N"} else " " for c in normal)
    return {t for t in chars.split() if len(t) >= 3 and t not in STOP}


def headline_overlap(first: str, second: str) -> float:
    a, b = title_tokens(first), title_tokens(second)
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 3)


def analyse_coverage(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep source indices identical to report citations (1-based)."""
    source_rows = sources[:12]
    labels = {str(s.get("publisher") or "Unknown").strip().casefold() for s in source_rows}
    origins = {str(s.get("feed_origin") or "unclassified").strip() for s in source_rows}
    similarity_groups: list[list[int]] = []
    for i, first in enumerate(source_rows):
        for j in range(i + 1, len(source_rows)):
            second = source_rows[j]
            # Conservative overlap threshold: similar headlines may still be
            # independent stories, and different headlines may be syndicated.
            if headline_overlap(str(first.get("title") or ""), str(second.get("title") or "")) >= 0.70:
                hits = [group for group in similarity_groups if i + 1 in group or j + 1 in group]
                if not hits:
                    similarity_groups.append([i + 1, j + 1])
                else:
                    merged = sorted({i + 1, j + 1, *(x for group in hits for x in group)})
                    similarity_groups = [g for g in similarity_groups if g not in hits]
                    similarity_groups.append(merged)
    overlap = [{"sources": indices, "note": "Similar headline wording; possible repeated or syndicated reporting, not proven"}
               for indices in sorted(similarity_groups, key=lambda g: g[0])[:6]]

    numbers: list[dict[str, Any]] = []
    seen = set()
    for i, source in enumerate(source_rows, 1):
        if i > 1 and source.get("relationship") == "topic_context":
            continue
        for field in ("title", "description"):
            raw = str(source.get(field) or "")[:1200]
            for match in _QUANTITY.finditer(raw):
                literal = match.group().strip()
                unique = (i, literal.casefold())
                if unique in seen:
                    continue
                seen.add(unique)
                start, end = match.span()
                # Expand the excerpt window to word boundaries so a numeric
                # context never starts mid-word (e.g. 'apers and answer keys').
                left = max(0, start - 55)
                right = min(len(raw), end + 55)
                if left > 0 and not raw[left - 1].isspace():
                    next_space = raw.find(" ", left, start)
                    if next_space != -1:
                        left = next_space + 1
                if right < len(raw) and not raw[right].isspace():
                    next_space = raw.find(" ", right)
                    if next_space != -1:
                        right = next_space
                    else:
                        right = len(raw)
                context = raw[left:right].strip()
                numbers.append({"source": i, "value": literal, "context": context, "field": field})
                if len(numbers) >= 15:
                    break
            if len(numbers) >= 15:
                break
        if len(numbers) >= 15:
            break

    return {
        "source_count": len(source_rows),
        "publisher_label_count": len(labels),
        "feed_origins": sorted(origins),
        "headline_overlap_groups": overlap,
        "reported_numbers": numbers,
        "independence_status": "Not established: different labels, domains or similar headlines do not prove independent reporting",
        "numbers_status": "Literal reported figures and units from RSS excerpts; not verified, comparable or necessarily current",
    }

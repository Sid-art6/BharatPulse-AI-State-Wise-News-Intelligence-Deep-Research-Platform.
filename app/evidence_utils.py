"""Reusable RSS evidence primitives; these never establish news truth."""
from __future__ import annotations
import re
import unicodedata

_TRANSLATE = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-", "…": "..."})

def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).translate(_TRANSLATE)
    text = "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() else ch for ch in text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return " ".join(text.casefold().split())

def numbers(text: str) -> set[str]:
    s = normalise(text)
    return {n.replace(",", "") for n in re.findall(r"\d+(?:[,.]\d+)*%?", s)}

def has_meaningful_excerpt(title: str, excerpt: str, publisher: str = "") -> bool:
    t, e, pub = normalise(title), normalise(excerpt), normalise(publisher)
    if not e or e == t: return False
    if t and e.startswith(t):
        suffix = e[len(t):].strip(" .–—-:|")
        if not suffix or suffix == pub or (pub and suffix.startswith(pub + " ") and len(suffix) < len(pub)+10):
            return False
    return True

def quote_in_source(quote: str, title: str, excerpt: str) -> bool:
    q = normalise(quote)
    return bool(q) and any(q in normalise(t) for t in (title, excerpt) if t)

def has_latin_letters(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]{3,}", value))

def hedge_preserved(claim: str, quote: str) -> bool:
    """Block definitive claims where RSS explicitly uses uncertainty language."""
    hedges = ("alleged", "allegedly", "accused", "reportedly", "claims", "claimed", "suspected", "may have", "could have")
    c, q = normalise(claim), normalise(quote)
    present = [x for x in hedges if re.search(r"(?<!\w)"+re.escape(x)+r"(?!\w)",q)]
    if not present:
        return True
    # A hedged allegation in a quote need not be repeated when the claim is
    # exclusively about the reported filing/request, rather than guilt.
    # Definitive claims of guilt or proof are never licensed by hedged evidence.
    if re.search(r"\b(?:confirmed|proven|guilty|was responsible|definitely)\b", c):
        return False
    # "Committed" can also occur in a conditional/attributed allegation.
    if "committed" in c and not any(x in c for x in ("alleged", "allegedly", "reportedly", "according to")):
        return False
    return True

def finding_status(quote: str) -> str:
    s=normalise(quote)
    if re.search(r"\b(?:alleged|allegedly|accused|suspected|fir|complaint|chargesheet)\b",s): return "allegation"
    if re.search(r"\b(?:court|judge|judgment|verdict|convicted|acquitted)\b",s): return "court_reporting"
    if re.search(r"\b(?:minister|police|official|directorate|government)\b.{0,70}\b(?:says|said|stated|announced|reported)\b",s): return "attributed_statement"
    return "reported_event"


def material_details_supported(claim: str, quote: str, publisher: str = "") -> bool:
    """Screen material additions before the model judges entailment."""
    if not has_latin_letters(quote):
        return True  # Cross-language claims still require semantic review.
    c, q = normalise(claim), normalise(quote)
    legal = r"\b(?:forgery|fraud|murder|bribery|extortion|convicted|acquitted|sentenced|corruption)\b"
    if set(re.findall(legal, c)) - set(re.findall(legal, q)):
        return False
    quantity = r"\d[\d,.]*\s*(?:crore|lakh|million|billion|km|tonnes?|hectares?|hours?|days?|%)"
    if set(re.findall(quantity, c)) - set(re.findall(quantity, q)):
        return False
    names = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", claim)
    return all(normalise(name).removeprefix("the ") in q or (
        normalise(name) == normalise(publisher) and
        re.search(re.escape(name) + r"\s+(?:reports|says|reported|states)", claim, re.I))
        for name in names)


def quote_context(quote: str, source: dict) -> str:
    """Supply nearby words so a reviewer can detect omitted negation or attribution."""
    for field in ("title", "description"):
        text = normalise(source.get(field, ""))
        phrase = normalise(quote)
        offset = text.find(phrase)
        if offset >= 0:
            return text[max(0, offset-150):offset+len(phrase)+150]
    return ""

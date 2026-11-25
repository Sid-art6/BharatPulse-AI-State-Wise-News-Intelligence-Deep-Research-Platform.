import asyncio
import json
from xml.etree import ElementTree as ET

import pytest
from app import article_context as reader, core, publisher_feed, research_v2, research_insights, chat_v07


@pytest.mark.parametrize("subject,other", [
    ("River Assembly election petition", "Hill Assembly election petition"),
    ("Mira Rao hospital complaint", "Tara Sen hospital complaint"),
    ("Lotus Finance merger vote", "Coral Finance merger vote"),
    ("Valley Transit commuter strike", "Coastal Transit commuter strike"),
    ("Saffron Reserve tiger census", "Silver Reserve tiger census"),
    ("Orchid Labs chip prototype", "Cedar Labs chip prototype"),
    ("Amber Clinic vaccine rollout", "Birch Clinic vaccine rollout"),
    ("Silver Academy exam results", "Cedar Academy exam results"),
    ("Amber Valley flood warning", "Cedar Valley flood warning"),
])
def test_similar_incidents_cannot_supply_numbers(subject, other):
    def row(key, text):
        return {"id": key, "title": "Officials review " + text, "description": "Costs reached 90 crore.",
                "fingerprint": key, "publisher": "Town Desk"}
    selected, different = row("a",subject), row("b",other)
    candidates = core.find_related(selected, [different])
    assert all(r["relationship"] == "topic_context" for r in candidates)
    report = research_v2.initial_report([selected, *candidates])
    assert all(r["source"] == 1 for r in report["coverage"]["reported_numbers"])
    assert all(r["source"] == 1 for r in report["publication_timeline"])


def test_syndicated_body_private_and_cached(monkeypatch, tmp_path):
    title = "Village water board restores the northern intake"
    url = "https://scroll.in/article/100/example"
    body = ("The village water board restored the northern intake following inspections. " * 10)
    item = ET.fromstring(f'<item xmlns:c="http://purl.org/rss/1.0/modules/content/"><title>{title}</title>'
                         f'<link>{url}</link><c:encoded><![CDATA[<p>{body}</p>]]></c:encoded></item>')
    row = {"id":"story","title":title,"publisher":"Scroll.in","url":"https://news.google.com/rss/articles/example"}
    async def provided(_url): return [item]
    monkeypatch.setattr(publisher_feed, "_items", provided)
    monkeypatch.setattr(core, "DB_PATH", tmp_path/"news.db")
    core.init_db()
    reader.init_db()
    result = asyncio.run(reader._retrieve(row))
    assert result["source_url"] == url and result["provenance"] == "publisher_syndicated_feed"
    assert reader.get_cached("story")["body"]
    with core.db_conn() as db:
        assert not db.execute("select body from article_context").fetchone()[0]
    assert not reader.public_source(reader.attach(row,result))["description"]


def test_direct_link_survives_duplicate_screening(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "DB_PATH", tmp_path/"news.db")
    core.init_db()
    title = "Marine institute opens satellite monitoring station"
    def parse(url,provider):
        return core.parse_rss(f"<rss><channel><item><title>{title}</title><link>{url}</link>"
                              "<source>Scroll.in</source></item></channel></rss>".encode(), "All India",provider)[0]
    google = parse("https://news.google.com/rss/articles/example","Google News")
    direct = parse("https://scroll.in/article/100/station","Scroll.in")
    core.save_articles([google])
    assert not core.unseen_articles([direct])
    monkeypatch.setattr(reader,"_valid_url",lambda url: url==direct["url"])
    assert asyncio.run(reader._resolve_from_index(google)) == direct["url"]


def test_cluster_and_paywall_exclusion():
    record = core.parse_rss(b'<rss><channel><item><title>Island election review</title><link>https://news.google.com/a</link>'
                            b'<description><![CDATA[<ol><li>Unrelated bribery charge</li></ol>]]></description></item></channel></rss>', "Goa")[0]
    assert record["description"] == ""
    with pytest.raises(ValueError, match="restricted"):
        reader._select_body('<script type="application/ld+json">{"isAccessibleForFree":false}</script>')


def test_fabricated_charge_with_real_quote_rejected():
    source={"title":"The board reviewed the application lodged by the director.","description":""}
    claim="The board reviewed a forgery application lodged by the director."
    raw=json.dumps({"claims":[{"claim_en":claim,"source":1,"quote":source["title"]}]})
    assert not chat_v07.validate_candidate_claims(raw,[source])[0]


def test_planner_keeps_distinct_legal_objectives():
    slots = research_insights.requested_topics("Explain the allegations, procedural history, reasoning, evidence and court outcome")
    assert {r["id"] for r in slots} >= {"allegations","procedure","reasoning","evidence","decision"}


def test_definition_and_event_implication_use_different_evidence():
    from app.chat_router_v1 import reference_definition
    assert "sets those proceedings aside" in reference_definition("What does quashing criminal proceedings mean?")
    assert reference_definition("What does quashing proceedings mean for his appointment?") is None


def test_freshness_search_reuses_prepared_evidence(monkeypatch):
    from app import conditional_search
    original = {"id":"99","title":"Valley district opens a volunteer centre"}
    prepared = {**original,"description":"Published passage","evidence_origin":"publisher_article"}
    monkeypatch.setattr(conditional_search, "should_fetch", lambda q: True)
    async def empty(*args): return b"<rss><channel/></rss>"
    monkeypatch.setattr(core, "fetch_rss", empty)
    for _ in range(2):
        result = asyncio.run(conditional_search.maybe_enrich("Latest updates?", original, [prepared]))
        assert result[0] == prepared


def test_retry_transient_page_read(monkeypatch, tmp_path):
    import httpx
    monkeypatch.setattr(core, "DB_PATH", tmp_path / "news.db")
    reader.init_db()
    title = "Regional harbour restores the tidal monitoring network"
    url = "https://scroll.in/article/example"
    calls = []
    async def fetch(_url):
        calls.append(_url)
        if len(calls) == 1:
            raise httpx.ReadTimeout("temporary")
        return url, f"<title>{title}</title><article><p>{(title+' after repairs. ') * 16}</p></article>"
    monkeypatch.setattr(reader, "_fetch_publisher_page", fetch)
    row = asyncio.run(reader._retrieve({"id":"retry","publisher":"Scroll.in","url":url,"title":title}))
    assert row["status"] == "ready" and calls == [url, url]

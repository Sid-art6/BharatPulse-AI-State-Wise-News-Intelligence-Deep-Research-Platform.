from app.core import clean_title, fingerprint, find_related, parse_rss, relevance_score, rss_url_for_query
from app.regions import classify_topic, infer_region, REGIONS

RSS = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Example RSS</title>
<item><title>Karnataka government reviews rail plan - Newsroom A</title>
<link>https://news.google.com/rss/articles/test-one</link>
<description>&lt;p&gt;Karnataka public transit review.&lt;/p&gt;</description>
<pubDate>Mon, 23 Nov 2026 08:00:00 GMT</pubDate><source>Newsroom A</source></item>
<item><title>Invalid URL record</title><link>javascript:alert(1)</link></item>
</channel></rss>'''


def test_rss_metadata_and_region():
    rows = parse_rss(RSS, "Karnataka")
    assert len(rows) == 1
    assert rows[0]["publisher"] == "Newsroom A"
    assert rows[0]["title"] == "Karnataka government reviews rail plan"
    assert rows[0]["region"] == "Karnataka"
    assert rows[0]["region_confidence"] == "explicit"
    assert rows[0]["topic"] == "Policy"  # topic rule is ordered
    assert rows[0]["url"].startswith("https://")
    assert "<p>" not in rows[0]["description"]


def test_never_guess_region_without_mention():
    assert infer_region("The cabinet met to discuss priorities", "Karnataka") == ("All India", "not_verified")
    assert infer_region("Delhi and Bihar leadership meeting", "Delhi") == ("Delhi", "explicit")


def test_rss_parser_rejects_malformed():
    import pytest
    with pytest.raises(ValueError):
        parse_rss(b"not RSS", "All India")


def test_canonical_titles_for_dedup():
    assert fingerprint("Headline about Karnataka - Publisher 1") == fingerprint("Headline about Karnataka - Publisher 2")


def test_feed_origin_is_fixed():
    url = rss_url_for_query('"Karnataka" India news when:7d')
    assert url.startswith("https://news.google.com/rss/search?")
    assert "%22" in url


def test_relevance_and_related():
    first = {"id": "a", "fingerprint": "a", "title": "Kerala coastal conservation proposal", "description": "", "published_at": "2026-11-22", "is_demo": 0}
    related = {"id": "b", "fingerprint": "b", "title": "Kerala conservation plan for the coast", "description": "", "published_at": "2026-11-22", "is_demo": 0}
    unrelated = {"id": "c", "fingerprint": "c", "title": "New bank lending programme", "description": "", "published_at": "2026-11-22", "is_demo": 0}
    assert relevance_score(first["title"], related["title"]) > .17
    assert [a["id"] for a in find_related(first, [related, unrelated])] == ["b"]


def test_regions_count():
    assert len(REGIONS) == 37  # All India + 28 states + 8 UTs


def test_multilingual_headlines_have_distinct_fingerprints():
    assert fingerprint("कर्नाटक में बारिश") != fingerprint("महाराष्ट्र में निवेश")
    assert fingerprint("தமிழ்நாட்டில் மழை") != fingerprint("கர்நாடகாவில் மழை")


def test_native_script_state_matching_and_language():
    from app.regions import detect_language
    assert infer_region("ಕರ್ನಾಟಕದಲ್ಲಿ ಸುದ್ದಿ", "Karnataka")[0] == "Karnataka"
    assert infer_region("दिल्ली में नई नीति", "Delhi")[0] == "Delhi"
    assert detect_language("தமிழ்நாட்டில் மழை", "Tamil Nadu") == "Tamil"
    assert detect_language("കേരളത്തിൽ മഴ", "Kerala") == "Malayalam"


def test_regional_rss_metadata_preserves_original_language():
    xml = '''<rss><channel><item>
        <title>ಕರ್ನಾಟಕದಲ್ಲಿ ಹೊಸ ಯೋಜನೆ - Local Paper</title>
        <link>https://local.example/news/123</link>
        <description>ಕರ್ನಾಟಕದಲ್ಲಿ ಸರ್ಕಾರಿ ಯೋಜನೆ</description>
        <source>Local Paper</source>
    </item></channel></rss>'''.encode("utf-8")
    rows = parse_rss(xml, "Karnataka")
    assert rows[0]["language"] == "Kannada"
    assert rows[0]["region"] == "Karnataka"
    assert rows[0]["summary_en"] == ""  # No invented English translation.


def test_english_preview_uses_original_excerpt_when_available():
    xml = '''<rss><channel><item>
        <title>Karnataka cabinet announces meeting</title>
        <link>https://local.example/news/124</link>
        <description>Karnataka ministers are meeting.</description>
    </item></channel></rss>'''.encode("utf-8")
    rows = parse_rss(xml, "Karnataka")
    assert rows[0]["language"] == "English"
    assert rows[0]["summary_en"] == "Karnataka ministers are meeting."


def test_poll_default_five_minutes(monkeypatch):
    from app.live import _poll_seconds
    monkeypatch.delenv("BHARATPULSE_POLL_SECONDS", raising=False)
    assert _poll_seconds() == 300
    monkeypatch.setenv("BHARATPULSE_POLL_SECONDS", "90")
    assert _poll_seconds() == 300


def test_selected_response_language_and_no_evidence_message(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import core, ai
    monkeypatch.setattr(core, "DATA_DIR", tmp_path)
    monkeypatch.setattr(core, "DB_PATH", tmp_path / "test.db")
    with TestClient(app) as client:
        metadata = client.get("/api/meta").json()
        assert metadata["auto_refresh_seconds"] == 300
        assert "Kannada" in metadata["response_languages"]
        item = client.get("/api/news", params={"demo": "true"}).json()["items"][0]
        answer = client.post("/api/chat", json={"article_id": item["id"], "question": "Any actual report?", "language": "Hindi"})
        assert answer.status_code == 200
        assert ai.no_information_message("Hindi") in answer.json()["answer"]
        invalid = client.post("/api/chat", json={"article_id": item["id"], "question": "Any report?", "language": "Klingon"})
        assert invalid.status_code == 422

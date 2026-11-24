"""Curated, fixed direct RSS section feeds for BharatPulse v0.10.

Source: publisher's own public RSS index, https://indianexpress.com/rss/

This is feed *discovery*, not a licence to republish article text. Only RSS
metadata/excerpts are indexed and original publisher URLs are linked. Region
section metadata is weaker than an explicit place mention in an article.

Every URL is hardcoded here. Never accept user-supplied fetch URLs.
Availability and content vary; no coverage guarantee is made.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedSpec:
    name: str
    url: str
    section_region: str  # fixed official publisher RSS section location


ORIGIN = "https://indianexpress.com"

# One conservative direct-feed request per watched region per five-minute poll.
# These sections are listed in The Indian Express's own RSS directory.
REGION_FEEDS: dict[str, FeedSpec] = {
    "All India": FeedSpec("The Indian Express", f"{ORIGIN}/section/india/feed/", "All India"),
    "Arunachal Pradesh": FeedSpec("The Indian Express", f"{ORIGIN}/section/north-east-india/arunachal-pradesh/feed/", "Arunachal Pradesh"),
    "Assam": FeedSpec("The Indian Express", f"{ORIGIN}/section/north-east-india/assam/feed/", "Assam"),
    "Bihar": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/patna/feed/", "Bihar"),
    "Chandigarh": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/chandigarh/feed/", "Chandigarh"),
    "Delhi": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/delhi/feed/", "Delhi"),
    "Goa": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/goa/feed/", "Goa"),
    "Gujarat": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/ahmedabad/feed/", "Gujarat"),
    "Himachal Pradesh": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/shimla/feed/", "Himachal Pradesh"),
    "Jammu and Kashmir": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/srinagar/feed/", "Jammu and Kashmir"),
    "Karnataka": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/bangalore/feed/", "Karnataka"),
    "Kerala": FeedSpec("The Indian Express", f"{ORIGIN}/section/india/kerala/feed/", "Kerala"),
    "Madhya Pradesh": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/bhopal/feed/", "Madhya Pradesh"),
    "Maharashtra": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/mumbai/feed/", "Maharashtra"),
    "Manipur": FeedSpec("The Indian Express", f"{ORIGIN}/section/north-east-india/manipur/feed/", "Manipur"),
    "Meghalaya": FeedSpec("The Indian Express", f"{ORIGIN}/section/north-east-india/meghalaya/feed/", "Meghalaya"),
    "Mizoram": FeedSpec("The Indian Express", f"{ORIGIN}/section/north-east-india/mizoram/feed/", "Mizoram"),
    "Nagaland": FeedSpec("The Indian Express", f"{ORIGIN}/section/north-east-india/nagaland/feed/", "Nagaland"),
    "Punjab": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/jalandhar/feed/", "Punjab"),
    "Rajasthan": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/jaipur/feed/", "Rajasthan"),
    "Tamil Nadu": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/chennai/feed/", "Tamil Nadu"),
    "Telangana": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/hyderabad/feed/", "Telangana"),
    "Tripura": FeedSpec("The Indian Express", f"{ORIGIN}/section/north-east-india/tripura/feed/", "Tripura"),
    "Uttar Pradesh": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/lucknow/feed/", "Uttar Pradesh"),
    "West Bengal": FeedSpec("The Indian Express", f"{ORIGIN}/section/cities/kolkata/feed/", "West Bengal"),
}


def feed_for_region(region: str) -> FeedSpec | None:
    return REGION_FEEDS.get(region)

# Secondary publisher-hosted RSS feeds listed as active by Feeder in Oct 2026.
# These four URLs have not been independently live-tested in this build.
# Reference: https://feeder.co/knowledge-base/rss-content/the-hindu-rss-feeds/
HINDU_FEEDS: dict[str, FeedSpec] = {
    "All India": FeedSpec("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss", "All India"),
    "Karnataka": FeedSpec("The Hindu", "https://www.thehindu.com/news/national/karnataka/feeder/default.rss", "Karnataka"),
    "Kerala": FeedSpec("The Hindu", "https://www.thehindu.com/news/national/kerala/feeder/default.rss", "Kerala"),
    "Tamil Nadu": FeedSpec("The Hindu", "https://www.thehindu.com/news/national/tamil-nadu/feeder/default.rss", "Tamil Nadu"),
}


def feeds_for_region(region: str) -> tuple[FeedSpec, ...]:
    """0–2 fixed publisher-hosted sections for a watched region."""
    return tuple(spec for spec in (REGION_FEEDS.get(region), HINDU_FEEDS.get(region)) if spec)

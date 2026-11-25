"""Prevent external publisher requests in ordinary hermetic unit tests.

Article-context tests explicitly exercise the real module with mocked HTTP.
"""
import pytest


@pytest.fixture(autouse=True)
def disable_publisher_fetch_during_unrelated_tests(request, monkeypatch):
    from app import publisher_feed
    async def no_network_feed(_url):
        return []
    monkeypatch.setattr(publisher_feed, "_items", no_network_feed)
    if request.node.path.name == 'test_article_context_v14.py':
        return
    from app import article_context

    async def no_publisher_fetch(_article, timeout=22.0):
        return {}

    monkeypatch.setattr(article_context, 'ensure', no_publisher_fetch)

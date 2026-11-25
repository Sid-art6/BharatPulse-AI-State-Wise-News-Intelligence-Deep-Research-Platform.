"""Security regression tests for the optional BharatPulse v1.0 public demo."""

from fastapi.testclient import TestClient
from app.main import app
from app import public_safety
from app.live import monitor


def test_security_headers_present_on_home_and_api():
    with TestClient(app) as c:
        for uri in ('/', '/api/health'):
            r=c.get(uri)
            assert r.status_code == 200
            assert r.headers['x-content-type-options'] == 'nosniff'
            assert r.headers['x-frame-options'] == 'DENY'
            assert "object-src 'none'" in r.headers['content-security-policy']
            assert 'frame-ancestors' in r.headers['content-security-policy']


def test_public_ai_disabled_by_default(monkeypatch):
    monkeypatch.setenv('BHARATPULSE_PUBLIC_MODE', 'true')
    monkeypatch.delenv('BHARATPULSE_PUBLIC_AI_ENABLED', raising=False)
    with TestClient(app) as c:
        r=c.post('/api/ai/check')
        assert r.status_code == 503
        assert 'disabled' in r.json()['detail']
        meta=c.get('/api/meta').json()
        assert meta['public_demo'] is True
        assert meta['public_ai_enabled'] is False
        assert meta['llm_configured'] is False
        assert meta['llm_provider'] == 'none'


def test_public_origin_validation(monkeypatch):
    monkeypatch.setenv('BHARATPULSE_PUBLIC_MODE', 'true')
    with TestClient(app) as c:
        r=c.post('/api/news/watch',headers={'origin':'https://attacker.example'},json={'region':'All India'})
        assert r.status_code == 403


def test_request_size_guard():
    with TestClient(app) as c:
        r=c.post('/api/news/watch',headers={'content-length':'32768'},content='{}')
        assert r.status_code == 413


def test_limiter_caps_public_automated_refreshes(monkeypatch):
    monkeypatch.setenv('BHARATPULSE_PUBLIC_MODE', 'true')
    monkeypatch.setattr(public_safety, 'limiter', public_safety.SlidingWindowLimiter())
    monkeypatch.setattr(monitor, 'watch', lambda region: None)
    with TestClient(app) as c:
        for i in range(24):
            assert c.post('/api/news/watch',json={'region':'All India'}).status_code == 200
        r=c.post('/api/news/watch',json={'region':'All India'})
        assert r.status_code == 429
        assert r.headers['retry-after'] == '3600'

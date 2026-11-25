"""Small, bounded public-demo protections; no user identity or cookies collected.

This is one-process in-memory rate limiting, suitable for a low-traffic demo.
For a scaled service use an edge WAF, distributed quotas, authentication and
persistent audit telemetry. Never trust unverified X-Forwarded-For headers.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse


def enabled(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# Only externally reachable endpoints with paid/expensive provider calls.
AI_PATHS = ("/api/research/", "/api/chat", "/api/weather/chat", "/api/ai/check", "/api/article-context/")
MAX_POST_BYTES = 16384
PUBLIC_AI_GLOBAL_HOURLY_LIMIT = 30  # Hard stop per running worker, independent of client-IP sharing.
WRITE_PATHS = ("/api/news/watch", "/api/news/refresh")
READ_PATHS = ("/api/news", "/api/news/status", "/api/weather/forecast", "/api/weather/map", "/api/chat/history")
HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; script-src 'self' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org https://unpkg.com; "
        "connect-src 'self'"
    ),
}


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, ip: str, group: str, max_calls: int, window_seconds: int = 3600) -> bool:
        now = time.monotonic()
        with self._lock:
            # Bound idle-key growth from rotating client IPs on a long-running service.
            if len(self._events) > 10000:
                self._events = defaultdict(deque, {
                    key: logs for key, logs in self._events.items()
                    if logs and logs[-1] > now - window_seconds
                })
            logs = self._events[(ip, group)]
            while logs and logs[0] <= now - window_seconds:
                logs.popleft()
            if len(logs) >= max_calls:
                return False
            logs.append(now)
            return True


limiter = SlidingWindowLimiter()


def _ip(request: Request) -> str:
    # ASGI server's trusted connection address. Do not read X-Forwarded-For.
    return request.client.host if request.client else 'unidentified'


async def public_safety_middleware(request: Request, call_next):
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and request.url.path.startswith('/api/'):
        length = request.headers.get('content-length', '0')
        if length and (not length.isdigit() or int(length) > MAX_POST_BYTES):
            return _respond({'detail': 'Request body is too large or has invalid length.'}, 413)
        # Content-Length can be missing (chunked) or dishonest. Stream with a
        # hard cap before request parsing; cache bounded bytes for FastAPI.
        chunks, received = [], 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_POST_BYTES:
                return _respond({'detail': 'Request body exceeds the allowed limit.'}, 413)
            chunks.append(chunk)
        request._body = b''.join(chunks)
        if enabled('BHARATPULSE_PUBLIC_MODE'):
            origin = request.headers.get('origin')
            if origin:
                # Browsers send Origin on fetch POST; enforce same-origin only.
                local_origin = f'{request.url.scheme}://{request.url.netloc}'
                public_origin = f'https://{request.headers.get("host", "")}'
                configured = {x.strip().rstrip('/') for x in os.getenv('BHARATPULSE_ALLOWED_ORIGINS', '').split(',') if x.strip()}
                if origin not in ({local_origin, public_origin} | configured):
                    return _respond({'detail': 'Cross-origin write requests are not permitted.'}, 403)
            ip = _ip(request)
            path = request.url.path
            if any(path == p or (p.endswith('/') and path.startswith(p)) for p in AI_PATHS):
                if not enabled('BHARATPULSE_PUBLIC_AI_ENABLED'):
                    return _respond({'detail': 'Public AI requests are disabled for this demo. News and weather browsing remain available.'}, 503)
                if not limiter.check(ip, 'ai', 6):
                    return _respond({'detail': 'Public AI demo quota reached. Try again later.'}, 429, {'Retry-After': '3600'})
                if not limiter.check('GLOBAL', 'ai_budget', PUBLIC_AI_GLOBAL_HOURLY_LIMIT):
                    return _respond({'detail': 'The shared public AI budget for this demo is exhausted. Try again later.'}, 429, {'Retry-After': '3600'})
            elif path in WRITE_PATHS:
                if not limiter.check(ip, 'rss', 24) or not limiter.check('GLOBAL', 'rss_budget', 120):
                    return _respond({'detail': 'RSS refresh quota reached. Use cached articles.'}, 429, {'Retry-After': '3600'})
            elif not limiter.check(ip, 'other_post', 100):
                return _respond({'detail': 'Request quota reached.'}, 429, {'Retry-After': '3600'})
    if request.method == 'GET' and enabled('BHARATPULSE_PUBLIC_MODE') and (
        request.url.path in READ_PATHS or request.url.path.startswith('/api/article-context/')):
        ip = _ip(request)
        if not limiter.check(ip, 'read', 240) or not limiter.check('GLOBAL', 'read_budget', 1800):
            return _respond({'detail': 'Public demo read quota reached. Try again later.'}, 429, {'Retry-After': '3600'})
    response = await call_next(request)
    for key, value in HEADERS.items():
        response.headers[key] = value
    return response


def _respond(data: dict, status: int, extra: dict[str, str] | None = None) -> JSONResponse:
    r = JSONResponse(data, status_code=status, headers=extra)
    for k, v in HEADERS.items():
        r.headers[k] = v
    return r

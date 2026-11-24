"""Bounded RSS polling for the local-first BharatPulse prototype.

There are no provider push notifications: this checks feeds on a configurable
interval. The national feed is polled while the API is running; additional
regions are polled only while a browser has recently requested them.
"""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import suppress
from datetime import datetime, timezone

import httpx

from . import ai, core


def _poll_seconds() -> int:
    try:
        value = int(os.getenv("BHARATPULSE_POLL_SECONDS", "300"))
    except ValueError:
        value = 300
    return max(300, min(value, 3600))


class NewsMonitor:
    def __init__(self) -> None:
        self.poll_seconds = _poll_seconds()
        self.watched: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._semaphore = asyncio.Semaphore(1)  # Respect feed providers
        self._loop_task: asyncio.Task | None = None
        self._pending: set[asyncio.Task] = set()

    def start(self) -> None:
        self.poll_seconds = _poll_seconds()
        self.watched.clear()
        self._loop_task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task
            self._loop_task = None
        for task in tuple(self._pending):
            task.cancel()
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)
        self._pending.clear()
        self.watched.clear()

    def watch(self, region: str) -> None:
        self.watched[region] = time.monotonic() + 1800  # 30-minute lease
        self.schedule_if_due(region)

    def status(self, region: str) -> dict:
        record = core.get_refresh_state(region)
        recent = self.watched.get(region, 0) > time.monotonic()
        return {
            "region": region,
            "provider": "Google News RSS + curated direct publisher RSS (where configured) + BBC India RSS (national)",
            "poll_seconds": self.poll_seconds,
            "watched": recent or region == "All India",
            "refreshing": self._locks.get(region, asyncio.Lock()).locked(),
            "last_attempt": record.get("last_attempt"),
            "last_success": record.get("last_success"),
            "last_error": record.get("last_error"),
            "fetched": record.get("fetched", 0),
            "added": record.get("added", 0),
            "filter_mode": record.get("filter_mode"),
        }

    def is_due(self, region: str) -> bool:
        record = core.get_refresh_state(region)
        if not record.get("last_attempt"):
            return True
        try:
            checked = datetime.fromisoformat(record["last_attempt"])
            return (datetime.now(timezone.utc) - checked).total_seconds() >= self.poll_seconds
        except (ValueError, TypeError):
            return True

    def schedule_if_due(self, region: str) -> None:
        if not self.is_due(region) or self._locks.setdefault(region, asyncio.Lock()).locked():
            return
        if any(getattr(task, "_bharatpulse_region", None) == region for task in self._pending):
            return
        task = asyncio.create_task(self.refresh(region))
        # Attach a small marker so multiple browsers cannot queue duplicates.
        task._bharatpulse_region = region  # type: ignore[attr-defined]
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        task.add_done_callback(self._log_task_error)

    @staticmethod
    def _log_task_error(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        # Failures are persisted to status; consume the exception so the event
        # loop does not emit "Task exception was never retrieved".
        task.exception()

    async def refresh(self, region: str, *, force: bool = False) -> dict:
        lock = self._locks.setdefault(region, asyncio.Lock())
        if lock.locked() or (not force and not self.is_due(region)):
            return {"fetched": 0, "added": 0, "skipped": True, "filter_mode": "not_due", "message": "Feed check already running or not due yet."}
        async with lock:
            core.record_refresh_attempt(region)
            try:
                async with self._semaphore:
                    articles = await core.fetch_news(region)
                    fresh = core.unseen_articles(articles)
                    if fresh:
                        filtered, mode = await ai.optional_llm_filter(fresh)
                        if mode.startswith("groq_filtered_") or mode.startswith("ollama_filtered_"):
                            core.remember_rejected_headlines(fresh, filtered)
                    else:
                        filtered, mode = [], "no_new_headlines"
                    # Store articles promptly, before optional (slower) local
                    # translation. Never replace original publisher text.
                    added = core.save_articles(filtered)
                    pending = core.pending_english_previews(filtered)
                    previews = await ai.english_previews(pending)
                    core.save_english_summaries(previews)
                    core.record_refresh_result(region, fetched=len(articles), added=added, filter_mode=mode)
                return {
                    "fetched": len(articles), "added": added, "skipped": False,
                    "filter_mode": mode,
                    "message": "Live RSS feed check complete; new headlines saved." if articles else "The provider returned no items.",
                }
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                core.record_refresh_error(region, f"{type(exc).__name__}: {str(exc)[:160]}")
                raise

    async def _run(self) -> None:
        # Check the national feed immediately when the app starts. Browsers
        # watching another state schedule that state immediately as well.
        while True:
            now = time.monotonic()
            active = ["All India", *(r for r, expiry in self.watched.items() if expiry > now and r != "All India")]
            self.watched = {r: expiry for r, expiry in self.watched.items() if expiry > now}
            for region in active:
                self.schedule_if_due(region)
            await asyncio.sleep(30)


monitor = NewsMonitor()

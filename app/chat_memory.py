"""Small, bounded first-party conversation memory for article chats.

No embeddings, extra LLM calls, third-party memory provider, or user profiles.
The opaque browser cookie is a bearer credential; only its SHA-256 digest is
stored server-side. Memory is isolated by session AND selected article.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from . import core

COOKIE_NAME = "bharatpulse_session"
MAX_HISTORY_TURNS = 5
RETENTION_HOURS = 24
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,100}$")


def new_session() -> str:
    return secrets.token_urlsafe(32)


def valid_session(token: str | None) -> bool:
    return bool(token and TOKEN_PATTERN.fullmatch(token))


def digest(token: str) -> str:
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def _cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)).isoformat(timespec='seconds')


def init_db() -> None:
    with core.db_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS chat_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_digest TEXT NOT NULL,
                article_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chat_session_article
            ON chat_turns(session_digest, article_id, id);
            CREATE INDEX IF NOT EXISTS idx_chat_expiry ON chat_turns(created_at);
        """)
        conn.execute('DELETE FROM chat_turns WHERE created_at < ?', (_cutoff(),))


def read_turns(token: str, article_id: str, limit: int = MAX_HISTORY_TURNS) -> list[dict[str, Any]]:
    if not valid_session(token):
        return []
    with core.db_conn() as conn:
        rows = conn.execute('''
            SELECT question, answer, created_at FROM chat_turns
            WHERE session_digest=? AND article_id=? AND created_at>=?
            ORDER BY id DESC LIMIT ?
        ''', (digest(token), article_id, _cutoff(), max(1, min(limit, MAX_HISTORY_TURNS)))).fetchall()
    return [dict(row) for row in reversed(rows)]


def save_turn(token: str, article_id: str, question: str, answer: str) -> None:
    if not valid_session(token):
        return
    with core.db_conn() as conn:
        conn.execute('DELETE FROM chat_turns WHERE created_at < ?', (_cutoff(),))
        conn.execute('''INSERT INTO chat_turns(session_digest, article_id, created_at, question, answer)
                        VALUES (?, ?, ?, ?, ?)''',
                     (digest(token), article_id, core.utcnow(), question[:1200], answer[:1600]))
        # Only the newest turns are retained even if the user keeps chatting.
        conn.execute('''DELETE FROM chat_turns WHERE session_digest=? AND article_id=?
                        AND id NOT IN (
                            SELECT id FROM chat_turns WHERE session_digest=? AND article_id=?
                            ORDER BY id DESC LIMIT ?
                        )''', (digest(token), article_id, digest(token), article_id, MAX_HISTORY_TURNS))


def clear_turns(token: str, article_id: str) -> int:
    if not valid_session(token):
        return 0
    with core.db_conn() as conn:
        cursor = conn.execute('DELETE FROM chat_turns WHERE session_digest=? AND article_id=?',
                              (digest(token), article_id))
        return cursor.rowcount


def last_context(history: list[dict[str, Any]]) -> str:
    """User questions give referents, never authoritative news evidence.

    Model-generated history is intentionally NOT fed back as fact: earlier
    answers may contain mistakes. The current selected RSS remains the source.
    """
    return '\n'.join('Earlier user question: ' + row['question'][:200]
                     for row in history[-3:])[:700]

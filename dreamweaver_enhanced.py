"""Core service layer for DreamWeaver N1.

This module is UI-agnostic: it owns persistence (SQLite), the Targeted Memory
Reactivation (TMR) session lifecycle, dream recording/playback modelling and the
Grok "dream coach" client (including streaming). The Flask layer in ``app.py``
is a thin adapter over the classes defined here, which keeps the business logic
fully unit-testable without a running web server or network access.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional
from urllib.parse import urlparse

import requests

DEFAULT_DB_PATH = os.environ.get("DREAMWEAVER_DB", "dreams.db")
GROK_API_URL = os.environ.get("GROK_API_URL", "https://api.x.ai/v1/chat/completions")
GROK_MODEL = os.environ.get("GROK_MODEL", "grok-4.5")
VIDEO_EXTENSIONS = (".mp4", ".webm", ".ogv", ".ogg")
IMAGE_EXTENSIONS = (".gif", ".webp", ".png", ".jpg", ".jpeg")


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string (seconds precision)."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class DreamWeaverError(Exception):
    """Base class for expected, user-facing errors raised by the service layer."""


class ValidationError(DreamWeaverError):
    """Raised when caller-supplied data fails validation."""


class NotFoundError(DreamWeaverError):
    """Raised when a requested record does not exist."""


class GrokError(DreamWeaverError):
    """Raised when the Grok API is misconfigured or returns an error."""


@dataclass
class Dream:
    """A recorded dream intention and its playback scene."""

    id: Optional[int]
    title: str
    intention: str
    scene: str
    media_url: str = ""
    created_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def media_kind(self) -> str:
        path = urlparse(self.media_url).path.lower()
        if path.endswith(VIDEO_EXTENSIONS):
            return "video"
        if path.endswith(IMAGE_EXTENSIONS):
            return "image"
        return ""


@dataclass
class TMRSession:
    """A Targeted Memory Reactivation cueing session bound to a dream."""

    id: Optional[int]
    dream_id: int
    status: str
    cue_count: int
    started_at: str
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class DreamStore:
    """SQLite-backed persistence for dreams and TMR sessions.

    A single instance owns one connection. ``check_same_thread=False`` allows the
    store to be shared across Flask's worker threads; all writes are small and
    serialized by SQLite's own locking.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dreams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                title TEXT NOT NULL,
                intention TEXT NOT NULL,
                scene TEXT NOT NULL DEFAULT '',
                media_url TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS tmr_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dream_id INTEGER NOT NULL REFERENCES dreams(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'active',
                cue_count INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                completed_at TEXT
            );
            """
        )
        columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(dreams)")
        }
        if "media_url" not in columns:
            self.conn.execute(
                "ALTER TABLE dreams ADD COLUMN media_url TEXT NOT NULL DEFAULT ''"
            )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- dreams -----------------------------------------------------------

    def add_dream(
        self,
        title: str,
        intention: str,
        scene: str = "",
        media_url: str = "",
    ) -> Dream:
        title = (title or "").strip()
        intention = (intention or "").strip()
        if not title:
            raise ValidationError("Dream title is required.")
        if not intention:
            raise ValidationError("Dream intention is required.")
        media_url = normalize_media_url(media_url)
        created_at = utcnow_iso()
        cur = self.conn.execute(
            "INSERT INTO dreams (created_at, title, intention, scene, media_url) "
            "VALUES (?, ?, ?, ?, ?)",
            (created_at, title, intention, scene or "", media_url),
        )
        self.conn.commit()
        return Dream(
            id=cur.lastrowid,
            title=title,
            intention=intention,
            scene=scene or "",
            media_url=media_url,
            created_at=created_at,
        )

    def get_dream(self, dream_id: int) -> Dream:
        row = self.conn.execute(
            "SELECT * FROM dreams WHERE id = ?", (dream_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Dream {dream_id} not found.")
        return self._row_to_dream(row)

    def list_dreams(self, limit: int = 50) -> "list[Dream]":
        rows = self.conn.execute(
            "SELECT * FROM dreams ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_dream(r) for r in rows]

    @staticmethod
    def _row_to_dream(row: sqlite3.Row) -> Dream:
        return Dream(
            id=row["id"],
            title=row["title"],
            intention=row["intention"],
            scene=row["scene"],
            media_url=row["media_url"],
            created_at=row["created_at"],
        )

    # -- TMR sessions -----------------------------------------------------

    def start_tmr_session(self, dream_id: int) -> TMRSession:
        # Raises NotFoundError if the dream is missing.
        self.get_dream(dream_id)
        started_at = utcnow_iso()
        cur = self.conn.execute(
            "INSERT INTO tmr_sessions (dream_id, status, cue_count, started_at) "
            "VALUES (?, 'active', 0, ?)",
            (dream_id, started_at),
        )
        self.conn.commit()
        return TMRSession(
            id=cur.lastrowid,
            dream_id=dream_id,
            status="active",
            cue_count=0,
            started_at=started_at,
        )

    def record_cue(self, session_id: int) -> TMRSession:
        session = self.get_tmr_session(session_id)
        if session.status != "active":
            raise ValidationError("Cannot cue a session that is not active.")
        self.conn.execute(
            "UPDATE tmr_sessions SET cue_count = cue_count + 1 WHERE id = ?",
            (session_id,),
        )
        self.conn.commit()
        return self.get_tmr_session(session_id)

    def complete_tmr_session(self, session_id: int) -> TMRSession:
        session = self.get_tmr_session(session_id)
        if session.status == "completed":
            return session
        self.conn.execute(
            "UPDATE tmr_sessions SET status = 'completed', completed_at = ? "
            "WHERE id = ?",
            (utcnow_iso(), session_id),
        )
        self.conn.commit()
        return self.get_tmr_session(session_id)

    def get_tmr_session(self, session_id: int) -> TMRSession:
        row = self.conn.execute(
            "SELECT * FROM tmr_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"TMR session {session_id} not found.")
        return self._row_to_session(row)

    def list_tmr_sessions(self, limit: int = 20) -> "list[TMRSession]":
        rows = self.conn.execute(
            "SELECT * FROM tmr_sessions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> TMRSession:
        return TMRSession(
            id=row["id"],
            dream_id=row["dream_id"],
            status=row["status"],
            cue_count=row["cue_count"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )


def normalize_media_url(media_url: str) -> str:
    media_url = (media_url or "").strip()
    if not media_url:
        return ""
    parsed = urlparse(media_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError("Media URL must be a public HTTP or HTTPS URL.")
    path = parsed.path.lower()
    if not path.endswith(VIDEO_EXTENSIONS + IMAGE_EXTENSIONS):
        raise ValidationError(
            "Media URL must point to an MP4, WebM, Ogg, GIF, WebP, PNG, or JPEG file."
        )
    return media_url


def build_coach_prompt(question: str, intention: Optional[str] = None) -> "list[dict]":
    """Construct a chat-completion message list for the Grok dream coach.

    The system prompt frames Grok as an evidence-aware lucid-dreaming coach; the
    optional ``intention`` grounds the advice in the user's current dream goal.
    """

    question = (question or "").strip()
    if not question:
        raise ValidationError("A question is required to consult the coach.")
    system = (
        "You are DreamWeaver's evidence-aware lucid dreaming and TMR coach. "
        "Respond with three short sections: Tonight's plan, Dream cue, and "
        "Morning recall. Give concrete, personalized steps for dream recall, "
        "reality checks, MILD, and Targeted Memory Reactivation when relevant. "
        "Separate established sleep guidance from experimental ideas, never "
        "promise lucidity, avoid advice that disrupts healthy sleep, and never "
        "give medical advice."
    )
    messages = [{"role": "system", "content": system}]
    if intention and intention.strip():
        messages.append(
            {
                "role": "system",
                "content": f"The dreamer's current intention is: {intention.strip()}",
            }
        )
    messages.append({"role": "user", "content": question})
    return messages


class GrokCoach:
    """Client for the Grok chat-completions API with streaming support."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: str = GROK_API_URL,
        model: str = GROK_MODEL,
        session: Optional[requests.Session] = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("GROK_API_KEY", "")
            if not api_key or api_key == "YOUR_XAI_API_KEY_HERE":
                api_key = os.environ.get("XAI_API_KEY", "")
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.session = session or requests.Session()

    @property
    def is_configured(self) -> bool:
        key = self.api_key
        return bool(key) and key != "YOUR_XAI_API_KEY_HERE"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def ask(self, question: str, intention: Optional[str] = None) -> str:
        """Return a single, non-streamed coach reply."""

        if not self.is_configured:
            raise GrokError("Grok API key is not configured.")
        messages = build_coach_prompt(question, intention)
        try:
            response = self.session.post(
                self.api_url,
                headers=self._headers(),
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise GrokError("Unable to reach the Grok API.") from exc
        if response.status_code >= 400:
            raise GrokError(f"Grok API error ({response.status_code}).")
        try:
            data = response.json()
        except requests.JSONDecodeError as exc:
            raise GrokError("Grok API returned invalid JSON.") from exc
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GrokError("Unexpected Grok API response shape.") from exc

    def stream(self, question: str, intention: Optional[str] = None) -> Iterator[str]:
        """Yield incremental content tokens from a streamed coach reply."""

        if not self.is_configured:
            raise GrokError("Grok API key is not configured.")
        messages = build_coach_prompt(question, intention)
        try:
            response = self.session.post(
                self.api_url,
                headers=self._headers(),
                json={"model": self.model, "messages": messages, "stream": True},
                timeout=30,
                stream=True,
            )
        except requests.RequestException as exc:
            raise GrokError("Unable to reach the Grok API.") from exc
        if response.status_code >= 400:
            raise GrokError(f"Grok API error ({response.status_code}).")
        try:
            yield from parse_sse_stream(response.iter_lines())
        except requests.RequestException as exc:
            raise GrokError("The Grok API stream was interrupted.") from exc


def parse_sse_stream(lines: Iterable) -> Iterator[str]:
    """Parse an OpenAI/Grok-style ``text/event-stream`` into content tokens.

    Each event line looks like ``data: {json}``; a terminal ``data: [DONE]``
    marks the end of the stream. Malformed payloads are skipped so a single bad
    chunk cannot abort the whole response.
    """

    for raw in lines:
        if raw is None:
            continue
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        line = raw.strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if payload == "[DONE]":
            break
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        try:
            delta = event["choices"][0]["delta"]
        except (KeyError, IndexError, TypeError):
            continue
        content = delta.get("content") if isinstance(delta, dict) else None
        if content:
            yield content

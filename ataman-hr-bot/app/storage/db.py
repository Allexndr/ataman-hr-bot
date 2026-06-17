from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    chat_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'choose_view',
    lang TEXT NOT NULL DEFAULT 'kk',
    profile_json TEXT NOT NULL DEFAULT '{}',
    clarify_attempts INTEGER NOT NULL DEFAULT 0,
    contact_name TEXT,
    interview_at INTEGER,
    interview_label TEXT,
    reminder_24_sent INTEGER NOT NULL DEFAULT 0,
    reminder_2_sent INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    body TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS stats (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sessions_interview ON sessions(interview_at);
"""


@dataclass
class Session:
    chat_id: str
    state: str
    lang: str = "kk"
    profile: dict[str, Any] = field(default_factory=dict)
    clarify_attempts: int = 0
    contact_name: str | None = None
    interview_at: int | None = None
    interview_label: str | None = None
    reminder_24_sent: bool = False
    reminder_2_sent: bool = False
    status: str = "new"
    updated_at: int = 0


class Store:
    def __init__(self, path: str):
        self.path = path
        self._ready = False

    async def init(self) -> None:
        if self._ready:
            return
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as conn:
            await conn.executescript(SCHEMA)
            await conn.commit()
        self._ready = True

    async def get_session(self, chat_id: str) -> Session:
        await self.init()
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM sessions WHERE chat_id = ?", (chat_id,)
            )
            row = await cur.fetchone()
        if not row:
            return Session(chat_id=chat_id, state="choose_view", updated_at=int(time.time()))
        return Session(
            chat_id=row["chat_id"],
            state=row["state"],
            lang=row["lang"] or "kk",
            profile=json.loads(row["profile_json"] or "{}"),
            clarify_attempts=row["clarify_attempts"] or 0,
            contact_name=row["contact_name"],
            interview_at=row["interview_at"],
            interview_label=row["interview_label"],
            reminder_24_sent=bool(row["reminder_24_sent"]),
            reminder_2_sent=bool(row["reminder_2_sent"]),
            status=row["status"] or "new",
            updated_at=row["updated_at"] or 0,
        )

    async def save_session(self, s: Session) -> None:
        await self.init()
        s.updated_at = int(time.time())
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                """
                INSERT INTO sessions (
                    chat_id, state, lang, profile_json, clarify_attempts, contact_name,
                    interview_at, interview_label, reminder_24_sent, reminder_2_sent,
                    status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    state=excluded.state, lang=excluded.lang, profile_json=excluded.profile_json,
                    clarify_attempts=excluded.clarify_attempts, contact_name=excluded.contact_name,
                    interview_at=excluded.interview_at, interview_label=excluded.interview_label,
                    reminder_24_sent=excluded.reminder_24_sent, reminder_2_sent=excluded.reminder_2_sent,
                    status=excluded.status, updated_at=excluded.updated_at
                """,
                (
                    s.chat_id,
                    s.state,
                    s.lang,
                    json.dumps(s.profile, ensure_ascii=False),
                    s.clarify_attempts,
                    s.contact_name,
                    s.interview_at,
                    s.interview_label,
                    int(s.reminder_24_sent),
                    int(s.reminder_2_sent),
                    s.status,
                    s.updated_at,
                ),
            )
            await conn.commit()

    async def reset_session(self, chat_id: str) -> Session:
        s = Session(chat_id=chat_id, state="choose_view", updated_at=int(time.time()))
        await self.save_session(s)
        return s

    async def log_message(self, chat_id: str, direction: str, body: str) -> None:
        await self.init()
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                "INSERT INTO messages (chat_id, direction, body, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, direction, body[:2000], int(time.time())),
            )
            await conn.commit()

    async def bump_stat(self, key: str, n: int = 1) -> None:
        await self.init()
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                """
                INSERT INTO stats (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = value + excluded.value
                """,
                (key, n),
            )
            await conn.commit()

    async def get_stats(self) -> dict[str, int]:
        await self.init()
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT key, value FROM stats")
            rows = await cur.fetchall()
        return {r["key"]: r["value"] for r in rows}

    async def due_reminders(self, now_ts: int) -> list[Session]:
        await self.init()
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT * FROM sessions
                WHERE interview_at IS NOT NULL
                  AND state IN ('confirm', 'schedule_interview', 'qa', 'welcome_qualified')
                  AND status NOT IN ('rejected', 'no_show')
                """
            )
            rows = await cur.fetchall()
        out: list[Session] = []
        for row in rows:
            s = Session(
                chat_id=row["chat_id"],
                state=row["state"],
                lang=row["lang"] or "kk",
                profile=json.loads(row["profile_json"] or "{}"),
                contact_name=row["contact_name"],
                interview_at=row["interview_at"],
                interview_label=row["interview_label"],
                reminder_24_sent=bool(row["reminder_24_sent"]),
                reminder_2_sent=bool(row["reminder_2_sent"]),
                status=row["status"] or "new",
            )
            if s.interview_at:
                out.append(s)
        _ = now_ts
        return out


_settings = get_settings()
store = Store(_settings.database_path)

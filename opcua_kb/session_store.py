"""SQLite-backed anonymous sessions, conversations, and RAG history."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class SessionStore:
    def __init__(self, path: str | Path, *, ttl_days: int = 30) -> None:
        if ttl_days <= 0:
            raise ValueError("ttl_days must be positive")
        self.path = Path(path)
        self.ttl_seconds = ttl_days * 24 * 60 * 60
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS anonymous_sessions (
                    id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES anonymous_sessions(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    mode TEXT,
                    retrieval_mode TEXT,
                    error TEXT,
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    retrieved_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_session_updated
                    ON conversations(session_id, archived, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
                    ON messages(conversation_id, created_at);
                """
            )

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def get_or_create_session(self, token: str | None) -> tuple[str, str, bool]:
        now = time.time()
        if token:
            with self._connection() as conn:
                row = conn.execute(
                    "SELECT id, expires_at FROM anonymous_sessions WHERE token_hash = ?",
                    (self._hash(token),),
                ).fetchone()
                if row and row["expires_at"] > now:
                    expires_at = now + self.ttl_seconds
                    conn.execute(
                        "UPDATE anonymous_sessions SET last_seen_at = ?, expires_at = ? WHERE id = ?",
                        (now, expires_at, row["id"]),
                    )
                    return row["id"], token, False
        new_token = secrets.token_urlsafe(32)
        session_id = uuid.uuid4().hex
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO anonymous_sessions(id, token_hash, created_at, last_seen_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, self._hash(new_token), now, now, now + self.ttl_seconds),
            )
        return session_id, new_token, True

    def create_conversation(self, session_id: str, title: str = "New Part 5 conversation") -> dict[str, Any]:
        now = time.time()
        conversation = {
            "id": uuid.uuid4().hex,
            "title": title.strip() or "New Part 5 conversation",
            "created_at": now,
            "updated_at": now,
            "archived": False,
        }
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO conversations(id, session_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conversation["id"],
                    session_id,
                    conversation["title"],
                    now,
                    now,
                ),
            )
        return conversation

    def list_conversations(self, session_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, title, created_at, updated_at, archived
                FROM conversations
                WHERE session_id = ? AND archived = 0
                ORDER BY updated_at DESC
                """,
                (session_id,),
            ).fetchall()
        return [self._conversation_row(row) for row in rows]

    def get_conversation(self, session_id: str, conversation_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, title, created_at, updated_at, archived
                FROM conversations
                WHERE id = ? AND session_id = ? AND archived = 0
                """,
                (conversation_id, session_id),
            ).fetchone()
            if row is None:
                return None
            messages = conn.execute(
                """
                SELECT id, role, content, mode, retrieval_mode, error,
                       citations_json, retrieved_json, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at, id
                """,
                (conversation_id,),
            ).fetchall()
        result = self._conversation_row(row)
        result["messages"] = [self._message_row(message) for message in messages]
        return result

    def append_message(
        self,
        session_id: str,
        conversation_id: str,
        *,
        role: str,
        content: str,
        mode: str | None = None,
        retrieval_mode: str | None = None,
        error: str | None = None,
        citations: list[dict[str, Any]] | None = None,
        retrieved: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if role not in {"user", "assistant"}:
            raise ValueError("role must be user or assistant")
        now = time.time()
        message = {
            "id": uuid.uuid4().hex,
            "role": role,
            "content": content,
            "mode": mode,
            "retrieval_mode": retrieval_mode,
            "error": error,
            "citations": citations or [],
            "retrieved": retrieved or [],
            "created_at": now,
        }
        with self._connection() as conn:
            owned = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ? AND session_id = ? AND archived = 0",
                (conversation_id, session_id),
            ).fetchone()
            if owned is None:
                return None  # type: ignore[return-value]
            conn.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, role, content, mode, retrieval_mode,
                    error, citations_json, retrieved_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message["id"],
                    conversation_id,
                    role,
                    content,
                    mode,
                    retrieval_mode,
                    error,
                    json.dumps(message["citations"], ensure_ascii=False),
                    json.dumps(message["retrieved"], ensure_ascii=False),
                    now,
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        return message

    def archive_conversation(self, session_id: str, conversation_id: str) -> bool:
        with self._connection() as conn:
            cursor = conn.execute(
                """
                UPDATE conversations SET archived = 1, updated_at = ?
                WHERE id = ? AND session_id = ? AND archived = 0
                """,
                (time.time(), conversation_id, session_id),
            )
        return cursor.rowcount == 1

    @staticmethod
    def _conversation_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "archived": bool(row["archived"]),
        }

    @staticmethod
    def _message_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "mode": row["mode"],
            "retrieval_mode": row["retrieval_mode"],
            "error": row["error"],
            "citations": json.loads(row["citations_json"]),
            "retrieved": json.loads(row["retrieved_json"]),
            "created_at": row["created_at"],
        }

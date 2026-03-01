"""
sqlite_backend.py — SQLite storage backend for agora-mem.

Stores session records in a local SQLite database using aiosqlite.
- Default search: FTS5 full-text search (BM25 ranked, porter stemmer)
- Fallback search: LIKE on JSON state column
- Optional: vector search with cosine similarity (when embeddings are stored)

FTS5 is kept in sync automatically via SQLite triggers on insert/update/delete.
"""

from __future__ import annotations

import json
import math
import os
from typing import List, Optional

import aiosqlite

from agora_mem.store import MemoryRecord


class SQLiteBackend:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._initialized = False

    async def _init(self):
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id   TEXT PRIMARY KEY,
                    state        TEXT NOT NULL,
                    version      INTEGER DEFAULT 1,
                    created_at   REAL,
                    updated_at   REAL,
                    ttl_seconds  INTEGER,
                    state_hash   TEXT,
                    embedding    TEXT
                )
            """)
            await db.commit()
        await self._ensure_fts()
        self._initialized = True

    async def _ensure_fts(self) -> None:
        """Create and populate the FTS5 virtual table + sync triggers if missing."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions_fts'"
            ) as cur:
                exists = await cur.fetchone()

            if not exists:
                await db.execute("""
                    CREATE VIRTUAL TABLE sessions_fts USING fts5(
                        session_id UNINDEXED,
                        state,
                        content='sessions',
                        content_rowid='rowid',
                        tokenize='porter ascii'
                    )
                """)
                # Populate from existing rows
                await db.execute("""
                    INSERT INTO sessions_fts(rowid, session_id, state)
                    SELECT rowid, session_id, state FROM sessions
                """)
                # Triggers keep FTS in sync on writes
                await db.execute("""
                    CREATE TRIGGER IF NOT EXISTS sessions_ai
                    AFTER INSERT ON sessions BEGIN
                        INSERT INTO sessions_fts(rowid, session_id, state)
                        VALUES (new.rowid, new.session_id, new.state);
                    END
                """)
                await db.execute("""
                    CREATE TRIGGER IF NOT EXISTS sessions_au
                    AFTER UPDATE ON sessions BEGIN
                        INSERT INTO sessions_fts(sessions_fts, rowid, session_id, state)
                        VALUES ('delete', old.rowid, old.session_id, old.state);
                        INSERT INTO sessions_fts(rowid, session_id, state)
                        VALUES (new.rowid, new.session_id, new.state);
                    END
                """)
                await db.execute("""
                    CREATE TRIGGER IF NOT EXISTS sessions_ad
                    AFTER DELETE ON sessions BEGIN
                        INSERT INTO sessions_fts(sessions_fts, rowid, session_id, state)
                        VALUES ('delete', old.rowid, old.session_id, old.state);
                    END
                """)
                await db.commit()

    async def upsert(self, record: MemoryRecord) -> None:
        await self._init()
        embedding_json = json.dumps(record.embedding) if record.embedding else None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO sessions
                    (session_id, state, version, created_at, updated_at,
                     ttl_seconds, state_hash, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    state       = excluded.state,
                    version     = excluded.version,
                    updated_at  = excluded.updated_at,
                    ttl_seconds = excluded.ttl_seconds,
                    state_hash  = excluded.state_hash,
                    embedding   = excluded.embedding
            """, (
                record.session_id,
                json.dumps(record.state),
                record.version,
                record.created_at,
                record.updated_at,
                record.ttl_seconds,
                record.state_hash,
                embedding_json,
            ))
            await db.commit()

    async def get(self, session_id: str) -> Optional[MemoryRecord]:
        await self._init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return self._row_to_record(row)

    async def delete(self, session_id: str) -> None:
        await self._init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            await db.commit()

    async def list_ids(self) -> List[str]:
        await self._init()
        import time
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT session_id, updated_at, ttl_seconds FROM sessions"
            ) as cursor:
                rows = await cursor.fetchall()
        now = time.time()
        return [
            row[0] for row in rows
            if row[2] is None or (now - row[1]) <= row[2]
        ]

    async def fts_search(self, query: str, k: int = 5) -> List[MemoryRecord]:
        """
        FTS5 full-text search with BM25 ranking and porter stemmer.

        Much better than LIKE — finds 'caching' when you stored 'cached',
        ranks by relevance, handles multi-word queries naturally.
        Falls back to keyword_search if the query syntax is invalid.
        """
        await self._init()
        safe_query = _fts5_escape(query)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            try:
                async with db.execute(
                    """
                    SELECT s.* FROM sessions s
                    JOIN sessions_fts ON s.rowid = sessions_fts.rowid
                    WHERE sessions_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (safe_query, k),
                ) as cursor:
                    rows = await cursor.fetchall()
                return [self._row_to_record(r) for r in rows]
            except Exception:
                # Syntax error or unsupported query — fall back gracefully
                return await self.keyword_search(query, k)

    async def keyword_search(self, query: str, k: int = 5) -> List[MemoryRecord]:
        """LIKE-based keyword search — fallback when FTS is unavailable."""
        await self._init()
        pattern = f"%{query}%"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sessions WHERE state LIKE ? OR session_id LIKE ? LIMIT ?",
                (pattern, pattern, k),
            ) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_record(r) for r in rows]

    async def vector_search(
        self,
        query_embedding: List[float],
        k: int = 5,
        min_score: float = 0.3,
    ) -> List[MemoryRecord]:
        """Cosine similarity search over stored embeddings (optional feature)."""
        await self._init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sessions WHERE embedding IS NOT NULL"
            ) as cursor:
                rows = await cursor.fetchall()

        records = [self._row_to_record(r) for r in rows]
        scored = []
        for rec in records:
            if rec.embedding:
                score = _cosine_similarity(query_embedding, rec.embedding)
                if score >= min_score:
                    scored.append((score, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in scored[:k]]

    @staticmethod
    def _row_to_record(row) -> MemoryRecord:
        emb = json.loads(row["embedding"]) if row["embedding"] else None
        return MemoryRecord(
            session_id=row["session_id"],
            state=json.loads(row["state"]),
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            ttl_seconds=row["ttl_seconds"],
            state_hash=row["state_hash"] or "",
            embedding=emb,
        )


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _fts5_escape(query: str) -> str:
    """
    Convert a plain user query into an FTS5 match expression.

    Each word is quoted and joined with OR so any word is a hit.
    Multi-word phrases stay together when quoted: "redis cache"
    """
    words = query.strip().split()
    if not words:
        return '""'
    if len(words) == 1:
        return f'"{words[0]}"'
    # OR across individual words — catches partial matches better than AND
    return " OR ".join(f'"{w}"' for w in words)

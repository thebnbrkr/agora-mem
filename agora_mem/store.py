"""
store.py — MemoryStore: session storage backend for agora-mem.

Supports two backends:
  - "sqlite"   : local file-based storage (default, zero infra)
  - "supabase" : cloud storage via Supabase (requires extras)

Public API:
  - store(session_id, state)      — upsert session state (no API calls)
  - load(session_id)              — load session by ID
  - search(query, k)              — FTS5 full-text search (free, always works)
  - semantic_search(query, k)     — vector search (requires embedder to be configured)
  - embed(session_id)             — explicitly generate + store embedding for one session
  - delete(session_id)            — hard delete
  - list_sessions()               — list all session IDs

Embeddings:
  Embeddings are NEVER generated automatically. Call embed(session_id) explicitly
  to index a session for semantic search. This avoids surprise API costs on platforms.
  Supported providers: "openai" | "gemini" | None
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
#  Data model                                                                  #
# --------------------------------------------------------------------------- #

@dataclass
class MemoryRecord:
    session_id: str
    state: Dict[str, Any]
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    ttl_seconds: Optional[int] = None   # None = never expires
    embedding: Optional[List[float]] = None
    state_hash: str = ""

    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        return (time.time() - self.updated_at) > self.ttl_seconds

    def compute_hash(self) -> str:
        raw = json.dumps(self.state, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
#  MemoryStore                                                                 #
# --------------------------------------------------------------------------- #

class MemoryStore:
    """
    Unified session memory store.

    Args:
        storage: "sqlite" (default) or "supabase"
        embeddings: "openai", "gemini", or None (no vector search)
        db_path: path to SQLite file (only used when storage="sqlite")
        supabase_url / supabase_key: required when storage="supabase"
        compress_threshold: auto-compress sessions when state has more than
                            this many top-level keys (None = disabled)
    """

    def __init__(
        self,
        storage: str = "sqlite",
        embeddings: Optional[str] = None,
        db_path: str = "./agora_mem_data/memory.db",
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        compress_threshold: Optional[int] = None,
    ):
        self.storage = storage
        self.embeddings_provider = embeddings
        self.compress_threshold = compress_threshold
        self._backend = self._init_backend(storage, db_path, supabase_url, supabase_key)
        self._embedder = self._init_embedder(embeddings)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def store(
        self,
        session_id: str,
        state: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> MemoryRecord:
        """
        Upsert session state. No API calls — always instant.
        Embeddings are NOT generated here. Call embed(session_id) explicitly
        if you want this session indexed for semantic search.
        """
        existing = await self.load(session_id)
        version = (existing.version + 1) if existing else 1

        record = MemoryRecord(
            session_id=session_id,
            state=state,
            version=version,
            updated_at=time.time(),
            ttl_seconds=ttl_seconds,
        )
        record.state_hash = record.compute_hash()
        await self._backend.upsert(record)
        return record

    async def load(self, session_id: str) -> Optional[MemoryRecord]:
        """Load session by ID. Returns None if not found or expired."""
        record = await self._backend.get(session_id)
        if record is None:
            return None
        if record.is_expired():
            await self.delete(session_id)
            return None
        return record

    async def search(
        self,
        query: str,
        k: int = 5,
    ) -> List[MemoryRecord]:
        """
        Full-text search using SQLite FTS5 (BM25 ranked, porter stemmer).
        No API calls — always free. Falls back to LIKE if FTS is unavailable.
        """
        if hasattr(self._backend, 'fts_search'):
            return await self._backend.fts_search(query, k=k)
        return await self._backend.keyword_search(query, k=k)

    async def semantic_search(
        self,
        query: str,
        k: int = 5,
        min_score: float = 0.3,
    ) -> List[MemoryRecord]:
        """
        Vector similarity search — requires embedder to be configured.
        Only searches sessions that have been explicitly embedded via embed().
        Raises RuntimeError if no embedder is configured.
        """
        if not self._embedder:
            raise RuntimeError(
                "No embedder configured. Pass embeddings='openai' or 'gemini' to MemoryStore, "
                "then call embed(session_id) to index sessions before searching."
            )
        query_embedding = await self._embedder(query)
        return await self._backend.vector_search(query_embedding, k=k, min_score=min_score)

    async def embed(self, session_id: str) -> MemoryRecord:
        """
        Explicitly generate and store an embedding for a session.
        Only call this when you want the session indexed for semantic_search().
        Requires an embedder to be configured.
        """
        if not self._embedder:
            raise RuntimeError(
                "No embedder configured. Pass embeddings='openai' or 'gemini' to MemoryStore."
            )
        record = await self.load(session_id)
        if record is None:
            raise KeyError(f"Session not found: {session_id!r}")
        text = self._state_to_text(record.state)
        record.embedding = await self._embedder(text)
        await self._backend.upsert(record)
        return record

    async def delete(self, session_id: str) -> None:
        """Hard delete a session."""
        await self._backend.delete(session_id)

    async def list_sessions(self) -> List[str]:
        """Return all session IDs (non-expired)."""
        return await self._backend.list_ids()

    # ------------------------------------------------------------------ #
    #  Internals                                                           #
    # ------------------------------------------------------------------ #

    def _state_to_text(self, state: Dict[str, Any]) -> str:
        """Convert state dict to a string suitable for embedding."""
        parts = []
        for k, v in state.items():
            if isinstance(v, list):
                parts.append(f"{k}: {', '.join(str(i) for i in v[:10])}")
            else:
                parts.append(f"{k}: {v}")
        return " | ".join(parts)[:1000]  # cap at 1000 chars

    def _init_backend(self, storage, db_path, supabase_url, supabase_key):
        if storage == "sqlite":
            from agora_mem.backends.sqlite_backend import SQLiteBackend
            return SQLiteBackend(os.path.expanduser(db_path))
        elif storage == "supabase":
            if not supabase_url or not supabase_key:
                raise ValueError("supabase_url and supabase_key required for supabase storage")
            from agora_mem.backends.supabase_backend import SupabaseBackend
            return SupabaseBackend(supabase_url, supabase_key)
        else:
            raise ValueError(f"Unknown storage backend: {storage!r}. Choose 'sqlite' or 'supabase'")

    def _init_embedder(self, provider: Optional[str]):
        if provider is None:
            return None
        elif provider == "openai":
            return self._make_openai_embedder()
        elif provider == "gemini":
            return self._make_gemini_embedder()
        elif provider == "local":
            return self._make_local_embedder()
        else:
            raise ValueError(f"Unknown embeddings provider: {provider!r}. Choose 'openai', 'gemini', 'local', or None")

    def _make_openai_embedder(self):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("Install openai: pip install agora-mem[openai]")
        client = AsyncOpenAI()
        async def embed(text: str) -> List[float]:
            resp = await client.embeddings.create(model="text-embedding-3-small", input=text)
            return resp.data[0].embedding
        return embed

    def _make_gemini_embedder(self):
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("Install google-generativeai: pip install agora-mem[gemini]")
        async def embed(text: str) -> List[float]:
            result = genai.embed_content(model="models/text-embedding-004", content=text)
            return result["embedding"]
        return embed

    def _make_local_embedder(self):
        """
        Local embeddings using sentence-transformers (no API key, no internet).
        Model: all-MiniLM-L6-v2 (~80MB, 384 dimensions)
        Loaded once and reused across all embed() calls.
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError("Install sentence-transformers: pip install agora-mem[local]")
        model = SentenceTransformer("all-MiniLM-L6-v2")
        async def embed(text: str) -> List[float]:
            vector = model.encode(text, convert_to_numpy=True)
            return vector.tolist()
        return embed

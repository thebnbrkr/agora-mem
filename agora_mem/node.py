"""
node.py — MemoryNode base class for agora-mem.

A framework-agnostic async base class that wires session memory
into the prep_async → exec_async → post_async lifecycle.

Works standalone (no Agora required). For the Agora-native version
with auto-telemetry, use:
    from agora_mem.integrations.agora import TracedMemoryNode

Usage:
    class MyNode(MemoryNode):
        async def exec_async(self, prep_res):
            # Your business logic here
            return {"decisions": [...], "next_steps": [...]}
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from agora_mem.store import MemoryStore


class MemoryNode:
    """
    Base class for nodes that automatically load and save session memory.

    Subclass and override exec_async. The prep/post hooks handle memory
    automatically — you only write the business logic.

    Args:
        memory: MemoryStore instance for session persistence
        session_key: key in shared dict that holds the session ID (default: "session_id")
        ttl_seconds: TTL for saved sessions (None = never expires)
        auto_compress: compress old sessions before loading (default: False)
    """

    def __init__(
        self,
        memory: MemoryStore,
        session_key: str = "session_id",
        ttl_seconds: Optional[int] = None,
        auto_compress: bool = False,
    ):
        self.memory = memory
        self.session_key = session_key
        self.ttl_seconds = ttl_seconds
        self.auto_compress = auto_compress

    # ------------------------------------------------------------------ #
    #  Lifecycle hooks — override exec_async only                         #
    # ------------------------------------------------------------------ #

    async def prep_async(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        """
        BEFORE exec: Load last session state into shared dict.

        Adds the following keys to shared (only if session exists):
          - _memory_last_session: full MemoryRecord
          - _memory_state: the saved state dict
        """
        session_id = shared.get(self.session_key)
        if not session_id:
            return shared

        record = await self.memory.load(session_id)
        if record:
            if self.auto_compress:
                from agora_mem.compressor import compress_record
                record = await compress_record(record)

            shared["_memory_last_session"] = record
            shared["_memory_state"] = record.state
            # Convenience: merge top-level state keys into shared
            for k, v in record.state.items():
                if k not in shared:  # don't override what caller already set
                    shared[k] = v

        return shared

    async def exec_async(self, prep_res: Dict[str, Any]) -> Any:
        """
        Override this with your business logic.
        Return value is passed to post_async as exec_res.
        """
        raise NotImplementedError("Override exec_async with your node's logic")

    async def post_async(
        self,
        shared: Dict[str, Any],
        prep_res: Dict[str, Any],
        exec_res: Any,
    ) -> Any:
        """
        AFTER exec: Save exec_res as new session state.

        exec_res should be a dict. If it's not, it will be wrapped
        under the key "result".
        """
        session_id = shared.get(self.session_key)
        if not session_id:
            return exec_res

        if not isinstance(exec_res, dict):
            state = {"result": exec_res}
        else:
            state = exec_res

        await self.memory.store(session_id, state, ttl_seconds=self.ttl_seconds)
        return exec_res

    # ------------------------------------------------------------------ #
    #  Run method (standalone, without a Flow orchestrator)               #
    # ------------------------------------------------------------------ #

    async def run_async(self, shared: Dict[str, Any]) -> Any:
        """
        Run this node standalone (no Flow required).

        Full lifecycle: prep → exec → post
        Returns exec_res (same as what exec_async returned).
        """
        prep_res = await self.prep_async(shared)
        exec_res = await self.exec_async(prep_res)
        return await self.post_async(shared, prep_res, exec_res)

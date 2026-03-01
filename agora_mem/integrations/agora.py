"""
integrations/agora.py — TracedMemoryNode for Agora users.

Extends MemoryNode with Agora's TracedAsyncNode so that every
memory load/save is automatically traced via OpenTelemetry.

Requires: pip install agora-mem[agora]

Usage:
    from agora_mem.integrations.agora import TracedMemoryNode
    from agora_mem import MemoryStore

    memory = MemoryStore()

    class MyNode(TracedMemoryNode):
        async def exec_async(self, prep_res):
            return {"decisions": [...], "next_steps": [...]}
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from agora_mem.node import MemoryNode
from agora_mem.store import MemoryStore


def _get_traced_base():
    try:
        from agora.agora_tracer import TracedAsyncNode
        return TracedAsyncNode
    except ImportError:
        raise ImportError(
            "Agora is required for TracedMemoryNode. "
            "Install it: pip install agora-mem[agora]"
        )


class TracedMemoryNode(MemoryNode):
    """
    MemoryNode with Agora telemetry (OpenTelemetry traces per node run).

    All memory operations (load/save) are traced as spans so you can
    see session load/save latency in your Agora dashboard.
    """

    def __init__(
        self,
        memory: MemoryStore,
        name: Optional[str] = None,
        session_key: str = "session_id",
        ttl_seconds: Optional[int] = None,
        auto_compress: bool = False,
    ):
        super().__init__(
            memory=memory,
            session_key=session_key,
            ttl_seconds=ttl_seconds,
            auto_compress=auto_compress,
        )
        self._node_name = name or self.__class__.__name__

        # Dynamically inherit Agora's tracing on first use
        TracedBase = _get_traced_base()
        self.__class__ = type(
            self.__class__.__name__,
            (self.__class__, TracedBase),
            {},
        )

    async def prep_async(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        return await MemoryNode.prep_async(self, shared)

    async def exec_async(self, prep_res: Dict[str, Any]) -> Any:
        raise NotImplementedError("Override exec_async with your node's logic")

    async def post_async(
        self,
        shared: Dict[str, Any],
        prep_res: Dict[str, Any],
        exec_res: Any,
    ) -> Any:
        return await MemoryNode.post_async(self, shared, prep_res, exec_res)

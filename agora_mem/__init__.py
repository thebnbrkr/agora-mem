"""
agora-mem — Workflow-native session memory for AI agents and team handoffs.

Standalone package. Works with any async Python framework.
Optional Agora integration available via: pip install agora-mem[agora]

Usage:
    from agora_mem import MemoryStore, MemoryNode

    memory = MemoryStore()
    await memory.store("session_id", {"decisions": [...], "next_steps": [...]})
    session = await memory.load("session_id")
"""

from agora_mem.store import MemoryStore
from agora_mem.node import MemoryNode

__version__ = "0.1.0"
__all__ = ["MemoryStore", "MemoryNode"]

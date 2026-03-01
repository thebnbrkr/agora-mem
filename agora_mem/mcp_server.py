"""
mcp_server.py — MCP server for agora-mem.

Exposes session memory as MCP tools so Claude, Cursor, Cline,
and other MCP-compatible agents can automatically read and write memory.

Tools exposed:
  - mem_store   : save a session
  - mem_load    : load a session by ID
  - mem_search  : semantic/keyword search across sessions
  - mem_list    : list all session IDs

Run:
    agora-mem-mcp

Or programmatically:
    from agora_mem.mcp_server import create_server
    server = create_server(memory_store)
    server.run()
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict

from agora_mem.store import MemoryStore


def create_server(memory: MemoryStore):
    """Create and return an MCP server bound to the given MemoryStore."""
    try:
        from mcp.server import MCPServer
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError:
        raise ImportError("Install MCP: pip install agora-mem[mcp]")

    server = MCPServer("agora-mem")

    @server.tool()
    async def mem_store(session_id: str, state: str, ttl_days: int = 30) -> str:
        """
        Save or update a session's state.

        Args:
            session_id: unique identifier for this session (e.g. ticket ID, project name)
            state: JSON string of the state to store
            ttl_days: days until this session expires (default 30, 0 = never)
        """
        try:
            state_dict = json.loads(state)
        except json.JSONDecodeError:
            return f"Error: state must be valid JSON. Got: {state[:100]}"

        ttl = ttl_days * 86400 if ttl_days > 0 else None
        record = await memory.store(session_id, state_dict, ttl_seconds=ttl)
        return f"Stored session '{session_id}' (version {record.version})"

    @server.tool()
    async def mem_load(session_id: str) -> str:
        """
        Load the last saved state for a session.

        Args:
            session_id: session to load
        """
        record = await memory.load(session_id)
        if record is None:
            return f"No session found for '{session_id}'"
        return json.dumps({
            "session_id": record.session_id,
            "version": record.version,
            "state": record.state,
            "updated_at": record.updated_at,
        }, indent=2)

    @server.tool()
    async def mem_search(query: str, k: int = 5) -> str:
        """
        Search across all stored sessions for ones relevant to the query.

        Args:
            query: natural language query (e.g. "authentication issues", "ticket CS-1234")
            k: number of results to return (default 5)
        """
        results = await memory.search(query, k=k)
        if not results:
            return f"No sessions found matching '{query}'"

        output = []
        for rec in results:
            output.append({
                "session_id": rec.session_id,
                "version": rec.version,
                "state": rec.state,
                "updated_at": rec.updated_at,
            })
        return json.dumps(output, indent=2)

    @server.tool()
    async def mem_list() -> str:
        """List all active session IDs."""
        ids = await memory.list_sessions()
        if not ids:
            return "No sessions stored."
        return "\n".join(ids)

    return server


def main():
    """Entry point for `agora-mem-mcp` CLI command."""
    try:
        from mcp.server.stdio import stdio_server
    except ImportError:
        raise ImportError("Install MCP: pip install agora-mem[mcp]")

    storage = os.environ.get("AGORA_MEM_STORAGE", "sqlite")
    embeddings = os.environ.get("AGORA_MEM_EMBEDDINGS", None)
    db_path = os.environ.get("AGORA_MEM_DB_PATH", "~/.agora_mem/memory.db")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    memory = MemoryStore(
        storage=storage,
        embeddings=embeddings,
        db_path=db_path,
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )

    server = create_server(memory)

    async def run():
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()

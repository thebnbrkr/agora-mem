"""
coding_agent.py — Using agora-mem in a coding agent / dev session.

Demonstrates how to persist coding session context across conversations
so Claude/Cursor can resume where you left off without rereading the repo.

Run: python examples/coding_agent.py

MCP usage (add to claude_desktop_config.json):
    {
        "mcpServers": {
            "agora-mem": {
                "command": "agora-mem-mcp",
                "env": {
                    "AGORA_MEM_STORAGE": "sqlite",
                    "AGORA_MEM_DB_PATH": "~/.agora_mem/memory.db"
                }
            }
        }
    }
"""

import asyncio
from agora_mem import MemoryStore, MemoryNode


memory = MemoryStore(storage="sqlite")


class CodingSessionNode(MemoryNode):
    """Persists coding session state: current files, hypotheses, decisions."""

    async def exec_async(self, shared):
        project = shared["session_id"]

        # Previous session loaded automatically in prep_async
        current_file = shared.get("current_file", "unknown")
        hypothesis = shared.get("hypothesis", "None yet")
        decisions = shared.get("decisions", [])
        blockers = shared.get("blockers", [])

        print(f"\n[Resuming: {project}]")
        print(f"  Last file: {current_file}")
        print(f"  Hypothesis: {hypothesis}")
        print(f"  Decisions so far: {decisions}")
        print(f"  Blockers: {blockers}")

        # --- Simulate new session work ---
        new_decision = "Switched to async HTTP client for performance"
        print(f"\n[Session progress] New decision: {new_decision}")

        return {
            "current_file": "agora/core/engine.py",
            "hypothesis": "Race condition in async node execution",
            "decisions": decisions + [new_decision],
            "blockers": ["Need review from team on locking strategy"],
            "branch": "fix/async-race-condition",
        }


async def main():
    project_id = "agora-async-fix"

    # First session
    print("=== Session 1 ===")
    node = CodingSessionNode(memory=memory, session_key="session_id")
    await node.run_async({
        "session_id": project_id,
        "current_file": "agora/core/engine.py",
        "hypothesis": "Race condition in async node execution",
        "decisions": ["Reproduce with 4-node pipeline"],
        "blockers": [],
    })

    # Second session — picks up exactly where we left off
    print("\n=== Session 2 (next day) ===")
    await node.run_async({"session_id": project_id})

    # Search for related sessions
    print("\n=== Searching for async-related sessions ===")
    results = await memory.search("async race condition")
    for r in results:
        print(f"  Found: {r.session_id} — {r.state.get('hypothesis', '')}")


if __name__ == "__main__":
    asyncio.run(main())

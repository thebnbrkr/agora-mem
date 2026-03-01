# agora-mem

**Workflow-native session memory for AI agents and team handoffs.**

Store what happened. Resume where you left off. Works with any Python async app — or natively with Agora workflows.

---

## Install

```bash
pip install agora-mem                    # core (SQLite only, no extras)
pip install "agora-mem[openai]"          # + OpenAI embeddings for semantic search
pip install "agora-mem[mcp]"             # + MCP server for Claude/Cursor
pip install "agora-mem[agora]"           # + Agora TracedMemoryNode integration
pip install "agora-mem[all]"             # everything
```

---

## Quick Start

```python
from agora_mem import MemoryStore, MemoryNode

memory = MemoryStore()  # SQLite, stored in ~/.agora_mem/memory.db

class MyNode(MemoryNode):
    async def exec_async(self, shared):
        # Previous session loaded automatically into shared
        last_decision = shared.get("last_decision", "None")
        print(f"Last session decided: {last_decision}")

        # Return new state — auto-saved after exec
        return {
            "last_decision": "Use Redis for caching",
            "next_steps": ["Benchmark Redis vs in-memory"],
        }

import asyncio

node = MyNode(memory=memory, session_key="session_id")
asyncio.run(node.run_async({"session_id": "my-project"}))
```

---

## Use Cases

| Use Case | What Gets Stored |
|---|---|
| **Coding agent** | Current file, hypothesis, decisions, branch |
| **Support tickets** | Issue, resolution attempts, escalation chain |
| **Sales handoffs** | Prospect, pain points, last call summary |
| **Chat app** | User preferences, past conversation summary |
| **Medical** | Patient summary, current meds, next actions |

---

## MCP Server (Claude / Cursor)

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agora-mem": {
      "command": "agora-mem-mcp",
      "env": {
        "AGORA_MEM_STORAGE": "sqlite"
      }
    }
  }
}
```

Then Claude can call:
- `mem_store` — save a session
- `mem_load` — load by ID
- `mem_search` — semantic search across sessions
- `mem_list` — list all sessions

---

## With Agora (traced memory)

```python
from agora_mem.integrations.agora import TracedMemoryNode

class MyNode(TracedMemoryNode):
    async def exec_async(self, shared):
        # Full Agora telemetry on every memory read/write
        return {"status": "done"}
```

---

## Storage Backends

| Backend | When to use |
|---|---|
| `sqlite` (default) | Local dev, single machine |
| `supabase` | Cloud / team shared memory |

```python
# Local
memory = MemoryStore(storage="sqlite")

# Cloud
memory = MemoryStore(
    storage="supabase",
    supabase_url="...",
    supabase_key="...",
    embeddings="openai",
)
```

---

## How It Differs From Mem0

| | Mem0 | agora-mem |
|---|---|---|
| Storage | Text blobs | Structured dicts + update-in-place |
| Compression | None | Write-time, per-field |
| Workflows | Manual | Native via `MemoryNode` lifecycle |
| MCP | No | Yes — `agora-mem-mcp` |
| TTL | Manual | Per-session TTL |

---

## License

Apache 2.0

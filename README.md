# agora-mem

**Persistent session memory for AI apps and team handoffs.**

Store what happened. Resume where you left off. Works with any Python async app.

---

## Install

```bash
pip install agora-mem                    # core (SQLite, no API keys needed)
pip install "agora-mem[openai]"          # + OpenAI embeddings for semantic search
pip install "agora-mem[mcp]"             # + MCP server for Claude/Cursor
```

Or directly from GitHub:
```bash
pip install git+https://github.com/thebnbrkr/agora-mem.git
```

---

## Quick Start

```python
from agora_mem import MemoryStore
import asyncio

memory = MemoryStore()  # SQLite, zero config

async def main():
    # Store a session
    await memory.store("user_alice", {
        "topic": "SaaS pricing strategy",
        "decisions": ["go with usage-based pricing"],
        "next_steps": ["research competitor tiers"]
    })

    # Load it back (next day, new session)
    session = await memory.load("user_alice")
    print(session.state["decisions"])  # ["go with usage-based pricing"]

    # Full-text search across all sessions (FTS5, no API calls)
    results = await memory.search("pricing strategy")

asyncio.run(main())
```

---

## Use Cases

| Use Case | What Gets Stored |
|---|---|
| **Chat app** | User preferences, conversation summary, past topics |
| **Support tickets** | Issue, resolution attempts, escalation history |
| **Sales handoffs** | Prospect info, pain points, last call summary |
| **Medical** | Patient summary, current meds, next actions |
| **Team standups** | Blockers, decisions made, who owns what |

---

## Search

```python
# Free full-text search (FTS5, BM25 ranked — no API calls)
results = await memory.search("slow API timeout")

# Semantic vector search (requires embeddings configured)
memory = MemoryStore(embeddings="openai")
await memory.embed("session_1")               # index this session
results = await memory.semantic_search("performance issues")
```

---

## Embeddings

```python
MemoryStore(embeddings="openai")   # text-embedding-3-small
MemoryStore(embeddings="gemini")   # text-embedding-004
MemoryStore(embeddings="local")    # all-MiniLM-L6-v2 (no API key, on-device)
MemoryStore(embeddings=None)       # keyword search only (default)
```

Embeddings are **never generated automatically** — call `embed(session_id)` explicitly
to control costs. Use `search()` for free FTS5 search without any embeddings.

---

## Extractor

Turn any raw session state into structured output:

```python
from agora_mem.extractor import extract, openai_llm

structured = await extract(session.state, llm_fn=openai_llm())
# {
#   "summary":      "Team decided on usage-based pricing after competitor research",
#   "key_items":    ["usage-based pricing", "free tier at 1000 calls/mo"],
#   "next_actions": ["A/B test landing page", "email beta users"],
#   "tags":         ["pricing", "saas", "beta"]
# }
```

---

## MCP Server (Claude / Cursor)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agora-mem": {
      "command": "agora-mem-mcp"
    }
  }
}
```

Claude can then call `mem_store`, `mem_load`, `mem_search`, `mem_list`.

---

## vs Mem0

| | Mem0 | agora-mem |
|---|---|---| 
| Unit | Individual facts | Full session state |
| Retrieval | "Find facts about X" | "Load last session for project X" |
| Search | Semantic only | FTS5 (free) + semantic (optional) |
| Compression | None | Write-time via LLM |
| TTL | Manual | Per-session |

Mem0 answers "what do I know about this user?"
agora-mem answers "where did we leave off?"

---

## License

Apache 2.0

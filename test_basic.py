"""
test_basic.py — Quick smoke test for agora-mem (no API keys needed)

Run: python test_basic.py
"""
import asyncio
from agora_mem import MemoryStore


async def main():
    memory = MemoryStore(storage="sqlite", db_path="./test_memory.db")
    print("✅ MemoryStore initialized\n")

    # --- STORE ---
    await memory.store("ticket_T001", {
        "content": "Customer complained about slow API responses",
        "type": "support_ticket",
        "priority": "high"
    })
    print("✅ Stored: support ticket")

    await memory.store("decision_redis", {
        "content": "Decided to use Redis for caching to fix the slow API",
        "type": "decision",
        "team": "backend"
    })
    print("✅ Stored: decision\n")

    # --- LOAD ---
    ticket = await memory.load("ticket_T001")
    print(f"✅ Loaded ticket: {ticket.state['content']}")
    print(f"   Version: {ticket.version}, Hash: {ticket.state_hash}\n")

    # --- UPDATE (upsert) ---
    await memory.store("ticket_T001", {
        "content": "Customer complained about slow API responses",
        "type": "support_ticket",
        "priority": "resolved",
        "resolution": "Redis caching deployed"
    })
    updated = await memory.load("ticket_T001")
    print(f"✅ Updated ticket priority: {updated.state['priority']} (version {updated.version})\n")

    # --- SEARCH ---
    results = await memory.search("API performance")
    print(f"✅ Search 'API performance': {len(results)} results")
    for r in results:
        print(f"   [{r.session_id}] {r.state.get('type')} — {r.state.get('content', '')[:60]}")
    print()

    # --- LIST ---
    sessions = await memory.list_sessions()
    print(f"✅ All sessions: {sessions}\n")

    # --- DELETE ---
    await memory.delete("decision_redis")
    sessions_after = await memory.list_sessions()
    print(f"✅ After delete: {sessions_after}\n")

    print("🎉 All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())

"""
test_support.py — demo of agora-mem for a support handoff use case.
No API keys needed. Tests FTS5 search, session management, and TTL.

Run: python test_support.py
"""
import asyncio
from agora_mem import MemoryStore


async def main():
    memory = MemoryStore(storage="sqlite", db_path="./support_memory.db")
    print("=" * 55)
    print("  agora-mem — Support Handoff Demo")
    print("=" * 55)

    # ── Shift 1: Agent Alice opens a ticket ──────────────────
    print("\n📋 SHIFT 1 — Alice opens ticket T-001")

    await memory.store("ticket_T001", {
        "customer": "Acme Corp",
        "issue": "API responses are slow, timing out after 30s",
        "priority": "high",
        "status": "investigating",
        "notes": "Looks like a database bottleneck under heavy load",
        "agent": "Alice",
    })
    print("✅ Alice saved ticket T-001")

    await memory.store("ticket_T002", {
        "customer": "Wayne Enterprises",
        "issue": "Login fails for enterprise SSO users",
        "priority": "critical",
        "status": "open",
        "notes": "Only affects SAML integration, normal login works",
        "agent": "Alice",
    })
    print("✅ Alice saved ticket T-002")

    # ── Shift 2: Agent Bob picks up where Alice left off ──────
    print("\n📋 SHIFT 2 — Bob takes over (loads T-001)")

    ticket = await memory.load("ticket_T001")
    print(f"✅ Loaded: {ticket.state['customer']} — {ticket.state['issue']}")
    print(f"   Alice's note: {ticket.state['notes']}")
    print(f"   Version: {ticket.version}")

    # Bob updates the ticket with new findings
    await memory.store("ticket_T001", {
        **ticket.state,
        "status": "resolved",
        "priority": "high",
        "resolution": "Added Redis caching layer, response times back to normal",
        "agent": "Bob",
    })
    print("✅ Bob resolved ticket T-001")

    updated = await memory.load("ticket_T001")
    print(f"   Now at version {updated.version}, status: {updated.state['status']}")

    # ── FTS5 Search — find tickets by topic ──────────────────
    print("\n🔍 SEARCH — 'slow performance timeout'")
    results = await memory.search("slow performance timeout")
    print(f"   Found {len(results)} tickets")
    for r in results:
        print(f"   → [{r.state['priority'].upper()}] {r.state['customer']}: {r.state['issue'][:50]}")

    print("\n🔍 SEARCH — 'login SSO authentication'")
    results = await memory.search("login SSO authentication")
    print(f"   Found {len(results)} tickets")
    for r in results:
        print(f"   → [{r.state['priority'].upper()}] {r.state['customer']}: {r.state['issue'][:50]}")

    # ── List all open sessions ────────────────────────────────
    print("\n📂 All active sessions:")
    sessions = await memory.list_sessions()
    for sid in sessions:
        r = await memory.load(sid)
        print(f"   {sid} → {r.state['customer']} [{r.state['status']}]")

    # ── TTL demo — auto-expiring session ─────────────────────
    print("\n⏱️  TTL demo — session expires in 2s")
    await memory.store("temp_note", {"note": "Quick reminder"}, ttl_seconds=2)
    r = await memory.load("temp_note")
    print(f"   Loaded before expiry: {r.state['note']!r}")
    await asyncio.sleep(2.1)
    r = await memory.load("temp_note")
    print(f"   Loaded after expiry:  {r}  ← None as expected")

    # ── Cleanup ───────────────────────────────────────────────
    import os
    os.remove("./support_memory.db")

    print("\n🎉 All tests passed!")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())

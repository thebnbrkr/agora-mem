"""
test_chat_app.py — Chat app demo using agora-mem with real OpenAI responses.

Features:
  - User-configurable memory size (how many messages to keep)
  - OpenAI key from .env
  - FTS5 search across all past conversations
  - Session persistence across "restarts"

Run: python test_chat_app.py
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load .env from the Agora project
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../Agora/.env"))

from agora_mem import MemoryStore

# ── Configuration ──────────────────────────────────────────────────────────
MEMORY_SIZE = 10       # <- user can change this: how many messages to keep per user
USER_ID = "alice"      # simulated user
DB_PATH = "./chat_memory.db"


async def chat_with_memory(user_message: str, memory: MemoryStore, openai: AsyncOpenAI):
    """
    Send a message to OpenAI with context from past sessions injected.
    Saves new message to memory after responding.
    """
    # 1. Load existing session for this user
    session = await memory.load(f"user_{USER_ID}")
    history = session.state.get("messages", []) if session else []
    summary = session.state.get("summary", "") if session else ""

    # 2. Build system prompt — inject memory context
    system_prompt = "You are a helpful assistant with memory of past conversations."
    if summary:
        system_prompt += f"\n\nContext from past sessions:\n{summary}"

    # 3. Build message history for this request
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-MEMORY_SIZE:]:   # only send last N messages
        messages.append({"role": "user",      "content": msg["user"]})
        messages.append({"role": "assistant", "content": msg["bot"]})
    messages.append({"role": "user", "content": user_message})

    # 4. Call OpenAI
    resp = await openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
    )
    bot_response = resp.choices[0].message.content

    # 5. Append to history and save (rolling window = MEMORY_SIZE)
    history.append({"user": user_message, "bot": bot_response})
    rolling = history[-MEMORY_SIZE:]   # keep only last N

    # 6. Auto-summarise older messages when we trim them
    trimmed_count = len(history) - len(rolling)
    new_summary = summary
    if trimmed_count > 0:
        older = history[:trimmed_count]
        topics = set()
        for m in older:
            for word in m["user"].lower().split():
                if len(word) > 4:
                    topics.add(word)
        new_summary = f"Previously discussed: {', '.join(list(topics)[:10])}"

    await memory.store(f"user_{USER_ID}", {
        "messages": rolling,
        "summary": new_summary,
        "message_count": len(history),
    })

    return bot_response


async def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in .env")
        sys.exit(1)

    openai = AsyncOpenAI(api_key=api_key)
    memory = MemoryStore(storage="sqlite", db_path=DB_PATH)

    print("=" * 60)
    print(f"  agora-mem Chat Demo  (memory size: {MEMORY_SIZE} messages)")
    print("=" * 60)

    # ── Simulate Session 1 ───────────────────────────────────
    print("\n🗨️  SESSION 1")
    conversations = [
        "Hi! I'm building a SaaS for HR teams. What pricing model do you recommend?",
        "What are the pros and cons of usage-based pricing for B2B?",
        "Got it. We'll go with usage-based. What should our free tier look like?",
    ]

    for msg in conversations:
        print(f"\n👤 User: {msg}")
        reply = await chat_with_memory(msg, memory, openai)
        print(f"🤖 Bot:  {reply[:180]}{'...' if len(reply) > 180 else ''}")

    # Show what's stored
    session = await memory.load(f"user_{USER_ID}")
    print(f"\n📦 Stored {session.state['message_count']} messages, "
          f"keeping last {len(session.state['messages'])}")

    # ── Simulate Session 2 (next day) ────────────────────────
    print("\n" + "─" * 60)
    print("🗨️  SESSION 2 — Simulating user returning next day")

    continuations = [
        "Hey, I'm back. What did we decide about our pricing model?",
        "Right! And what about enterprise customers — different pricing?",
    ]

    for msg in continuations:
        print(f"\n👤 User: {msg}")
        reply = await chat_with_memory(msg, memory, openai)
        print(f"🤖 Bot:  {reply[:180]}{'...' if len(reply) > 180 else ''}")

    # ── FTS5 search across all sessions ──────────────────────
    print("\n" + "─" * 60)
    print("🔍 FTS5 SEARCH — 'pricing enterprise SaaS'")
    results = await memory.search("pricing enterprise SaaS")
    print(f"   Found {len(results)} sessions")
    for r in results:
        msg_count = r.state.get("message_count", 0)
        summary = r.state.get("summary", "no summary yet")
        print(f"   → {r.session_id}: {msg_count} messages | {summary[:60]}")

    # ── Cleanup ───────────────────────────────────────────────
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    print("\n🎉 Done!")
    print("=" * 60)
    print(f"\n💡 To change memory size: edit MEMORY_SIZE at top of file")
    print(f"   Current: {MEMORY_SIZE} messages per user")


if __name__ == "__main__":
    asyncio.run(main())

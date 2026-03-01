"""
chat.py — Interactive terminal chat with persistent memory + OpenAI embeddings.

- FTS5 search for free text search
- OpenAI embeddings for semantic search across past conversations
- Memory persists across sessions — it remembers you next time

Run:  python chat.py
Quit: type 'quit' or press Ctrl+C
Commands: 'history', 'search <query>', 'clear', 'quit'
"""
import asyncio
import os
import sys
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agora_mem import MemoryStore

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../Agora/.env"))

MEMORY_SIZE = 10   # messages to keep in rolling window
USER_ID     = "user"
DB_PATH     = "/Users/anirudhanil/Desktop/agora3/agora-mem/chat_memory.db"


async def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in .env"); sys.exit(1)

    openai = AsyncOpenAI(api_key=api_key)

    # embeddings="openai" enables semantic search via embed() + semantic_search()
    memory = MemoryStore(storage="sqlite", db_path=DB_PATH, embeddings="openai")

    # Load existing session
    session   = await memory.load(f"user_{USER_ID}")
    history   = session.state.get("messages", []) if session else []
    msg_total = session.state.get("message_count", 0) if session else 0

    print("\n🧠  agora-mem chat  (FTS5 + OpenAI embeddings)")
    if history:
        print(f"📂  Loaded {msg_total} past messages — I remember you!\n")
    else:
        print("🆕  New session — no past memory yet.\n")
    print("Commands: 'quit' | 'history' | 'search <query>' | 'clear'\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Bye!")
            break

        if not user_input:
            continue

        # ── Built-in commands ──────────────────────────────────
        if user_input.lower() == "quit":
            print("👋 Bye!")
            break

        if user_input.lower() == "history":
            if not history:
                print("  (no history yet)\n")
            else:
                print("\n── Past messages ──")
                for m in history:
                    print(f"  You: {m['user']}")
                    print(f"  Bot: {m['bot'][:80]}...")
                print()
            continue

        if user_input.lower() == "clear":
            await memory.delete(f"user_{USER_ID}")
            history, msg_total = [], 0
            session = None
            print("  🗑️  Memory cleared.\n")
            continue

        if user_input.lower().startswith("search "):
            query = user_input[7:].strip()
            print(f"\n🔍 Semantic search: '{query}'")
            try:
                results = await memory.semantic_search(query, k=5)
                if results:
                    for r in results:
                        msgs = r.state.get("messages", [])
                        print(f"  [{r.session_id}] {len(msgs)} messages")
                        if msgs:
                            print(f"    Last: {msgs[-1]['user'][:60]}")
                else:
                    print("  No results (embed more sessions first)")
            except RuntimeError:
                # Fall back to FTS5 if no embedding configured
                results = await memory.search(query)
                for r in results:
                    print(f"  [{r.session_id}]")
            print()
            continue

        # ── Normal chat message ────────────────────────────────
        system = "You are a helpful assistant with memory of past conversations."
        if session and session.state.get("summary"):
            system += f"\n\nContext from older messages: {session.state['summary']}"

        messages = [{"role": "system", "content": system}]
        for m in history[-MEMORY_SIZE:]:
            messages.append({"role": "user",      "content": m["user"]})
            messages.append({"role": "assistant", "content": m["bot"]})
        messages.append({"role": "user", "content": user_input})

        # Stream response
        print("Bot: ", end="", flush=True)
        full_response = ""
        stream = await openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            print(delta, end="", flush=True)
            full_response += delta
        print("\n")

        # Save to memory (rolling window)
        history.append({"user": user_input, "bot": full_response})
        msg_total += 1
        rolling = history[-MEMORY_SIZE:]

        await memory.store(f"user_{USER_ID}", {
            "messages":      rolling,
            "message_count": msg_total,
            "summary":       session.state.get("summary", "") if session else "",
        })

        # Embed the session so semantic search works
        await memory.embed(f"user_{USER_ID}")

        # keep session ref updated
        session = await memory.load(f"user_{USER_ID}")


if __name__ == "__main__":
    asyncio.run(main())

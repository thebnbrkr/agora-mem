"""
chat_app.py — Using agora-mem in a chat application.

Shows how to persist conversation context across sessions
so users don't have to re-explain their preferences every time.

Run: python examples/chat_app.py
"""

import asyncio
from agora_mem import MemoryStore, MemoryNode


memory = MemoryStore(storage="sqlite")  # stored in ~/.agora_mem/memory.db


class ChatContextNode(MemoryNode):
    """Loads user preferences before generating a response, saves updates after."""

    async def exec_async(self, shared):
        user_id = shared["user_id"]
        message = shared["message"]

        # Previous session was loaded in prep_async — available here
        preferences = shared.get("preferences", {})
        history_summary = shared.get("history_summary", "No previous context.")

        print(f"\nUser: {message}")
        print(f"[Context loaded] Preferences: {preferences}")
        print(f"[Context loaded] History: {history_summary}")

        # --- Your LLM call would go here ---
        # response = await llm.complete(message, context=history_summary)
        response = f"[Mock response to: {message}]"

        print(f"Assistant: {response}")

        # Return state to save for next session
        return {
            "preferences": preferences,
            "history_summary": f"Last topic: {message[:50]}",
            "last_message": message,
        }


async def main():
    user_id = "user_alice"

    # First session
    print("=== Session 1 ===")
    node = ChatContextNode(memory=memory, session_key="user_id")
    await node.run_async({
        "user_id": user_id,
        "message": "I prefer concise answers. My team uses Python.",
    })

    # Second session — memory is automatically loaded
    print("\n=== Session 2 (days later) ===")
    await node.run_async({
        "user_id": user_id,
        "message": "How do I set up a virtual environment?",
    })


if __name__ == "__main__":
    asyncio.run(main())

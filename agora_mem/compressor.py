"""
compressor.py — Write-time session compression for agora-mem.

When a session's state grows too large (too many decisions, long timeline,
etc.), compress it before storage to reduce token usage on retrieval.

Compression is triggered either:
  - Manually: await compress_record(record)
  - Automatically: when MemoryNode is initialized with auto_compress=True

The compressed summary is stored alongside the last N raw items,
so recent context is always precise.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from agora_mem.store import MemoryRecord


# Number of recent items to keep verbatim (rest get summarized)
KEEP_RECENT = 3


async def compress_record(
    record: MemoryRecord,
    llm_provider: str = "openai",
    max_items_before_compress: int = 10,
) -> MemoryRecord:
    """
    Compress a MemoryRecord's state if it's grown too large.

    For list-valued keys with more than max_items_before_compress items:
      - Keep the last KEEP_RECENT items verbatim
      - Summarize the rest into a single string

    Returns a new MemoryRecord (does not modify in place).
    """
    state = record.state
    compressed_state: Dict[str, Any] = {}
    needs_compression = False

    for key, value in state.items():
        if isinstance(value, list) and len(value) > max_items_before_compress:
            needs_compression = True
            older = value[:-KEEP_RECENT]
            recent = value[-KEEP_RECENT:]
            summary = await _summarize(key, older, llm_provider)
            compressed_state[key] = recent
            compressed_state[f"{key}_summary"] = summary
        else:
            compressed_state[key] = value

    if not needs_compression:
        return record

    import copy
    new_record = copy.copy(record)
    new_record.state = compressed_state
    new_record.state_hash = new_record.compute_hash()
    return new_record


async def _summarize(
    key: str,
    items: List[Any],
    provider: str,
) -> str:
    """Summarize a list of items into a short paragraph."""
    items_text = "\n".join(f"- {item}" for item in items)
    prompt = (
        f"Summarize these past '{key}' entries into 2-3 bullet points. "
        f"Be concise. Preserve key decisions, blockers, and outcomes:\n\n{items_text}"
    )

    if provider == "openai":
        return await _openai_summarize(prompt)
    elif provider == "gemini":
        return await _gemini_summarize(prompt)
    else:
        # Naive fallback: just join the first few
        return "; ".join(str(i) for i in items[:5]) + f" (+ {len(items) - 5} more)"


async def _openai_summarize(prompt: str) -> str:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError("pip install agora-mem[openai]")

    client = AsyncOpenAI()
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


async def _gemini_summarize(prompt: str) -> str:
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError("pip install agora-mem[gemini]")

    model = genai.GenerativeModel("gemini-2.0-flash")
    resp = await model.generate_content_async(prompt)
    return resp.text.strip()

"""
extractor.py — Universal structured extractor for agora-mem.

Extracts structured output from any session state using an LLM.
The schema is intentionally generic — works for support, sales, medical,
coding, or any other domain without domain-specific field definitions.

Output schema:
{
    "summary":      str,        # one sentence: what happened this session
    "key_items":    list[str],  # important facts, decisions, insights
    "next_actions": list[str],  # what needs to happen next
    "tags":         list[str],  # keywords for search and categorisation
}

Usage:
    from agora_mem.extractor import extract
    from agora_mem import MemoryStore

    memory = MemoryStore()
    record = await memory.load("session_1")

    structured = await extract(record.state, llm_fn=my_llm)
    # structured = {
    #     "summary": "Investigated JWT auth bug; root cause identified",
    #     "key_items": ["off-by-one in timestamp comparison", "fix in auth.py:47"],
    #     "next_actions": ["write regression test", "deploy to staging"],
    #     "tags": ["auth", "jwt", "bug", "backend"],
    # }
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Coroutine, Dict, List, Optional

# The universal output schema — same for every domain
EXTRACT_SCHEMA = {
    "summary": "One sentence describing what happened this session",
    "key_items": "List of important facts, decisions, or insights (strings)",
    "next_actions": "List of concrete next steps to take (strings)",
    "tags": "List of 3-8 short keyword tags for search and categorisation",
}

_SYSTEM_PROMPT = """\
You are a session summariser. Given a raw session state (JSON), extract structured information.
Return ONLY valid JSON — no markdown, no explanation, no code fences.
"""

_USER_PROMPT_TEMPLATE = """\
Session state:
{state_json}

Extract the following fields and return as JSON:
{schema_json}

Rules:
- summary: one sentence, past tense
- key_items: 3-10 items, each a short phrase
- next_actions: list what needs to happen next (empty list if unknown)
- tags: 3-8 lowercase single-word or hyphenated tags
- If a field cannot be determined, return an empty string or empty list
"""


async def extract(
    state: Dict[str, Any],
    llm_fn: Callable[[str, str], Coroutine],
    extra_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract structured output from a session state dict using an LLM.

    Args:
        state:         The session state dict to extract from.
        llm_fn:        Async function (system_prompt, user_prompt) -> str.
                       Should return the LLM's raw text response.
        extra_context: Optional extra context to append to the user prompt.

    Returns:
        Dict with keys: summary, key_items, next_actions, tags.
        Falls back to a best-effort dict if LLM returns invalid JSON.
    """
    state_json = json.dumps(state, indent=2, default=str)[:3000]  # cap input size
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        state_json=state_json,
        schema_json=json.dumps(EXTRACT_SCHEMA, indent=2),
    )
    if extra_context:
        user_prompt += f"\n\nAdditional context:\n{extra_context}"

    raw = await llm_fn(_SYSTEM_PROMPT, user_prompt)
    return _parse_response(raw, state)


def _parse_response(raw: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Parse LLM response, falling back gracefully on invalid JSON."""
    # Strip any accidental markdown code fences
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        result = json.loads(cleaned)
        return _normalise(result)
    except (json.JSONDecodeError, ValueError):
        # Best-effort fallback: return partial state info
        return {
            "summary": str(state.get("summary", state.get("content", "Session data"))),
            "key_items": _flatten_values(state),
            "next_actions": state.get("next_steps", state.get("next_actions", [])),
            "tags": state.get("tags", []),
        }


def _normalise(result: dict) -> Dict[str, Any]:
    """Ensure all fields are the right types."""
    return {
        "summary": str(result.get("summary", "")),
        "key_items": _ensure_list(result.get("key_items", [])),
        "next_actions": _ensure_list(result.get("next_actions", [])),
        "tags": _ensure_list(result.get("tags", [])),
    }


def _ensure_list(val: Any) -> List[str]:
    if isinstance(val, list):
        return [str(i) for i in val]
    if isinstance(val, str):
        return [val] if val else []
    return []


def _flatten_values(state: Dict[str, Any]) -> List[str]:
    """Extract readable strings from a state dict as fallback key_items."""
    items = []
    for k, v in state.items():
        if isinstance(v, list):
            items.extend(str(i) for i in v[:5])
        elif isinstance(v, str) and v:
            items.append(f"{k}: {v[:80]}")
    return items[:10]


# ---------------------------------------------------------------------------
# Convenience: pre-built llm_fn wrappers for common providers
# ---------------------------------------------------------------------------

def openai_llm(model: str = "gpt-4o-mini"):
    """Returns an llm_fn compatible with extract() using OpenAI."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError("pip install openai")
    client = AsyncOpenAI()

    async def llm_fn(system: str, user: str) -> str:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
        )
        return resp.choices[0].message.content or ""

    return llm_fn


def gemini_llm(model: str = "gemini-2.0-flash"):
    """Returns an llm_fn compatible with extract() using Gemini."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError("pip install google-generativeai")

    gmodel = genai.GenerativeModel(model)

    async def llm_fn(system: str, user: str) -> str:
        full_prompt = f"{system}\n\n{user}"
        response = await gmodel.generate_content_async(full_prompt)
        return response.text or ""

    return llm_fn

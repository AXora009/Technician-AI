"""LLM-powered tagger for ingested content.

Option B: each chunk gets {topic_path, entry_type, title} attached to its
metadata. Option C will reuse this same shape inside atomic entries — see
entry_types.ATOMIC_ENTRY_FIELDS.
"""
from __future__ import annotations

import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

import entry_types

load_dotenv(Path(__file__).resolve().parent / ".env")

# When False, tag_content returns rule-based defaults with no API call.
# Set USE_LLM_TAGGER=true in .env to re-enable Claude tagging during ingest.
USE_LLM_TAGGER: bool = os.getenv("USE_LLM_TAGGER", "false").lower() == "true"

MODEL = os.environ.get("TECHNICIAN_AI_MODEL", "claude-opus-4-7")

SYSTEM_PROMPT = """You classify chunks of technical documentation for a technician's knowledge base.

For each chunk, return:
- topic_path: 2-3 hierarchical labels, broad → narrow, lowercase snake_case (e.g. ["module_rework", "el_inspection"]).
- entry_type: exactly one of: {types}.
- title: short, ≤ 8 words, human-readable, captures the chunk's subject.

Strongly prefer reusing topic paths from the "existing topic paths" list when one fits the chunk. Only propose a new path when none of the existing ones apply. Keep the taxonomy small."""

SCHEMA = {
    "type": "object",
    "properties": {
        "topic_path": {"type": "array", "items": {"type": "string"}},
        "entry_type": {"type": "string", "enum": entry_types.ENTRY_TYPES},
        "title": {"type": "string"},
    },
    "required": ["topic_path", "entry_type", "title"],
    "additionalProperties": False,
}

_client: anthropic.Anthropic | None = None


def _cheap_tag(text: str, source_label: str) -> dict:
    """Rule-based fallback — no API call. Used when USE_LLM_TAGGER=false."""
    words = text.split()
    title = " ".join(words[:10]) if len(words) >= 4 else (source_label or "untitled")
    return {
        "topic_path": ["manual", source_label] if source_label else ["manual"],
        "entry_type": "reference",
        "title": title.strip()[:120],
    }


def _anthropic() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        print(f"[tagger] ANTHROPIC_API_KEY present: {bool(api_key)}", flush=True)
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def tag_content(
    text: str,
    source_label: str,
    existing_topics: list[list[str]] | None = None,
) -> dict:
    if not USE_LLM_TAGGER:
        return _cheap_tag(text, source_label)
    existing_block = ""
    if existing_topics:
        seen = set()
        sample: list[str] = []
        for tp in existing_topics:
            key = tuple(tp)
            if key in seen or not tp:
                continue
            seen.add(key)
            sample.append(" > ".join(tp))
            if len(sample) >= 50:
                break
        if sample:
            existing_block = "\n\nExisting topic paths:\n" + "\n".join(f"- {p}" for p in sample)

    user_message = f"Source: {source_label}{existing_block}\n\nChunk:\n{text}"

    response = _anthropic().messages.create(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT.format(types=", ".join(entry_types.ENTRY_TYPES)),
        messages=[{"role": "user", "content": user_message}],
        tools=[{
            "name": "tag_chunk",
            "description": "Tag a documentation chunk with topic_path, entry_type, and title.",
            "input_schema": SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "tag_chunk"},
    )
    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    result = tool_block.input if tool_block else {}
    # Defensive: clamp pathological outputs to a sane shape.
    path = [str(p).strip() for p in result.get("topic_path", []) if str(p).strip()][:4]
    if not path:
        path = ["unclassified"]
    return {
        "topic_path": path,
        "entry_type": result.get("entry_type") or "unknown",
        "title": (result.get("title") or "").strip()[:120] or "untitled",
    }

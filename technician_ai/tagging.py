"""LLM-powered tagger for ingested content.

Option B: each chunk gets {topic_path, entry_type, title} attached to its
metadata. Option C will reuse this same shape inside atomic entries — see
entry_types.ATOMIC_ENTRY_FIELDS.
"""
from __future__ import annotations

import json
import logging
import os

from . import entry_types
from . import llm as llm_client

log = logging.getLogger(__name__)

MODEL = os.environ.get("TECHNICIAN_AI_MODEL", "claude-opus-4-7")

SYSTEM_PROMPT = """You classify chunks of technical documentation for a technician's knowledge base.

For each chunk, return:
- topic_path: 2-3 hierarchical labels, broad → narrow, lowercase snake_case (e.g. ["module_rework", "el_inspection"]).
- entry_type: exactly one of: {types}.
- title: short, ≤ 8 words, human-readable, captures the chunk's subject.
- machine: the specific machine this document is about (e.g. "Glass Loading Machine", "Edge Trimming Machine"). Use a short, consistent name — the same document should always produce the same machine name. Set to null if the document is not specific to a single machine.

Strongly prefer reusing topic paths from the "existing topic paths" list when one fits the chunk. Only propose a new path when none of the existing ones apply. Keep the taxonomy small."""

BATCH_SYSTEM_PROMPT = """You classify chunks of technical documentation for a technician's knowledge base.

You will receive multiple numbered chunks. For EACH chunk, return:
- topic_path: 2-3 hierarchical labels, broad → narrow, lowercase snake_case (e.g. ["module_rework", "el_inspection"]).
- entry_type: exactly one of: {types}.
- title: short, ≤ 8 words, human-readable, captures the chunk's subject.
- machine: the specific machine this document is about (e.g. "Glass Loading Machine", "Edge Trimming Machine"). Use a short, consistent name — the same document should always produce the same machine name. Set to null if the document is not specific to a single machine.

Return a JSON object with a "results" array containing one object per chunk, in the same order as the input chunks.

Strongly prefer reusing topic paths from the "existing topic paths" list when one fits the chunk. Only propose a new path when none of the existing ones apply. Keep the taxonomy small."""

SCHEMA = {
    "type": "object",
    "properties": {
        "topic_path": {"type": "array", "items": {"type": "string"}},
        "entry_type": {"type": "string", "enum": entry_types.ENTRY_TYPES},
        "title": {"type": "string"},
        "machine": {"type": ["string", "null"]},
    },
    "required": ["topic_path", "entry_type", "title", "machine"],
    "additionalProperties": False,
}

BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": SCHEMA,
        },
    },
    "required": ["results"],
    "additionalProperties": False,
}

TAG_BATCH_SIZE = int(os.environ.get("TAG_BATCH_SIZE", "8"))

def tag_content(
    text: str,
    source_label: str,
    existing_topics: list[list[str]] | None = None,
) -> dict:
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

    raw = llm_client.chat(
        system=SYSTEM_PROMPT.format(types=", ".join(entry_types.ENTRY_TYPES)),
        user_message=user_message,
        model=MODEL,
        max_tokens=512,
        json_schema=SCHEMA,
        effort="low",
    )
    result = json.loads(raw)
    # Defensive: clamp pathological outputs to a sane shape.
    path = [str(p).strip() for p in result.get("topic_path", []) if str(p).strip()][:4]
    if not path:
        path = ["unclassified"]
    machine = result.get("machine")
    return {
        "topic_path": path,
        "entry_type": result.get("entry_type") or "unknown",
        "title": (result.get("title") or "").strip()[:120] or "untitled",
        "machine": machine.strip() if isinstance(machine, str) and machine.strip() else None,
    }


def _normalize_tag(result: dict) -> dict:
    path = [str(p).strip() for p in result.get("topic_path", []) if str(p).strip()][:4]
    if not path:
        path = ["unclassified"]
    machine = result.get("machine")
    return {
        "topic_path": path,
        "entry_type": result.get("entry_type") or "unknown",
        "title": (result.get("title") or "").strip()[:120] or "untitled",
        "machine": machine.strip() if isinstance(machine, str) and machine.strip() else None,
    }


def _build_existing_block(existing_topics: list[list[str]] | None) -> str:
    if not existing_topics:
        return ""
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
    if not sample:
        return ""
    return "\n\nExisting topic paths:\n" + "\n".join(f"- {p}" for p in sample)


def tag_content_batch(
    chunks: list[str],
    source_label: str,
    existing_topics: list[list[str]] | None = None,
) -> list[dict]:
    if not chunks:
        return []
    if len(chunks) == 1:
        return [tag_content(chunks[0], source_label, existing_topics)]

    existing_block = _build_existing_block(existing_topics)
    numbered = "\n\n".join(
        f"--- Chunk {i + 1} ---\n{text}" for i, text in enumerate(chunks)
    )
    user_message = f"Source: {source_label}{existing_block}\n\n{numbered}"

    log.info("batch-tagging %d chunks in one LLM call", len(chunks))
    raw = llm_client.chat(
        system=BATCH_SYSTEM_PROMPT.format(types=", ".join(entry_types.ENTRY_TYPES)),
        user_message=user_message,
        model=MODEL,
        max_tokens=256 * len(chunks),
        json_schema=BATCH_SCHEMA,
        effort="low",
    )
    parsed = json.loads(raw)
    results = parsed.get("results", [])

    if len(results) != len(chunks):
        log.warning(
            "batch tag returned %d results for %d chunks, falling back to single",
            len(results), len(chunks),
        )
        return [
            tag_content(c, source_label, existing_topics)
            for c in chunks
        ]

    return [_normalize_tag(r) for r in results]

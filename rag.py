from __future__ import annotations

import os
import re

import anthropic
import openai

import db
import tagger

EMBED_MODEL = "text-embedding-3-small"
ANSWER_MODEL = os.environ.get("TECHNICIAN_AI_MODEL", "claude-opus-4-7")
TOP_K = 6
CHUNK_CHARS = 1800
CHUNK_OVERLAP = 200
NO_EMBED_MAX_DOCS = 20

EMBEDDINGS_ENABLED = bool(os.environ.get("OPENAI_API_KEY"))

DIAGNOSE_SYSTEM_PROMPT = """You are Technician AI running a guided, multi-turn fault diagnosis.

The first user message contains source snippets from service manuals and field knowledge, the problem description, and a progress note showing how many questions have already been asked.

Turn-by-turn rules:
1. FIRST turn only: Read the problem and sources. Identify the 2-3 most plausible root causes. Ask ONE targeted, observable yes/no or short-answer question the technician can answer by inspecting the machine right now. Do NOT list the causes yet. Do NOT give repair steps.
2. FOLLOW-UP turns: Review every answer so far. Update your working hypothesis. Ask ONE new question that either confirms the leading cause or rules it out. Vary the type of check (visual, audible, measurement) to build a fuller picture.
3. MINIMUM QUESTIONS: Do NOT resolve until the progress note confirms at least 3 questions have been answered. The only exception is an immediately safety-critical situation (imminent injury, fire, or electrical hazard) — if that applies, say so explicitly and resolve immediately.
4. RESOLUTION: Only when you have gathered sufficient evidence, begin your response with exactly "RESOLVED:" on its own line, then provide all four sections:
   - Root cause: [one clear sentence]
   - Confidence: [High / Medium / Low] — [one sentence justification based on the evidence collected]
   - Repair steps: [numbered list, specific and actionable]
   - Sources: [cite inline as [#1], [#2] matching the numbered snippets]
5. Cite sources inline as [#N] in diagnostic questions too — note which source supports your hypothesis.
6. Never ask more than 6 questions total before resolving regardless of outcome.
7. One question per turn. Be concise. No preamble or filler."""

ANSWER_SYSTEM_PROMPT = """You are Technician AI, an assistant for technicians doing construction and parts-assembly work.

You answer questions using the provided source snippets. Two kinds of sources can appear:
- MANUAL: official manufacturer documentation.
- KNOWLEDGE: field-learned notes contributed by other technicians (often more practical than the manual, sometimes contradicting it).

Rules:
1. Ground every claim in the provided sources. Cite them inline as [#1], [#2], etc., matching the numbered snippets.
2. If the sources do not contain the answer, say so plainly. Do not guess.
3. When MANUAL and KNOWLEDGE conflict, surface both. Field knowledge often reflects real-world reality, but flag the conflict for the technician.
4. Be concise. Lead with the answer. Add the why or the steps only if it materially helps.
5. Never invent part numbers, torque specs, or measurements. If a precise value is needed and not in the sources, say so."""

STRUCTURE_SYSTEM_PROMPT = """You convert a technician's correction or new finding into a clean knowledge-base entry.

Output a compact entry with two fields: a canonical question (what someone would search for) and a self-contained answer (the field-learned fact, with any context needed to apply it). Strip filler. Preserve numbers, part references, and conditions exactly as the technician stated them."""

_openai_embed: openai.OpenAI | None = None
_anthropic: anthropic.Anthropic | None = None


def _openai_client() -> openai.OpenAI:
    global _openai_embed
    if _openai_embed is None:
        _openai_embed = openai.OpenAI()
    return _openai_embed


def _anthropic_client() -> anthropic.Anthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = anthropic.Anthropic()
    return _anthropic


def embed_texts(texts: list[str], input_type: str = "document") -> list[list[float]]:
    if not texts:
        return []
    if not EMBEDDINGS_ENABLED:
        raise RuntimeError("embed_texts called but OPENAI_API_KEY is not set")
    response = _openai_client().embeddings.create(input=texts, model=EMBED_MODEL)
    return [d.embedding for d in response.data]


def embed_query(text: str) -> list[float]:
    return embed_texts([text], input_type="query")[0]


def chunk_text(text: str, max_chars: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) <= max_chars:
        return [text] if text else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split = text.rfind("\n", start, end)
            if split == -1 or split <= start + max_chars // 2:
                split = text.rfind(". ", start, end)
            if split != -1 and split > start + max_chars // 2:
                end = split + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _format_sources(snippets: list[dict]) -> str:
    lines = []
    for i, s in enumerate(snippets, start=1):
        meta = s["metadata"]
        if s["kind"] == "manual_chunk":
            label = f"MANUAL — {meta.get('manual_title', 'unknown')}"
            if "page" in meta:
                label += f", p.{meta['page']}"
            elif "slide" in meta:
                label += f", slide {meta['slide']}"
        else:
            label = "KNOWLEDGE — field note"
            if meta.get("validated"):
                label += " (validated)"
        topic = meta.get("topic_path")
        entry_type = meta.get("entry_type")
        if topic:
            tag_bits = " > ".join(topic)
            if entry_type:
                tag_bits += f" / {entry_type}"
            label += f"  [{tag_bits}]"
        lines.append(f"[#{i}] {label}\n{s['text']}")
    return "\n\n".join(lines)


def answer_question(question: str) -> dict:
    # API-FREE PATH: no Anthropic call.
    # Retrieves the most relevant chunks from the local DB and returns them
    # directly as the answer. If OPENAI_API_KEY is set, uses OpenAI embeddings
    # to rank results; otherwise falls back to most-recent documents.
    # Zero Anthropic API cost regardless of call volume.
    if EMBEDDINGS_ENABLED:
        query_vec = embed_query(question)
        snippets = db.search_similar(query_vec, k=TOP_K)
    else:
        snippets = db.list_all_documents(limit=NO_EMBED_MAX_DOCS)

    if not snippets:
        answer = "No manuals or field notes found. Ingest a manual first (`python ingest.py <pdf>`)."
        conv_id = db.insert_conversation(question, answer, [])
        return {"answer": answer, "sources": [], "conversation_id": conv_id, "mode": "retrieval"}

    # Present the top retrieved passages directly — no synthesis step.
    shown = snippets[:3]
    parts = []
    for i, s in enumerate(shown, start=1):
        meta = s["metadata"]
        if s["kind"] == "manual_chunk":
            label = meta.get("manual_title", "Manual")
            if "page" in meta:
                label += f" — p.{meta['page']}"
            elif "slide" in meta:
                label += f" — slide {meta['slide']}"
        else:
            label = "Field note"
        parts.append(f"[#{i}] {label}\n{s['text']}")

    extra = len(snippets) - len(shown)
    suffix = f"\n\n— {extra} more result(s) in references below —" if extra > 0 else ""
    answer = "\n\n".join(parts) + suffix

    doc_ids = [s["id"] for s in snippets]
    conv_id = db.insert_conversation(question, answer, doc_ids)

    return {
        "answer": answer,
        "mode": "retrieval",
        "sources": [
            {
                "index": i + 1,
                "id": s["id"],
                "kind": s["kind"],
                "metadata": s["metadata"],
                "preview": s["text"][:200],
            }
            for i, s in enumerate(snippets)
        ],
        "conversation_id": conv_id,
    }


_ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": ["question", "answer"],
    "additionalProperties": False,
}


def structure_knowledge_entry(question: str, prior_answer: str, technician_note: str) -> dict:
    # ANTHROPIC API PATH: called only when a technician submits a "Didn't work"
    # or "+ Add field note" form. User-triggered and infrequent.
    user_message = (
        f"Original question: {question}\n\n"
        f"AI's previous answer: {prior_answer}\n\n"
        f"Technician's correction or finding: {technician_note}"
    )

    response = _anthropic_client().messages.create(
        model=ANSWER_MODEL,
        max_tokens=1024,
        system=STRUCTURE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[{
            "name": "save_entry",
            "description": "Save the structured knowledge entry with a canonical question and self-contained answer.",
            "input_schema": _ENTRY_SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "save_entry"},
    )
    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    result = tool_block.input if tool_block else {}
    return {
        "question": str(result.get("question", "")).strip() or technician_note[:80],
        "answer": str(result.get("answer", "")).strip() or technician_note,
    }


def diagnose_step(question: str, history: list[dict], questions_asked: int = 0) -> dict:
    """Multi-turn diagnostic. history is a list of prior {"role", "content"} turns
    (excluding the initial sources block, which is always prepended internally).
    questions_asked is the count of AI questions already sent before this call.
    Returns message, is_resolved, sources (only when resolved), conversation_id.

    ANTHROPIC API PATH: every call to this function makes one Anthropic API request.
    Used only when the user clicks "Diagnose", never for Submit Query.
    """
    if EMBEDDINGS_ENABLED:
        query_vec = embed_query(question)
        snippets = db.search_similar(query_vec, k=TOP_K)
    else:
        snippets = db.list_all_documents(limit=NO_EMBED_MAX_DOCS)

    if not snippets:
        msg = "No manuals or field notes found. Ingest a manual first."
        return {"message": msg, "is_resolved": False, "sources": [], "conversation_id": None}

    sources_block = _format_sources(snippets)
    context_note = (
        f"\n\n[Diagnostic progress: {questions_asked} question(s) asked so far. "
        f"Minimum 3 must be answered before resolving unless safety-critical.]"
    )
    initial_content = f"Sources:\n\n{sources_block}\n\n---\n\nProblem reported: {question}{context_note}"

    messages = [{"role": "user", "content": initial_content}] + history

    response = _anthropic_client().messages.create(
        model=ANSWER_MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": DIAGNOSE_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )

    raw = next((b.text for b in response.content if b.type == "text"), "")
    is_resolved = raw.startswith("RESOLVED:")
    message = raw[len("RESOLVED:"):].strip() if is_resolved else raw.strip()

    conv_id = None
    if is_resolved:
        doc_ids = [s["id"] for s in snippets]
        conv_id = db.insert_conversation(question, message, doc_ids)

    return {
        "message": message,
        "is_resolved": is_resolved,
        "sources": [
            {
                "index": i + 1,
                "id": s["id"],
                "kind": s["kind"],
                "metadata": s["metadata"],
                "preview": s["text"][:200],
            }
            for i, s in enumerate(snippets)
        ] if is_resolved else [],
        "conversation_id": conv_id,
    }


def record_knowledge_from_feedback(
    conversation_id: int, kind: str, note: str | None
) -> dict | None:
    conv = db.get_conversation(conversation_id)
    if conv is None:
        return None

    if kind == "worked":
        return None

    if not note:
        return None

    structured = structure_knowledge_entry(conv["question"], conv["answer"], note)
    text = f"Q: {structured['question']}\nA: {structured['answer']}"
    embedding = (
        embed_texts([text], input_type="document")[0] if EMBEDDINGS_ENABLED else None
    )
    tags = tagger.tag_content(
        text,
        source_label="(field knowledge)",
        existing_topics=db.list_existing_topic_paths(),
    )
    metadata = {
        "question": structured["question"],
        "source_conversation_id": conversation_id,
        "origin": kind,
        "topic_path": tags["topic_path"],
        "entry_type": tags["entry_type"],
        "title": tags["title"],
    }
    doc_id = db.insert_document(
        kind="knowledge_entry",
        text=text,
        embedding=embedding,
        metadata=metadata,
    )
    return {"id": doc_id, **structured}

from __future__ import annotations

import json
import os
import re

from . import database as db
from . import diagnosis as diagnosis_fsm
from . import embeddings as embed_client
from . import llm as llm_client
from . import safety as safety_gate
from . import tagging as tagger

ANSWER_MODEL = os.environ.get("TECHNICIAN_AI_MODEL", "claude-opus-4-7")
TOP_K = 6
CHUNK_CHARS = 1800
CHUNK_OVERLAP = 200
NO_EMBED_MAX_DOCS = 20

EMBEDDINGS_ENABLED = embed_client.EMBEDDINGS_ENABLED

# ---------------------------------------------------------------------------
# Reply-language template (i18n-style slot).
#
# The assistant infers the user's preferred language and replies in it. Add a
# language by adding one entry to SUPPORTED_LANGUAGES — the directive (the
# {languages} slot) and the system prompts pick it up automatically.
# ---------------------------------------------------------------------------
SUPPORTED_LANGUAGES = {
    # display name : native name
    "English": "English",
    "Spanish": "Español",
    "Chinese": "中文",
}

_LANGUAGE_DIRECTIVE_TEMPLATE = """REPLY LANGUAGE:
- Infer the user's preferred language from THEIR message and write all human-readable prose in that language.
- Supported reply languages: {languages}. If the user's language is none of these, reply in English.
- English is a lingua franca: when the user mixes English with another supported language, reply in the OTHER language (e.g. English + 中文 -> reply in 中文; English + Español -> reply in Español). If the message is wholly in one language, reply in that language.
- Write ALL natural-language prose in the user's language — including diagnosis questions, resolution content (likely cause, next steps, confirmed condition, confidence justification), and safety instructions.
- Keep the following in English regardless of user language: citation markers such as [#1]; part numbers, identifiers, units, and measurements; JSON field names (these are handled by the schema, not your text output)."""


def _detect_language(text: str) -> str:
    """Detect script/language from Unicode block heuristics.
    For non-Latin scripts we can be specific; for Latin-script languages
    we pass the sample text and let the model infer."""
    for ch in text:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            return "Chinese (中文)"
        if 0x3040 <= o <= 0x309F or 0x30A0 <= o <= 0x30FF:
            return "Japanese (日本語)"
        if 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF:
            return "Korean (한국어)"
        if 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F:
            return "Arabic (العربية)"
        if 0x0400 <= o <= 0x04FF:
            return "Russian (Русский)"
        if 0x0900 <= o <= 0x097F:
            return "Hindi (हिन्दी)"
        if 0x0E00 <= o <= 0x0E7F:
            return "Thai (ภาษาไทย)"
    # Latin-script languages: let the model infer from the actual text
    sample = text[:60].replace("\n", " ")
    return f"the same language as this text: \"{sample}\""


def _render_language_directive() -> str:
    languages = ", ".join(
        native if native == name else f"{name} ({native})"
        for name, native in SUPPORTED_LANGUAGES.items()
    )
    return _LANGUAGE_DIRECTIVE_TEMPLATE.format(languages=languages)


LANGUAGE_DIRECTIVE = _render_language_directive()

ANSWER_SYSTEM_PROMPT = """You are Technician AI, a friendly and experienced colleague who helps factory technicians with equipment questions, procedures, troubleshooting, and everyday workplace matters.

Sound like a real person on the shop floor — someone who's fixed these machines before and knows how to explain things simply. Use everyday words, not textbook language. Short sentences. Write the way you'd talk to a coworker standing next to you.

Formatting rules:
- If there are sequential steps that must be done in order, number them — each step on its own separate line (1.\n2.\n3.).
- If there are parallel items of the same type (e.g. a list of part numbers, a list of options), use bullet points — each item on its own separate line.
- Never put multiple list items on the same line.
- Otherwise, write in plain sentences — do not force lists where prose flows naturally.

Only acknowledge emotion if the user is clearly venting personal feelings (e.g. "我很累", "I'm exhausted"). Do NOT add empathy for equipment problems or production urgency. Skip any preamble and go straight to the answer. Never open with "好的", "明白了", "收到", "既然X", or any phrase that echoes what the user said. Start with the actual answer.

Source snippets from manuals and field notes are provided. Two kinds of sources can appear:
- MANUAL: official manufacturer documentation.
- KNOWLEDGE: field-learned notes contributed by other technicians.

Rules:
1. If the question is about equipment or procedures: use the sources to back up your answer and cite them inline as [#1], [#2], etc.
2. If the question is NOT about equipment, or if it's about any company-specific fact (HR policy, PTO, lunch, schedules, benefits, pay, safety rules, anything workplace-related) that is NOT in the provided sources: do NOT guess or invent an answer — even if you think you might know. Simply point them to the right person (HR, supervisor, team lead). Never fabricate facts about the company.
3. When MANUAL and KNOWLEDGE conflict, mention both. Real-world field experience often matters more than the manual.
4. Lead with the answer. Keep it short. Skip the preamble. Never use formal phrases like "根据手册", "建议您", "请注意" — just say it plainly.
5. Never invent part numbers, torque specs, or measurements. If a precise value isn't in the sources, say so."""

DIAGNOSE_SYSTEM_PROMPT = """You are Technician AI, a friendly and experienced colleague helping a factory technician figure out what's wrong with their equipment, one step at a time.

Sound like a real person on the shop floor — someone who's seen these problems before. Use plain everyday words, not textbook language. Short sentences. Ask one simple question at a time — don't pile on multiple questions at once. When you find the root cause, explain it the way you'd explain it to a coworker standing next to you, not like you're writing a report. Never mention the manual, documentation, or any source by name in your response text — use what you know from the sources, but don't say "according to the manual" or "consistent with the manual".

Formatting rules:
- If there are sequential steps that must be done in order, number them — each step on its own separate line (1.\n2.\n3.).
- If there are parallel items of the same type (e.g. a list of part numbers, a list of options), use bullet points — each item on its own separate line.
- Never put multiple list items on the same line.
- Otherwise, write in plain sentences — do not force lists where prose flows naturally.

Only acknowledge emotion if the user is clearly venting personal feelings (e.g. "我很累", "我快崩溃了", "I'm exhausted"). Do NOT add empathy for equipment problems, urgency, or production pressure — even if the situation sounds stressful. Go straight to the diagnostic question or finding. Never open with phrases that echo back what the user said — no "好的，收到", "明白了", "既然X，那么Y", "按钮坏了确实让人头疼", or any similar preamble. Just start with the action or question.

The user message contains: retrieved source snippets (manuals + field knowledge), the list of known machines, the machine identified so far (or "unknown"), the original problem, and the conversation so far. You reason over the whole conversation as your memory each turn. You MUST reply with a single JSON object matching the provided schema and nothing else.

SAFETY-CRITICAL DETECTION (evaluate before anything else):
Before applying any turn-by-turn rules, determine whether the reported problem involves an immediate hazard:
- Broken glass near mechanisms, conveyor belts, or personnel
- Injury or risk of injury to personnel
- Electric shock hazard or exposed live conductors
- Unexpected pneumatic or mechanical movement while personnel are near or inside the machine
- Personnel inside the machine
- Active fire, smoke, or chemical release
- Emergency-stop situations where the cause is unknown

If ANY of the above conditions are present or cannot be ruled out, respond with a SAFETY ALERT block BEFORE asking any diagnostic question. Format it exactly as:

SAFETY ALERT:
[Immediate hazard identified — one sentence describing it]

Required immediate actions:
1. [action]
2. [action]
...

Then ask ONE safety-verification question (e.g., "Is everyone clear of the machine and is the machine now fully stopped?") before proceeding to normal diagnosis. Do NOT ask about air pressure, gauge readings, operational parameters, root cause, or mechanical details until the technician confirms the immediate hazard is controlled.

For pneumatic movement incidents specifically: do not include broken-glass cleanup PPE instructions, door-closure instructions, or any undocumented energy-isolation steps. After air is confirmed isolated and personnel are clear, if further investigation near pneumatic mechanisms is needed, instruct the technician to follow their site-approved energy isolation procedure before proceeding. Do not present residual pressure bleeding or actuator position checks as documented requirements unless a retrieved source document explicitly states them.

For broken glass specifically (and ONLY for broken glass — do not apply these instructions to pneumatic, electrical, or other hazard types):
1. Do not reach into the machine or approach moving mechanisms.
2. Use the Emergency Stop if there is any immediate risk to personnel.
3. Keep machine doors closed and locked until the machine is fully stopped and de-energized.
4. Wear proper PPE before any cleanup of broken glass. Do not specify which PPE items unless a retrieved source explicitly lists them for broken-glass cleanup.
5. Ask whether anyone is injured and confirm the machine is safely stopped.
6. Report to supervisor and EHS — personnel safety events require escalation.

For pneumatic movement incidents (and ONLY for pneumatic incidents): do NOT include broken-glass cleanup instructions, PPE-for-cleanup instructions, or door-closure instructions. These are hazard-specific to broken glass only.

OUTPUT: Reply with a single JSON object matching the provided schema and nothing else. If you must issue the SAFETY ALERT described above, do it inside the JSON: set "action" to "ask" and put the alert text (hazard line + required immediate actions + the safety-verification question) in "message".

MACHINE FIRST: You are given the list of known machines. If the conversation does not clearly indicate which one the technician is on, your first action is "ask": briefly ask them to confirm which machine and list the known options. Keep "identified_machine" null until it is clear; then set it to the EXACT name from the list and proceed. Do not ask about the machine again once it is known.

MACHINE ALIASES (treat these as exact matches — do not ask for confirmation):
- "串焊机" → "All-in-One Soldering Machine"
- "串焊" → "All-in-One Soldering Machine"
- "Soldering Machine" → "All-in-One Soldering Machine"
- "soldering machine" → "All-in-One Soldering Machine"

REASON THEN DECIDE (every turn): Use "reasoning" to privately reassess the evidence so far and your leading hypothesis (not shown to the technician), then choose "action": "ask" one more question, or "resolve". There is NO minimum or maximum number of questions — decide based on the evidence, never on how many questions have been asked.

Turn rules:
0. ESCALATION CHECK (non-safety-critical): scan the retrieved sources for explicit escalation instructions — phrases like "report to team lead", "notify supervisor", "stop production", "contact maintenance", "do not continue", or "ask for equipment assistance". If the reported problem matches such an instruction, resolve immediately with that escalation directive instead of investigating.
1. Once the machine is known, identify the 2-3 most plausible root causes from the problem and sources, and ask ONE targeted, observable question the technician can answer by inspecting the machine right now. Do NOT list the causes; do NOT give repair steps yet. If the symptom is described as consistent ("always", "every time", "exactly", "same every time"), prioritise systematic causes (recent maintenance, setting/parameter changes, HMI calibration) over random ones (debris, slippage, misalignment).
2. FOLLOW-UP turns: ask ONE new question that confirms or rules out the leading cause. Vary the type of check (visual, audible, measurement) to build a fuller picture.
3. KEEP ASKING until you have at least one CONFIRMED observation that directly explains the symptom. If all evidence is approximate, suspected, or hearsay, ask one more targeted question instead of resolving.
4. Cite the source supporting your hypothesis inline as [#N] in your questions.
5. One question per turn. Be concise. No preamble or filler.

Evidence rules (apply at every turn):
8. A measured or observed condition that falls outside the source-defined operating standard may be stated as the blocking condition with high confidence. Do NOT elevate this to a specific component failure without direct evidence.
9. Do NOT name a specific component as the cause unless the technician has confirmed observable evidence of that component's failure, or a retrieved source explicitly links the symptom to that component.
10. For any safety door or interlock alarm: before concluding a sensor or latch failure, first ask whether any material, packaging, pallet, or physical obstruction is preventing the door from fully closing.
11. Only recommend repair or replacement steps that are explicitly supported by the retrieved sources. If the sources do not cover the required repair, instruct the technician to escalate to qualified maintenance personnel rather than inventing procedures.
12. REPAIR AUTHORIZATION: In Next steps, do NOT instruct the technician to "replace" or "swap" a part themselves unless the retrieved source explicitly authorizes that action for a line technician. Instead write: "Have Equipment Maintenance inspect and replace [part] using the approved maintenance procedure." or "Do not continue using the affected [component] until it has been inspected or replaced by authorized maintenance." Only say "you can replace" if a source explicitly grants that to the technician role.
13. NEGATIVE PRESSURE WORDING: When comparing a negative vacuum reading against a spec range, do NOT use vague phrases like "below the range" or "lower than expected." State explicitly: "The measured [X] kPa is outside the required [A] to [B] kPa range and indicates weaker-than-required vacuum." (Numerically, -65 kPa is weaker than -70 kPa; "below" is ambiguous for negative numbers.)

EVIDENCE CLASSIFICATION (apply internally every turn):
Classify each technician observation as one of:
- CONFIRMED: exact stated measurement, clearly stated visible defect, direct sensory observation with no hedging language.
  Examples: "The gauge reads -50 kPa", "There is a visible crack in the cup", "The belt is visibly jammed against the frame"
  NOTE: An alarm code (e.g. "HMI shows E-47") confirms that a fault was detected, but is NOT by itself a root cause. An alarm code is CONFIRMED evidence of a symptom only. You must ask at least one more question to identify the physical cause behind the alarm before resolving.
- APPROXIMATE: estimated or uncertain measurement with hedging.
  Examples: "It looked like about -50", "The gauge moved around some", "Roughly -70 kPa"
- SUSPECTED: plausible but unverified; technician hedges.
  Examples: "One cup might be dirty", "The stack may be crooked", "I think I heard a leak"
- HEARSAY: reported by others, not directly observed.
  Examples: "Someone said it stopped earlier", "The previous shift may have adjusted it"
- NEGATIVE: a condition explicitly ruled out.
  Examples: "No active alarm", "No visible cracks", "No one is injured"

RESOLVING (action = "resolve"): resolve only when at least one CONFIRMED observation directly explains the symptom. If all evidence is APPROXIMATE, SUSPECTED, or HEARSAY, ask one more targeted question that can yield a confirmed reading instead of resolving. Fill every field of the "resolution" object:
- likely_cause: the specific component or condition confirmed as the root cause, in one sentence.
- next_steps: ordered actions. Only recommend a repair/replacement a retrieved source authorizes for a line technician; otherwise write "Have qualified maintenance inspect/replace [part] using the approved procedure." Cite sources [#N].
- confirmed_condition: describe what the technician actually observed, in plain conversational language. State numeric comparisons explicitly (e.g. "vacuum was at -65 kPa, needs to be -70 kPa"). Never reference or mention the manual or any document — just describe what was seen or measured. Do NOT name a specific component as the cause unless the technician confirmed observable evidence of its failure.
- confidence_level: "high" ONLY when a CONFIRMED observation directly explains the symptom — a measurement outside a source-defined standard, a clearly visible defect, a documented alarm code together with a confirmed physical cause behind it, or two independent confirmed observations. Otherwise use "medium" or "low".
- confidence_justification: one plain sentence explaining why. Never cite or mention the manual. Write it as a person would say it — e.g. "We confirmed the vacuum pressure was low and the cups were worn" not "consistent with the manual's description of idle state".

For intermittent or multi-symptom problems, do not force a single root cause prematurely — keep alternatives open and recommend targeted verification rather than immediate replacement.

ESCALATION: when you cannot reach a confirmed root cause, or you are told the session has run long, resolve with an escalation recommendation — confidence_level "low" or "medium", confirmed_condition stating what is and isn't established, and next_steps directing the technician to escalate to qualified maintenance or a supervisor with the evidence gathered so far.

OFF-TOPIC MESSAGES: If the user's message is clearly NOT a factory equipment or machinery problem — this includes HR/policy questions, personal feelings, tiredness, stress, emotional venting, general complaints, or anything not about a specific machine fault — respond ONLY with a warm, brief `message` in the user's language. Do NOT ask which machine they are on. Do NOT add any phrase like "if you have equipment questions, I'm here" or any reference to equipment at all. Do NOT ask any follow-up questions of any kind. Set action to "ask", identified_machine to null, resolution to null. If the conversation has been personal/emotional for multiple turns, continue responding purely as a supportive presence — no equipment mentions ever."""

# Structured per-turn decision the diagnosis agent must return.
DIAGNOSE_DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "identified_machine": {"type": ["string", "null"]},
        "reasoning": {"type": "string"},
        "action": {"type": "string", "enum": ["ask", "resolve"]},
        "message": {"type": "string"},
        "resolution": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "likely_cause": {"type": "string"},
                "next_steps": {"type": "array", "items": {"type": "string"}},
                "confirmed_condition": {"type": "string"},
                "confidence_level": {"type": "string", "enum": ["high", "medium", "low"]},
                "confidence_justification": {"type": "string"},
            },
            "required": [
                "likely_cause", "next_steps", "confirmed_condition",
                "confidence_level", "confidence_justification",
            ],
        },
    },
    "required": ["identified_machine", "reasoning", "action", "message", "resolution"],
}

# Append the reply-language directive so every answer/diagnosis turn honors it.
ANSWER_SYSTEM_PROMPT = ANSWER_SYSTEM_PROMPT + "\n\n" + LANGUAGE_DIRECTIVE
DIAGNOSE_SYSTEM_PROMPT = DIAGNOSE_SYSTEM_PROMPT + "\n\n" + LANGUAGE_DIRECTIVE


def _downgrade_unwarranted_confidence(resolution: dict, session: dict | None) -> dict:
    """Backstop: drop HIGH confidence to medium when the logged observations are
    all uncertain. Only fires when there ARE substantive per-turn observations to
    judge — on a direct first-turn resolve (no replies logged yet) we trust the
    agent, which reasoned over the full problem description itself.
    """
    if session is not None:
        substantive = [e for e in session.get("evidence_log", []) if e != "NEGATIVE"]
    else:
        substantive = []
    if (
        resolution.get("confidence_level") == "high"
        and session is not None
        and substantive
        and not diagnosis_fsm.high_confidence_warranted(session)
    ):
        resolution["confidence_level"] = "medium"
        note = (
            "Confidence adjusted to medium — observations were approximate or uncertain; "
            "confirm with a direct measurement before any repair."
        )
        just = (resolution.get("confidence_justification") or "").strip()
        resolution["confidence_justification"] = f"{just} {note}".strip()
    return resolution


STRUCTURE_SYSTEM_PROMPT = """You convert a technician's correction or new finding into a clean knowledge-base entry.

Output a compact entry with two fields: a canonical question (what someone would search for) and a self-contained answer (the field-learned fact, with any context needed to apply it). Strip filler. Preserve numbers, part references, and conditions exactly as the technician stated them."""

def embed_texts(texts: list[str], input_type: str = "document") -> list[list[float]]:
    if not texts:
        return []
    if not EMBEDDINGS_ENABLED:
        raise RuntimeError("embed_texts called but no embedding provider is configured")
    return embed_client.embed_texts(texts, input_type=input_type)


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


_REPAIR_ACTION_RE = re.compile(
    r"\b(replace\s+the|replace\s+sensor|rewire|swap\s+out\s+the|install\s+new)\b",
    re.IGNORECASE,
)
_CITATION_RE = re.compile(r"\[#\d+\]")
_ESCALATE_RE = re.compile(r"\bescalate\b", re.IGNORECASE)

_GROUNDING_NOTE = (
    "\n\n_Note: No source document was retrieved supporting this repair procedure. "
    "Escalate to qualified maintenance personnel._"
)


def grounding_guard(response: str) -> str:
    """Append a grounding disclaimer if the response suggests uncited repair actions.

    The check fires when ALL of the following are true:
    - The response contains a repair-action phrase (replace, rewire, swap out, etc.)
    - The response contains no inline citations ([#N])
    - The response does not already contain an escalation instruction

    Returns the (possibly augmented) response string.
    """
    if (
        _REPAIR_ACTION_RE.search(response)
        and not _CITATION_RE.search(response)
        and not _ESCALATE_RE.search(response)
    ):
        return response + _GROUNDING_NOTE
    return response


def answer_question(question: str) -> dict:
    if EMBEDDINGS_ENABLED:
        query_vec = embed_query(question)
        snippets = db.search_similar(query_vec, k=TOP_K)
    else:
        snippets = db.search_by_keywords(question, k=TOP_K)

    if not snippets:
        answer = "I don't have any manuals or field notes ingested yet. Run `python ingest.py <pdf>` to load a manual."
        conv_id = db.insert_conversation(question, answer, [])
        return {"answer": answer, "sources": [], "conversation_id": conv_id}

    sources_block = _format_sources(snippets)
    user_message = f"Sources:\n\n{sources_block}\n\n---\n\nQuestion: {question}"

    answer = llm_client.chat(
        system=ANSWER_SYSTEM_PROMPT,
        user_message=user_message,
        model=ANSWER_MODEL,
        max_tokens=2048,
        cache_system=True,
    )
    answer = grounding_guard(answer)
    doc_ids = [s["id"] for s in snippets]
    conv_id = db.insert_conversation(question, answer, doc_ids)

    return {
        "answer": answer,
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


def structure_knowledge_entry(question: str, prior_answer: str, technician_note: str) -> dict:
    user_message = (
        f"Original question: {question}\n\n"
        f"AI's previous answer: {prior_answer}\n\n"
        f"Technician's correction or finding: {technician_note}\n\n"
        "Return JSON with two fields: 'question' (canonical search-style question) and 'answer' (the field-learned fact, self-contained)."
    )

    text = llm_client.chat(
        system=STRUCTURE_SYSTEM_PROMPT,
        user_message=user_message,
        model=ANSWER_MODEL,
        max_tokens=1024,
        json_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "answer": {"type": "string"},
            },
            "required": ["question", "answer"],
            "additionalProperties": False,
        },
    )
    return json.loads(text)


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


def record_field_note(
    question: str,
    answer: str,
    comment: str,
    source_id: str | int,
    source_type: str,
    machine: str | None = None,
) -> dict:
    """Save a technician's field comment as an internal knowledge entry."""
    prefix = f"Machine: {machine}\n" if machine else ""
    text = f"{prefix}Q: {question}\nA: {answer}\nField note: {comment}"
    embedding = (
        embed_texts([text], input_type="document")[0] if EMBEDDINGS_ENABLED else None
    )
    tags = tagger.tag_content(
        text,
        source_label="(field feedback)",
        existing_topics=db.list_existing_topic_paths(),
    )
    metadata = {
        "question": question,
        "source_id": str(source_id),
        "source_type": source_type,
        "origin": "field_feedback",
        "topic_path": tags["topic_path"],
        "entry_type": tags["entry_type"],
        "title": tags["title"],
    }
    if machine:
        metadata["machine"] = machine
    doc_id = db.insert_document(
        kind="knowledge_entry",
        text=text,
        embedding=embedding,
        metadata=metadata,
    )
    return {"id": doc_id}


def _parse_decision(raw: str) -> dict:
    """Parse the agent's JSON decision, tolerating stray text around the object."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"\{[\s\S]*\}", raw or "")
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    # Fallback: keep the loop alive by treating the text as a question.
    return {
        "action": "ask",
        "message": (raw or "").strip(),
        "identified_machine": None,
        "resolution": None,
    }


def diagnose_step(
    question: str,
    history: list[dict],
    questions_asked: int = 0,
    session: dict | None = None,
    machine: str | None = None,
    machine_options: list[str] | None = None,
    escalate: bool = False,
) -> dict:
    """Run one turn of the guided fault-diagnosis agent.

    The deterministic safety gate runs first (unchanged). Once safety is clear,
    the LLM agent reasons over the full conversation and returns a structured
    decision: identify the machine if unclear, ask one more question, or resolve.
    There is no hardcoded question count — the agent decides when to conclude.

    Parameters
    ----------
    question:        original problem description (never changes across turns).
    history:         alternating assistant / user messages from prior turns.
    questions_asked: assistant turns so far (kept for backward compatibility).
    session:         FSM session dict (safety state + evidence-quality memory).
    machine:         machine confirmed so far, or None.
    machine_options: known machine names offered when the machine is unclear.
    escalate:        when True, nudge the agent to conclude with an escalation.

    Returns a dict with: message, is_resolved, resolution, phase, machine,
    identified_machine, is_safety_critical, hazard_type, sources, conversation_id.
    """
    # ------------------------------------------------------------------
    # 1. Safety gate — deterministic pre-flight check on the first turn.
    #    Fires when: no history yet AND the problem matches a hazard pattern.
    # ------------------------------------------------------------------
    is_first_turn = not history
    hazard_type: str | None = None

    if is_first_turn:
        hazard_type = safety_gate.classify_safety_critical(question)
        if hazard_type is not None:
            safety_response = safety_gate.build_safety_response(hazard_type)

            # Stamp the session into SAFETY_CHECK state so follow-up turns
            # know to stay in safety mode until the hazard is confirmed.
            if session is not None:
                diagnosis_fsm.new_session.__doc__  # no-op to ensure module loaded
                # Overwrite session in-place with FSM-managed fields; preserve
                # any app.py keys that already exist (question, history).
                fsm_session = diagnosis_fsm.new_session(
                    question, is_safety_critical=True, hazard_type=hazard_type
                )
                # Merge FSM fields into the live session dict.
                for k, v in fsm_session.items():
                    if k not in ("question", "history"):
                        session[k] = v

            return {
                "message": safety_response,
                "is_resolved": False,
                "resolution": None,
                "phase": "safety_hold",
                "machine": machine,
                "identified_machine": None,
                "is_safety_critical": True,
                "hazard_type": hazard_type,
                "sources": [],
                "conversation_id": None,
            }

    # ------------------------------------------------------------------
    # 1b. SAFETY_HOLD enforcement — subsequent turns of a safety-critical
    #     session.  Fires when: history exists AND session is still in
    #     SAFETY_CHECK (prerequisites not all confirmed).
    #     The LLM is NOT called; a code-generated response is returned.
    # ------------------------------------------------------------------
    if (
        not is_first_turn
        and session is not None
        and session.get("is_safety_critical")
        and session.get("state") == diagnosis_fsm.STATE_SAFETY_CHECK
    ):
        hazard = session.get("hazard_type")
        prerequisites = session.get("prerequisites", {})

        if hazard:
            # Parse the latest technician response for prerequisite confirmations.
            latest_user = next(
                (m["content"] for m in reversed(history) if m["role"] == "user"),
                "",
            )
            if latest_user:
                safety_gate.update_prerequisites(hazard, prerequisites, latest_user)
                session["prerequisites"] = prerequisites

            if safety_gate.all_prerequisites_met(hazard, prerequisites):
                # All prerequisites now confirmed — leave SAFETY_HOLD.
                session["state"] = diagnosis_fsm.STATE_SYMPTOM_GATHERING
                session["safety_confirmed"] = True
                # Fall through to normal retrieval and LLM.
            else:
                # Still in SAFETY_HOLD — return code-generated response only.
                unmet = safety_gate.get_unmet_prerequisites(hazard, prerequisites)
                return {
                    "message": safety_gate.build_safety_hold_response(hazard, unmet),
                    "is_resolved": False,
                    "resolution": None,
                    "phase": "safety_hold",
                    "machine": machine,
                    "identified_machine": None,
                    "is_safety_critical": True,
                    "hazard_type": hazard,
                    "sources": [],
                    "conversation_id": None,
                }

    # ------------------------------------------------------------------
    # 2. Retrieval — scope to the confirmed machine's manual when known.
    # ------------------------------------------------------------------
    retrieval_query = f"{machine} {question}" if machine else question
    if EMBEDDINGS_ENABLED:
        snippets = db.search_similar(embed_query(retrieval_query), k=TOP_K)
    else:
        snippets = db.search_by_keywords(retrieval_query, k=TOP_K, machine=machine)

    if not snippets:
        return {
            "message": "No manuals or field notes found. Ingest a manual first.",
            "is_resolved": False,
            "resolution": None,
            "phase": "investigating",
            "machine": machine,
            "identified_machine": None,
            "is_safety_critical": False,
            "hazard_type": None,
            "sources": [],
            "conversation_id": None,
        }

    # ------------------------------------------------------------------
    # 3. System prompt + safety/evidence notes (no counts) + escalation nudge.
    # ------------------------------------------------------------------
    system_prompt = DIAGNOSE_SYSTEM_PROMPT
    if session is not None:
        fsm_addition = diagnosis_fsm.get_state_prompt_addition(session)
        if fsm_addition:
            system_prompt += "\n\n" + fsm_addition
    if escalate:
        system_prompt += (
            "\n\n[ESCALATION] This session has run long without a confirmed root "
            "cause. Prefer to resolve now with an escalation recommendation rather "
            "than asking further questions."
        )

    # ------------------------------------------------------------------
    # 4. Assemble the conversation and request a structured decision.
    # ------------------------------------------------------------------
    sources_block = _format_sources(snippets)
    known = ", ".join(machine_options) if machine_options else "(none configured)"
    convo = "\n".join(
        f"[{m['role'].upper()}]: {m['content']}" for m in history
    ) or "(no replies yet)"
    detected_lang = _detect_language(question)
    user_message = (
        f"Known machines: {known}\n"
        f"Machine identified so far: {machine or 'unknown'}\n\n"
        f"Sources:\n\n{sources_block}\n\n---\n\n"
        f"Problem reported: {question}\n\n"
        f"Conversation so far:\n{convo}"
    )
    # Inject language into all text field descriptions so Gemini honors it
    # even in structured-output mode (it reads field descriptions).
    import copy as _copy
    lang_note = f"MUST be in {detected_lang}."
    schema_with_lang = _copy.deepcopy(DIAGNOSE_DECISION_SCHEMA)
    schema_with_lang["properties"]["message"] = {
        "type": "string",
        "description": f"{lang_note} Your question or reply to the technician.",
    }
    res_props = schema_with_lang["properties"]["resolution"].get("properties", {})
    for field in ("likely_cause", "confirmed_condition", "confidence_justification"):
        if field in res_props:
            res_props[field]["description"] = lang_note
    if "next_steps" in res_props:
        res_props["next_steps"]["description"] = f"Each step {lang_note}"
        if isinstance(res_props["next_steps"].get("items"), dict):
            res_props["next_steps"]["items"]["description"] = lang_note
    raw = llm_client.chat(
        system=system_prompt,
        user_message=user_message,
        model=ANSWER_MODEL,
        max_tokens=1024,
        json_schema=schema_with_lang,
        cache_system=True,
    )

    # ------------------------------------------------------------------
    # 5. Parse the structured decision.
    # ------------------------------------------------------------------
    decision = _parse_decision(raw)
    identified_machine = decision.get("identified_machine")
    _res = decision.get("resolution")
    # Treat dummy/off-topic resolutions as non-resolved so the chat shows
    # the message as plain text rather than a resolution card.
    _NA = {"n/a", "na", "—", "-", ""}
    _offtopic_phrases = ("issue is resolved", "no further action", "user confirmed", "not machine")
    if isinstance(_res, dict):
        _lc = _res.get("likely_cause", "").strip().lower()
        if _lc in _NA or any(p in _lc for p in _offtopic_phrases):
            _res = None
            decision["resolution"] = None
            decision["action"] = "ask"
    is_resolved = (
        decision.get("action") == "resolve"
        and isinstance(decision.get("resolution"), dict)
    )

    # ------------------------------------------------------------------
    # 6. Advance safety / evidence-quality memory from the latest answer.
    # ------------------------------------------------------------------
    if session is not None and not is_first_turn:
        technician_answer = next(
            (m["content"] for m in reversed(history) if m["role"] == "user"), ""
        )
        updated = diagnosis_fsm.advance_state(
            session,
            llm_response=("RESOLVED:" if is_resolved else decision.get("message", "")),
            technician_answer=technician_answer,
        )
        for k, v in updated.items():
            if k != "history":  # history is owned by the caller
                session[k] = v

    confirmed_machine = machine or identified_machine

    # ------------------------------------------------------------------
    # 7. Build the turn result.
    # ------------------------------------------------------------------
    if is_resolved:
        resolution = _downgrade_unwarranted_confidence(dict(decision["resolution"]), session)
        doc_ids = [s["id"] for s in snippets]
        conv_id = db.insert_conversation(
            question, resolution.get("likely_cause", ""), doc_ids
        )
        return {
            "message": (decision.get("message") or "").strip(),
            "is_resolved": True,
            "resolution": resolution,
            "phase": "resolved",
            "machine": confirmed_machine,
            "identified_machine": identified_machine,
            "is_safety_critical": False,
            "hazard_type": None,
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

    # action == "ask"
    phase = "investigating" if confirmed_machine else "identify_machine"
    message = (decision.get("message") or "").strip() or (
        "Could you tell me a bit more about what you're seeing?"
    )
    return {
        "message": message,
        "is_resolved": False,
        "resolution": None,
        "phase": phase,
        "machine": confirmed_machine,
        "identified_machine": identified_machine,
        "is_safety_critical": False,
        "hazard_type": None,
        "sources": [],
        "conversation_id": None,
    }

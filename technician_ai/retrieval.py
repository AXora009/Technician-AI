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

DIAGNOSE_SYSTEM_PROMPT = """You are Technician AI running a guided, multi-turn fault diagnosis.

The first user message contains source snippets from service manuals and field knowledge, the problem description, and a progress note showing how many questions have already been asked.

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

Turn-by-turn rules:
1. FIRST turn only (non-safety-critical): Read the problem and sources. Identify the 2-3 most plausible root causes. Ask ONE targeted, observable yes/no or short-answer question the technician can answer by inspecting the machine right now. Do NOT list the causes yet. Do NOT give repair steps.
2. FOLLOW-UP turns: Internally update your working hypothesis. Do NOT output a summary of findings, a working hypothesis block, or intermediate confidence ratings — just ask ONE new question that either confirms the leading cause or rules it out. Vary the type of check (visual, audible, measurement) to build a fuller picture.
3. KEEP ASKING: Do NOT resolve until you have at least one CONFIRMED observation that directly explains the symptom. If all evidence so far is approximate, suspected, or hearsay, ask one more targeted question. Only stop when the root cause is confirmed — not based on how many questions have been asked. The only exception is an immediately safety-critical situation.
4. RESOLUTION: Only when you have at least one CONFIRMED observation, begin your response with exactly "RESOLVED:" on its own line, then immediately use the exact section labels defined in RESOLUTION OUTPUT STRUCTURE below — do not use markdown headers (##), emojis, or any other format.
5. Cite sources inline as [#N] in diagnostic questions too — note which source supports your hypothesis.
6. Never ask more than 6 questions total before resolving regardless of outcome.
7. One question per turn. Be concise. No preamble or filler.

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

Uncertainty language markers (when present, classify as APPROXIMATE or SUSPECTED, not CONFIRMED):
maybe / might / I think / I'm not sure / not really sure / hard to tell / looked like /
probably / roughly / around / about / kind of / sort of / someone said / I wasn't watching /
I didn't check / not 100% / I guess / unclear / can't tell / I didn't really / seems like /
could be / may be / I believe.

RESOLUTION THRESHOLD — non-safety scenarios:
Do NOT resolve with HIGH confidence unless at least one of the following is true:
1. A CONFIRMED, stated measurement is outside a source-defined operating standard and directly explains the symptom.
2. A CONFIRMED, clearly visible physical defect directly explains the symptom (no hedging from technician).
3. A documented alarm code AND a CONFIRMED physical field observation both converge on the same root cause. The alarm code alone is not sufficient — the physical cause behind the alarm must be confirmed by the technician.
4. Two independent CONFIRMED observations independently support the same root cause.

When all available evidence is APPROXIMATE, SUSPECTED, or HEARSAY:
- Do NOT resolve with HIGH confidence.
- Use MEDIUM or LOW confidence.
- Preserve alternative explanations not yet ruled out.
- Either ask one more targeted confirmation question, or output a working hypothesis with LOW/MEDIUM confidence.

RESOLUTION OUTPUT STRUCTURE — use these exact section labels, in this exact order:

If CONFIRMED evidence supports the conclusion, output exactly:
  RESOLVED:

  Likely cause:
  [Specific component or condition confirmed as the root cause. One sentence, plain English.]

  Next steps:
  1. [First action — source-supported]
  2. [Second action — source-supported]
  3. [If repair not covered by sources: "Escalate to qualified maintenance personnel"]

  Confirmed condition:
  [The specific observation(s) that confirmed the root cause, with source citation [#N].]

  Confidence: High
  [One sentence justification.]

  Sources: [#N], [#N]

Use "Confidence: High", "Confidence: Medium", or "Confidence: Low" on ONE line — value immediately after the colon.
Do NOT use markdown headers (##), emojis, bold labels, or bullet dashes for section labels.

If evidence is APPROXIMATE, SUSPECTED, or mixed:
  Do NOT output RESOLVED. Ask ONE more targeted question to obtain a CONFIRMED observation.

INTERMITTENT / MULTI-SYMPTOM BEHAVIOR:
When a symptom is intermittent (sometimes works, sometimes does not) or involves multiple overlapping symptoms with no active alarm:
- Do not force a single root cause prematurely.
- Identify the most useful next evidence to collect.
- Compare measurements against documented standards only when the reading is CONFIRMED.
- Keep alternative contributors open until actively ruled out by confirmed evidence.
- Recommend targeted verification rather than immediate replacement or repair.

DO NOT label an issue as "Blocking condition" unless it is supported by a CONFIRMED observation or a CONFIRMED measurement against a source-defined standard."""

_HIGH_CONFIDENCE_RE = re.compile(r"Confidence:\s*High", re.IGNORECASE)


def _enforce_evidence_quality(response: str, session: dict | None) -> str:
    """Downgrade unwarranted HIGH confidence claims in RESOLVED responses.

    If the LLM emits 'Confidence: High' but the FSM session has no CONFIRMED
    observations, downgrade to Medium and append an advisory note.
    This is a safety net — the prompt instructions should prevent this in most
    cases, but the code-level check catches any slip-through.
    """
    if not _HIGH_CONFIDENCE_RE.search(response):
        return response
    if session is None or diagnosis_fsm.high_confidence_warranted(session):
        return response
    downgraded = _HIGH_CONFIDENCE_RE.sub("Confidence: Medium", response)
    downgraded += (
        "\n\n_Note: Confidence adjusted to Medium — observations were approximate "
        "or uncertain. A targeted confirmation step is recommended before initiating "
        "any repair or replacement._"
    )
    return downgraded


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


def _parse_resolution(message: str) -> dict:
    """Extract structured fields from a RESOLVED message.

    Uses position-based slicing: finds each section label in the text,
    then extracts the content block between that label and the next one.
    Works whether the content is on the same line or the next line.
    Handles both new plain-label format and old ## markdown-header format.
    """
    print("[_parse_resolution] raw input:\n", repr(message[:800]))

    label_patterns: dict[str, list[str]] = {
        "likely_cause":       [r"^Likely cause:",          r"^##[^\n]*Root Cause"],
        "next_steps":         [r"^Next steps?:",            r"^##[^\n]*Next Steps?"],
        "confirmed_condition":[r"^Confirmed condition:",    r"^##[^\n]*Issue Identified"],
        "confidence":         [r"^Confidence:",             r"\*\*Confidence:\*\*"],
        "sources":            [r"^Sources:"],
    }

    # Find the start + end of each label in the text
    positions: dict[str, tuple[int, int]] = {}
    for key, patterns in label_patterns.items():
        for p in patterns:
            m = re.search(p, message, re.IGNORECASE | re.MULTILINE)
            if m:
                positions[key] = (m.start(), m.end())
                break

    def get_content(key: str) -> str:
        if key not in positions:
            return ""
        _, label_end = positions[key]
        label_start = positions[key][0]
        # Next section starts at the minimum start position that is > label_start
        next_start = len(message)
        for other_key, (other_start, _) in positions.items():
            if other_start > label_start:
                next_start = min(next_start, other_start)
        raw = message[label_end:next_start].strip()
        # Strip markdown bold markers
        return re.sub(r"\*\*([^*]+)\*\*", r"\1", raw).strip()

    likely_cause       = get_content("likely_cause")
    next_steps_raw     = get_content("next_steps")
    confirmed_condition= get_content("confirmed_condition")
    confidence_raw     = get_content("confidence")

    # Parse confidence level + justification
    confidence_level = "medium"
    confidence_justification = ""
    if confidence_raw:
        cm = re.match(r"(high|medium|low)[^\w]*(.*)", confidence_raw, re.IGNORECASE | re.DOTALL)
        if cm:
            confidence_level = cm.group(1).lower()
            confidence_justification = re.sub(r"^[—–\-\s]+", "", cm.group(2)).strip()

    # Parse next steps into a list
    next_steps: list[str] = []
    for line in next_steps_raw.split("\n"):
        line = re.sub(r"^[\d]+[.)]\s*", "", line.strip())
        line = re.sub(r"^[-•*]\s*", "", line)
        if line:
            next_steps.append(line)

    result = {
        "likely_cause": likely_cause,
        "next_steps": next_steps,
        "confirmed_condition": confirmed_condition,
        "confidence_level": confidence_level,
        "confidence_justification": confidence_justification,
    }
    print("[_parse_resolution] parsed:", result)
    return result


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


def diagnose_step(
    question: str,
    history: list[dict],
    questions_asked: int = 0,
    session: dict | None = None,
) -> dict:
    """Run one turn of the guided fault-diagnosis FSM.

    Parameters
    ----------
    question:
        The original problem description (never changes across turns).
    history:
        Alternating assistant / user messages from all prior turns.
    questions_asked:
        Count of assistant turns already completed (used when *session* is None).
    session:
        Optional FSM session dict managed by the caller (app.py's
        _diag_sessions).  When provided, the safety gate and FSM state machine
        are fully active.  When None the function degrades gracefully to the
        original behaviour (backward-compatible).

    Returns
    -------
    dict with keys:
        message           : str   — assistant text to display
        is_resolved       : bool
        is_safety_critical: bool  — True if a safety alert was issued this turn
        hazard_type       : str | None
        sources           : list  — populated on RESOLVED turns only
        conversation_id   : int | None
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
                    "is_safety_critical": True,
                    "hazard_type": hazard,
                    "sources": [],
                    "conversation_id": None,
                }

    # ------------------------------------------------------------------
    # 2. Retrieval — unchanged from original logic.
    # ------------------------------------------------------------------
    if EMBEDDINGS_ENABLED:
        query_vec = embed_query(question)
        snippets = db.search_similar(query_vec, k=TOP_K)
    else:
        snippets = db.search_by_keywords(question, k=TOP_K)

    if not snippets:
        return {
            "message": "No manuals or field notes found. Ingest a manual first.",
            "is_resolved": False,
            "is_safety_critical": False,
            "hazard_type": None,
            "sources": [],
            "conversation_id": None,
        }

    # ------------------------------------------------------------------
    # 3. Build system prompt, optionally enriched with FSM state context.
    # ------------------------------------------------------------------
    system_prompt = DIAGNOSE_SYSTEM_PROMPT
    if session is not None:
        fsm_addition = diagnosis_fsm.get_state_prompt_addition(session)
        if fsm_addition:
            system_prompt = system_prompt + fsm_addition

    # ------------------------------------------------------------------
    # 4. Assemble conversation and call the LLM.
    # ------------------------------------------------------------------
    sources_block = _format_sources(snippets)
    qa_count = (
        session["questions_asked"]
        if session is not None and "questions_asked" in session
        else questions_asked
    )
    evidence_note = ""
    if session is not None:
        ev_log = session.get("evidence_log", [])
        if ev_log:
            counts = {q: ev_log.count(q) for q in ("CONFIRMED", "APPROXIMATE", "SUSPECTED", "HEARSAY", "NEGATIVE") if ev_log.count(q)}
            ev_summary = ", ".join(f"{v} {k}" for k, v in counts.items())
            warranted = diagnosis_fsm.high_confidence_warranted(session)
            evidence_note = (
                f" Evidence quality this session: {ev_summary}. "
                + ("HIGH confidence warranted." if warranted
                   else "HIGH confidence NOT warranted — all observations approximate or uncertain.")
            )
    context_note = (
        f"\n\n[Diagnostic progress: {qa_count} question(s) asked so far. "
        f"Resolve only when root cause is CONFIRMED — keep asking if uncertain.{evidence_note}]"
    )
    initial_content = (
        f"Sources:\n\n{sources_block}\n\n---\n\n"
        f"Problem reported: {question}"
    )
    system_prompt = system_prompt + context_note
    messages = [{"role": "user", "content": initial_content}] + history
    packed = "\n\n".join(
        f"[{m['role'].upper()}]: {m['content']}" for m in messages
    )
    raw = llm_client.chat(
        system=system_prompt,
        user_message=packed,
        model=ANSWER_MODEL,
        max_tokens=1024,
        cache_system=True,
    )

    # ------------------------------------------------------------------
    # 5. FSM resolution guard — if the LLM wants to resolve but the FSM
    #    says it is too early, strip the RESOLVED: prefix and make a second
    #    call with the block reason injected.
    # ------------------------------------------------------------------
    if raw.startswith("RESOLVED:") and session is not None:
        allowed, block_reason = diagnosis_fsm.check_resolution_allowed(session)
        if not allowed:
            # Re-prompt with the block reason appended so the LLM asks
            # another question instead of resolving prematurely.
            override_system = system_prompt + f"\n\n[FSM RESOLUTION BLOCKED] {block_reason}"
            raw = llm_client.chat(
                system=override_system,
                user_message=packed,
                model=ANSWER_MODEL,
                max_tokens=1024,
                cache_system=True,
            )

    # ------------------------------------------------------------------
    # 6. Parse response.
    # ------------------------------------------------------------------
    is_resolved = raw.startswith("RESOLVED:")
    message = raw[len("RESOLVED:"):].strip() if is_resolved else raw.strip()
    message = re.sub(r"\[Diagnostic progress:[^\]]*\]\s*", "", message).strip()

    if is_resolved:
        message = grounding_guard(message)
        message = _enforce_evidence_quality(message, session)

    # ------------------------------------------------------------------
    # 7. Advance FSM state when a session is provided.
    #    The technician's last answer is the final user turn in history.
    # ------------------------------------------------------------------
    if session is not None and not is_first_turn:
        # Find the most recent technician reply from history.
        technician_answer = ""
        for m in reversed(history):
            if m["role"] == "user":
                technician_answer = m["content"]
                break
        updated = diagnosis_fsm.advance_state(
            session,
            llm_response=raw,
            technician_answer=technician_answer,
        )
        # Merge updated FSM fields back into the live session in-place.
        for k, v in updated.items():
            if k not in ("history",):  # history is managed by app.py
                session[k] = v

    # ------------------------------------------------------------------
    # 8. Persist conversation on resolution.
    # ------------------------------------------------------------------
    conv_id = None
    if is_resolved:
        doc_ids = [s["id"] for s in snippets]
        conv_id = db.insert_conversation(question, message, doc_ids)

    resolution = _parse_resolution(message) if is_resolved else None

    return {
        "message": message,
        "is_resolved": is_resolved,
        "resolution": resolution,
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
        ] if is_resolved else [],
        "conversation_id": conv_id,
    }

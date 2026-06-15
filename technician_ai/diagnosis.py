"""
diagnosis_fsm.py -- Finite-state machine for the technician diagnostic session.
"""

import re
from copy import deepcopy

from . import safety as _sg

# ---------------------------------------------------------------------------
# State constants
# ---------------------------------------------------------------------------
STATE_SAFETY_CHECK = "SAFETY_CHECK"
STATE_SYMPTOM_GATHERING = "SYMPTOM_GATHERING"
STATE_STANDARD_COMPARISON = "STANDARD_COMPARISON"
STATE_CAUSE_NARROWING = "CAUSE_NARROWING"
STATE_RESOLVED = "RESOLVED"

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

_OBSTRUCTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bobstruct",
        r"\bblockage\b",
        r"\bblocked\b",
        r"\bblock(ing)?\b",
        r"\bpallet\b",
        r"\bpackaging\b",
        r"\bjam(med|ming)?\b",
        r"\bclear(ed)? the (path|area|way)\b",
        r"\bobject in (the )?(way|path)\b",
        r"\bforeign (object|material|body)\b",
        r"\bdebris\b",
    ]
]

_SPEC_COMPARISON_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b\d+(\.\d+)?\s*(bar|psi|mpa|kpa)\b",
        r"\b\d+(\.\d+)?\s*(mm|cm|m|in|inch|inches)\b",
        r"\b\d+(\.\d+)?\s*(v|volt|volts|vdc|vac)\b",
        r"\b\d+(\.\d+)?\s*(a|amp|amps|ampere|ma)\b",
        r"\b\d+(\.\d+)?\s*(rpm)\b",
        r"\b\d+(\.\d+)?\s*%\b",
        r"\b\d+(\.\d+)?\s*(deg c|deg f|celsius|fahrenheit)\b",
        r"\b\d+(\.\d+)?\s*(nm|newton.?met(er|re))\b",
        r"\bspec(ification)?s?\b",
        r"\bwithin (tolerance|range|limits?)\b",
        r"\boutside (tolerance|range|limits?)\b",
        r"\bnominal (value|range|level)\b",
        r"\bexpected (value|reading|level|range)\b",
        r"\bshould (read|be|measure|show)\b",
        r"\bcompare (to|with) (the )?(spec|manual|data(sheet)?|drawing)\b",
        r"\baccording to (the )?(spec|manual|data(sheet)?|drawing)\b",
        r"\bmanual (says|states|specifies|calls for)\b",
    ]
]

_SAFETY_DOOR_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bsafety door\b",
        r"\bdoor (open|alarm|error|fault|interlock)\b",
        r"\binterlock (alarm|error|fault|open)\b",
        r"\bdoor (sensor|switch|latch)\b",
        r"\bsafety gate\b",
        r"\bguard (door|open|alarm)\b",
        r"\bdoor not closed\b",
        r"\bdoor wont close\b",
        r"\bdoor (will not|cannot) (close|latch|lock)\b",
    ]
]

# ---------------------------------------------------------------------------
# Evidence quality classification
# ---------------------------------------------------------------------------

_UNCERTAINTY_MARKERS: frozenset[str] = frozenset([
    "maybe", "might", "i think", "i'm not sure", "im not sure",
    "not really sure", "hard to tell", "looked like", "probably",
    "someone said", "i didn't check", "i wasn't watching",
    "not 100%", "not certain", "i guess", "i believe", "i suppose",
    "appears to", "seems like", "seems to", "could be", "might be",
    "may be", "not sure", "kind of", "sort of", "roughly",
    "approximately", "around", "about", "i'm guessing", "guessing",
    "don't know", "dont know", "unclear", "not clear",
    "can't tell", "cant tell", "hard to say", "difficult to tell",
    "wasn't watching", "i was not watching", "didn't see", "didn't notice",
    "not totally sure", "not completely sure", "i didn't really",
    "not really sure", "i'm not 100", "im not 100",
])

_HEARSAY_MARKERS: frozenset[str] = frozenset([
    "someone said", "they said", "previous shift", "i was told",
    "i heard from", "someone told me", "another technician",
    "supervisor said", "coworker said", "i was informed",
])

_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "no alarm", "no error", "no fault", "no crack", "no damage",
    "no injury", "no injuries", "not broken", "nothing wrong",
    "no visible", "not visible", "no one hurt", "nobody hurt",
    "no active alarm", "no warning", "not lit", "not on",
    "machine is fine", "looks fine", "seems fine",
)


def _classify_evidence_quality(text: str) -> str:
    """Classify a single technician observation into an evidence quality category.

    Categories (in priority order checked):
        HEARSAY   — reported by others, not directly observed
        NEGATIVE  — a condition explicitly ruled out
        APPROXIMATE — uncertain measurement with hedging language
        SUSPECTED — uncertain visual/sensory with hedging language
        CONFIRMED — direct observation or measurement, no hedging
    """
    lower = text.lower()

    if any(h in lower for h in _HEARSAY_MARKERS):
        return "HEARSAY"

    if any(n in lower for n in _NEGATIVE_KEYWORDS):
        return "NEGATIVE"

    is_uncertain = any(m in lower for m in _UNCERTAINTY_MARKERS)
    if is_uncertain:
        has_measurement = _matches_any(_SPEC_COMPARISON_PATTERNS, text)
        return "APPROXIMATE" if has_measurement else "SUSPECTED"

    return "CONFIRMED"


def high_confidence_warranted(session: dict) -> bool:
    """Return True when evidence quality supports a HIGH-confidence resolution.

    Requires at least one CONFIRMED observation in the evidence log.
    APPROXIMATE, SUSPECTED, and HEARSAY observations alone do not warrant
    HIGH confidence.
    """
    return bool(session.get("has_confirmed_evidence", False))


_SAFETY_CONFIRMED_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\byes\b",
        r"\bconfirmed?\b",
        r"\bcleared?\b",
        r"\be.?stop\b",
        r"\bde.?energized?\b",
        r"\bloto\b",
        r"\block(ed)?.?out\b",
        r"\btag(ged)?.?out\b",
        r"\bsafe to proceed\b",
        r"\barea is (safe|clear|secured?)\b",
        r"\bsafety (check|procedure|protocol) (complete|done|finished|passed)\b",
        r"\bpower (is |has been )?(off|removed|disconnected|isolated)\b",
        r"\bmachine (is |has been )?(safe|locked|de.?energized|isolated)\b",
        r"\bguards? (are |is )?(in place|installed|secured?)\b",
    ]
]

_OBSERVABLE_QUESTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bdo you (see|notice|observe|hear|feel|smell)\b",
        r"\bcan you (see|notice|observe|hear|feel|check|measure|inspect|verify)\b",
        r"\bwhat (does|is|are) (the |it |they )?(reading|showing|indicating|displaying|measuring)\b",
        r"\bwhat (color|colour|sound|noise|smell|vibration|movement)\b",
        r"\bis (there|the|it|this) .{0,40}\?",
        r"\bare (there|the|they) .{0,40}\?",
        r"\bhave you (checked|verified|inspected|tested|tried|looked at)\b",
        r"\bplease (check|verify|inspect|measure|observe|look at)\b",
        r"\bwhat (error|fault|alarm|code|message|light) .{0,30}\?",
    ]
]

# ---------------------------------------------------------------------------
# Helper: detect patterns in text
# ---------------------------------------------------------------------------

def _matches_any(patterns, text):
    """Return True if any compiled pattern matches text."""
    for pat in patterns:
        if pat.search(text):
            return True
    return False


# ---------------------------------------------------------------------------
# Public: detect_safety_door
# ---------------------------------------------------------------------------

def detect_safety_door(text):
    """Return True if text mentions a safety door / interlock scenario."""
    return _matches_any(_SAFETY_DOOR_PATTERNS, text)


# ---------------------------------------------------------------------------
# Internal: state transition logic
# ---------------------------------------------------------------------------

def _all_prerequisites_met(session: dict) -> bool:
    """True when every hazard-specific prerequisite is confirmed."""
    hazard = session.get("hazard_type")
    prerequisites = session.get("prerequisites", {})
    if not hazard or not prerequisites:
        # Non-safety-critical or no prerequisites defined — use legacy flag.
        return session.get("safety_confirmed", False)
    return _sg.all_prerequisites_met(hazard, prerequisites)


def _next_state(session):
    """Determine the next FSM state based on current flags."""
    current = session["state"]

    if current == STATE_SAFETY_CHECK:
        if _all_prerequisites_met(session):
            return STATE_SYMPTOM_GATHERING
        return STATE_SAFETY_CHECK

    if current == STATE_SYMPTOM_GATHERING:
        if session["symptoms_gathered"] >= 2:
            return STATE_STANDARD_COMPARISON
        return STATE_SYMPTOM_GATHERING

    if current == STATE_STANDARD_COMPARISON:
        if session["has_spec_comparison"]:
            return STATE_CAUSE_NARROWING
        return STATE_STANDARD_COMPARISON

    if current == STATE_CAUSE_NARROWING:
        return STATE_CAUSE_NARROWING

    return current


# ---------------------------------------------------------------------------
# Public: new_session
# ---------------------------------------------------------------------------

def new_session(question, is_safety_critical=False, hazard_type=None):
    """Create and return a fresh diagnostic session dict."""
    prerequisites = (
        _sg.init_prerequisites(hazard_type) if hazard_type else {}
    )
    return {
        "state": STATE_SAFETY_CHECK if is_safety_critical else STATE_SYMPTOM_GATHERING,
        "question": question,
        "is_safety_critical": is_safety_critical,
        "hazard_type": hazard_type,
        "prerequisites": prerequisites,
        "safety_confirmed": False,
        "has_safety_door": detect_safety_door(question),
        "obstruction_checked": False,
        "has_spec_comparison": False,
        "symptoms_gathered": 0,
        "questions_asked": 0,
        "history": [],
        # Evidence quality tracking
        "evidence_log": [],          # list of quality strings per technician turn
        "has_confirmed_evidence": False,
    }


# ---------------------------------------------------------------------------
# Public: advance_state
# ---------------------------------------------------------------------------

def advance_state(session, llm_response, technician_answer):
    """
    Advance the session by one turn.

    Parameters
    ----------
    session          : dict -- existing session (will NOT be mutated).
    llm_response     : str  -- latest assistant message.
    technician_answer: str  -- technician reply to that message.

    Returns
    -------
    New session dict with updated state and history.
    """
    s = deepcopy(session)

    is_resolution = llm_response.startswith("RESOLVED:")

    # 1. Append assistant turn; count questions only for non-resolution turns.
    s["history"].append({"role": "assistant", "content": llm_response})
    if not is_resolution:
        s["questions_asked"] += 1

    # 2. Append technician turn (skip when terminal).
    if not is_resolution:
        s["history"].append({"role": "user", "content": technician_answer})

    # 3. Run flag detectors.
    combined_text = llm_response + " " + (technician_answer if not is_resolution else "")

    if not s["obstruction_checked"]:
        s["obstruction_checked"] = _matches_any(_OBSTRUCTION_PATTERNS, combined_text)

    if not s["has_spec_comparison"]:
        s["has_spec_comparison"] = _matches_any(_SPEC_COMPARISON_PATTERNS, combined_text)

    if not s["has_safety_door"]:
        s["has_safety_door"] = _matches_any(_SAFETY_DOOR_PATTERNS, combined_text)

    if s["state"] == STATE_SAFETY_CHECK and not s["safety_confirmed"]:
        if not is_resolution:
            if s.get("hazard_type") and s.get("prerequisites") is not None:
                # For hazard-specific sessions, rag.py updates prerequisites
                # before advance_state is called; sync the boolean flag here.
                s["safety_confirmed"] = _all_prerequisites_met(s)
            else:
                # Legacy path: no hazard-specific prerequisites defined.
                s["safety_confirmed"] = _matches_any(
                    _SAFETY_CONFIRMED_PATTERNS, technician_answer
                )

    # 4a. Classify and log evidence quality for this technician turn.
    if not is_resolution and technician_answer.strip():
        quality = _classify_evidence_quality(technician_answer)
        s.setdefault("evidence_log", []).append(quality)
        if quality == "CONFIRMED":
            s["has_confirmed_evidence"] = True

    # 4. Count symptoms gathered from observable questions.
    if _matches_any(_OBSERVABLE_QUESTION_PATTERNS, llm_response):
        s["symptoms_gathered"] += 1

    # 5. Transition state.
    if is_resolution:
        s["state"] = STATE_RESOLVED
    else:
        s["state"] = _next_state(s)

    return s


# ---------------------------------------------------------------------------
# Public: check_resolution_allowed
# ---------------------------------------------------------------------------

def check_resolution_allowed(session):
    """
    Check whether the FSM permits a resolution at this point.

    Returns
    -------
    (True, "")  if resolution is permitted.
    (False, instruction_string) if blocked.
    """
    # Gate 1: already resolved -- allow immediately.
    if session["state"] == STATE_RESOLVED:
        return (True, "")

    # Gate 2: safety check not yet confirmed.
    if session["state"] == STATE_SAFETY_CHECK and not session["safety_confirmed"]:
        return (
            False,
            "[FSM OVERRIDE] Safety has not been confirmed. You must ask the technician "
            "to verify that the machine is safe before proceeding with any diagnosis."
        )

    # Gate 3: safety-critical with confirmation waives minimum-question rule.
    if session["is_safety_critical"] and session["safety_confirmed"]:
        return (True, "")

    # Gate 4: no minimum question count — resolve only when evidence warrants it.

    # Gate 5: door detected but obstruction not yet checked.
    if session["has_safety_door"] and not session["obstruction_checked"]:
        return (
            False,
            "[FSM OVERRIDE] A safety door issue is present. You must ask whether any "
            "obstruction or foreign object is blocking the door before concluding."
        )

    # Gate 6: evidence quality — all observations uncertain (non-safety sessions).
    # Do not resolve if every substantive observation is APPROXIMATE/SUSPECTED/HEARSAY.
    if not session.get("is_safety_critical") or session.get("safety_confirmed"):
        evidence_log = session.get("evidence_log", [])
        substantive = [e for e in evidence_log if e != "NEGATIVE"]
        if substantive and not session.get("has_confirmed_evidence", False):
            return (
                False,
                "[FSM EVIDENCE GATE] All observations so far are approximate, suspected, "
                "or unverified (no CONFIRMED measurement or directly observed fact). "
                "Ask one more targeted question that can yield a confirmed reading or "
                "clearly observable fact — such as asking the technician to read the "
                "vacuum gauge during a live failed pickup, or to inspect a specific cup "
                "closely and report exactly what they see. Do not resolve with HIGH "
                "confidence on uncertain evidence alone.",
            )

    return (True, "")


# ---------------------------------------------------------------------------
# Public: get_state_prompt_addition
# ---------------------------------------------------------------------------

def get_state_prompt_addition(session):
    """
    Return a string of [FSM OVERRIDE] / [FSM NOTE] blocks to prepend to the
    system prompt for the current turn, or "" if nothing needs to be added.
    """
    blocks = []
    state = session["state"]

    # Safety check -- not yet confirmed.
    if state == STATE_SAFETY_CHECK and not session["safety_confirmed"]:
        blocks.append(
            "[FSM OVERRIDE] The machine has not been confirmed safe. "
            "Do NOT ask diagnostic questions about components or causes yet. "
            "First ask the technician to confirm that the machine is powered down, "
            "locked out/tagged out, and safe to work on."
        )

    # Safety check -- confirmed.
    elif state == STATE_SAFETY_CHECK and session["safety_confirmed"]:
        blocks.append(
            "[FSM NOTE] Safety has been confirmed. You may now proceed with diagnostic questions."
        )

    # Door detected but obstruction not yet checked (any non-terminal state).
    if (
        session["has_safety_door"]
        and not session["obstruction_checked"]
        and state != STATE_RESOLVED
    ):
        blocks.append(
            "[FSM OVERRIDE] A safety door issue has been identified. Before naming specific "
            "components as the root cause, ask the technician to check whether any obstruction, "
            "foreign object, pallet, or packaging is blocking the door."
        )

    # Cause narrowing without sufficient evidence.
    if state == STATE_CAUSE_NARROWING and session["questions_asked"] < 3:
        blocks.append(
            "[FSM NOTE] You are in the CAUSE_NARROWING phase but have not yet gathered "
            "enough evidence. Do not provide a resolution until you have asked at least "
            "3 diagnostic questions."
        )

    # Evidence quality summary — injected every non-trivial turn.
    evidence_log = session.get("evidence_log", [])
    if evidence_log:
        confirmed = evidence_log.count("CONFIRMED")
        approximate = evidence_log.count("APPROXIMATE")
        suspected = evidence_log.count("SUSPECTED")
        hearsay = evidence_log.count("HEARSAY")
        parts = []
        if confirmed:
            parts.append(f"{confirmed} CONFIRMED")
        if approximate:
            parts.append(f"{approximate} APPROXIMATE")
        if suspected:
            parts.append(f"{suspected} SUSPECTED")
        if hearsay:
            parts.append(f"{hearsay} HEARSAY")
        quality_line = ", ".join(parts) if parts else "none yet"
        if session.get("has_confirmed_evidence"):
            verdict = "HIGH confidence is warranted if evidence directly explains symptom."
        else:
            verdict = (
                "No CONFIRMED observation yet — HIGH confidence is NOT warranted. "
                "Use MEDIUM or LOW confidence if resolving, or ask one targeted "
                "confirmation question."
            )
        blocks.append(
            f"[FSM EVIDENCE SUMMARY] Observation quality so far: {quality_line}. {verdict}"
        )

    # Append blocked-resolution reason if applicable.
    allowed, reason = check_resolution_allowed(session)
    if not allowed and reason and reason not in " ".join(blocks):
        blocks.append(reason)

    return "\n\n".join(blocks)

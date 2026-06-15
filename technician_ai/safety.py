"""
safety_gate.py

Classifies incoming technician questions for safety-critical hazards and
renders structured safety responses before the RAG pipeline runs.

Public API (consumed by rag.py and app.py):
    classify_safety_critical(text) -> str | None
    build_safety_response(hazard_type) -> str
    is_safety_confirmed(user_response) -> bool
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Hazard trigger phrases
# ---------------------------------------------------------------------------

SAFETY_TRIGGERS: dict[str, list[str]] = {
    "broken_glass": [
        "broken glass",
        "glass broke",
        "glass break",
        "glass shatter",
        "shattered glass",
        "cracked glass",
        "glass crack",
        "glass fragment",
        "glass shard",
        "glass chip",
        "broken pane",
        "glass on floor",
        "glass on the floor",
        "glass pieces",
        "glass broke in",
        "glass has broken",
        "panel broke",
        "panel shattered",
        "pane broke",
        "pane shattered",
    ],
    "electrical_hazard": [
        "electrical hazard",
        "electric shock",
        "electrocution",
        "live wire",
        "exposed wire",
        "sparking",
        "spark from",
        "arc flash",
        "arc fault",
        "short circuit",
        "tripped breaker",
        "breaker tripped",
        "tripped fuse",
        "burning smell from",
        "smoke from panel",
        "voltage present",
        "high voltage",
        "loto",
        "lockout tagout",
        "lock out tag out",
        "de-energize",
        "de-energized",
        "deenergize",
        "needs to be de-energized",
    ],
    "chemical_hazard": [
        "chemical spill",
        "chemical leak",
        "spilled chemical",
        "leaked chemical",
        "eva spill",
        "resin spill",
        "solvent spill",
        "acid spill",
        "hazardous material",
        "hazmat",
        "chemical fume",
        "fume exposure",
        "inhaled chemical",
        "chemical burn",
        "skin contact with chemical",
        "chemical contact",
        "material safety",
        "msds",
        "sds sheet",
        "toxic vapor",
    ],
    "pneumatic_hazard": [
        "moved suddenly",
        "machine moved",
        "moved unexpectedly",
        "unexpected movement",
        "unexpected motion",
        "pneumatic movement",
        "actuator moved",
        "actuator fired",
        "actuator extended",
        "cylinder moved",
        "cylinder fired",
        "cylinder extended",
        "pneumatic actuator",
        "air on",
        "almost caught",
        "almost got caught",
        "almost pinched",
        "hand almost",
        "nearly caught",
        "nearly pinched",
        "unexpected pneumatic",
        "machine jumped",
        "machine lurched",
        "arm moved suddenly",
        "robot moved suddenly",
    ],
    "crush_pinch_hazard": [
        "crush hazard",
        "crushing hazard",
        "pinch point",
        "pinch hazard",
        "hand caught",
        "finger caught",
        "hand pinched",
        "finger pinched",
        "caught in machine",
        "caught in the machine",
        "entrapment",
        "trapped in",
        "body part caught",
        "arm caught",
        "nip point",
        "roller pinch",
        "press hazard",
        "laminator pinch",
        "conveyor pinch",
    ],
    "fire_hazard": [
        "fire",
        "smoke",
        "burning",
        "burn smell",
        "smell of smoke",
        "smells like smoke",
        "on fire",
        "catching fire",
        "flame",
        "flammable",
        "ignition",
        "overheating",
        "overheat",
        "thermal runaway",
        "fire extinguisher",
        "evacuation",
        "fire alarm",
        "fire suppression",
    ],
    "fall_hazard": [
        "fall hazard",
        "falling hazard",
        "risk of falling",
        "fall from height",
        "working at height",
        "ladder safety",
        "unstable ladder",
        "scaffold",
        "scaffolding",
        "elevated work",
        "harness",
        "fall arrest",
        "slip hazard",
        "slipping hazard",
        "wet floor",
        "slippery floor",
        "trip hazard",
        "tripping hazard",
    ],
}

# ---------------------------------------------------------------------------
# Hazard-specific prerequisite checklists
#
# Each prerequisite must be individually confirmed before leaving SAFETY_HOLD.
# confirmation_patterns: positive evidence phrases (case-insensitive substring).
# instruction_if_missing: what to tell the technician when this is still unmet.
# ---------------------------------------------------------------------------

SAFETY_PREREQUISITES: dict[str, list[dict]] = {
    "pneumatic_hazard": [
        {
            "id": "no_injury",
            "description": "No one is injured, or any injury has been addressed",
            "confirmation_patterns": [
                "no one hurt", "nobody hurt", "not hurt", "no injury", "no injuries",
                "everyone ok", "everyone okay", "i'm ok", "im ok", "no one is hurt",
                "nobody is hurt", "not injured", "fine", "no one injured",
                "nobody injured", "all ok", "everyone is fine", "no one was hurt",
                "no one got hurt",
            ],
            "instruction_if_missing": (
                "Confirm: is anyone injured or in need of medical attention? "
                "If so, call for help immediately before anything else."
            ),
        },
        {
            "id": "estop_engaged",
            "description": "Emergency Stop or safe stop has been engaged",
            "confirmation_patterns": [
                "e-stop", "estop", "e stop", "emergency stop", "hit the stop",
                "pressed stop", "stop button", "stopped the machine", "machine stopped",
                "engaged e-stop", "pressed e-stop", "hit e-stop",
                "emergency stop pressed", "stop pressed", "machine is stopped",
                "stopped it",
            ],
            "instruction_if_missing": (
                "Press the Emergency Stop immediately to prevent further unexpected movement."
            ),
        },
        {
            "id": "personnel_clear",
            "description": "All personnel are clear of moving mechanisms",
            "confirmation_patterns": [
                "everyone clear", "all clear", "stepped back", "moved back",
                "away from", "no one near", "people are clear", "cleared",
                "backed away", "standing back", "everyone stepped back",
                "no one is near", "no one close", "area is clear",
                "personnel are clear", "everyone is clear",
            ],
            "instruction_if_missing": (
                "Ensure all personnel are clear of the machine and any moving mechanisms "
                "before proceeding."
            ),
        },
        {
            "id": "air_isolated",
            "description": "Main air source has been shut off and locked out",
            "confirmation_patterns": [
                "air off", "air shut off", "air isolated", "air supply off",
                "turned off the air", "isolated the air", "locked out", "loto",
                "shut off air", "air is off", "cut the air", "air source off",
                "pneumatic off", "air locked", "air has been shut", "air shutoff",
                "air supply isolated", "air supply shut", "main air off",
                "compressed air off", "air is isolated", "air has been isolated",
                "air now isolated", "air supply is off", "air has been turned off",
            ],
            "instruction_if_missing": (
                "Leave the E-stop engaged. Shut off and lock the main air source before "
                "any further inspection. Stay clear of all mechanisms until pneumatic "
                "pressure has fully released. Confirm once the air supply is isolated."
            ),
        },
    ],
    "crush_pinch_hazard": [
        {
            "id": "no_injury",
            "description": "No one is injured, or any injury has been addressed",
            "confirmation_patterns": [
                "no one hurt", "nobody hurt", "not hurt", "no injury", "no injuries",
                "everyone ok", "everyone okay", "no one is hurt", "not injured",
                "fine", "no one injured", "nobody injured", "no one got hurt",
            ],
            "instruction_if_missing": (
                "Confirm: is anyone injured or in need of immediate medical attention?"
            ),
        },
        {
            "id": "estop_engaged",
            "description": "Emergency Stop or safe stop has been engaged",
            "confirmation_patterns": [
                "e-stop", "estop", "emergency stop", "machine stopped",
                "stop button", "stopped the machine", "hit e-stop",
                "stop pressed", "machine is stopped",
            ],
            "instruction_if_missing": (
                "Press the Emergency Stop to prevent further movement."
            ),
        },
        {
            "id": "personnel_clear",
            "description": "All personnel are clear of moving mechanisms",
            "confirmation_patterns": [
                "clear", "everyone clear", "all clear", "stepped back",
                "no one near", "cleared", "area is clear", "everyone is clear",
            ],
            "instruction_if_missing": (
                "Ensure all personnel are clear of the machine before proceeding."
            ),
        },
    ],
    "broken_glass": [
        {
            "id": "injury_checked",
            "description": "Anyone injured or in need of medical attention has been addressed",
            "confirmation_patterns": [
                "no one hurt", "nobody hurt", "not hurt", "no injury", "no injuries",
                "everyone ok", "everyone okay", "no one is hurt", "not injured",
                "fine", "no one injured", "nobody injured", "no one was hurt",
                "no one got hurt",
            ],
            "instruction_if_missing": (
                "Confirm: is anyone injured? If so, call for medical assistance immediately."
            ),
        },
        {
            "id": "machine_safe",
            "description": "Machine is stopped or confirmed safe before cleanup",
            "confirmation_patterns": [
                "stopped", "machine stopped", "machine is stopped", "e-stop",
                "emergency stop", "shut down", "powered off", "turned off",
                "safe", "stopped the machine", "machine off",
            ],
            "instruction_if_missing": (
                "Stop the machine before approaching for cleanup."
            ),
        },
    ],
    "_default": [
        {
            "id": "general_safety",
            "description": "Area is safe and machine is stopped",
            "confirmation_patterns": [
                "yes", "confirmed", "done", "safe", "stopped", "clear", "ok", "okay",
                "e-stop", "emergency stop", "machine stopped", "loto",
                "all clear", "area is clear",
            ],
            "instruction_if_missing": (
                "Please confirm the machine is stopped and the area is safe "
                "before I continue."
            ),
        },
    ],
}


def get_prerequisites_for_hazard(hazard_type: str) -> list[dict]:
    """Return the prerequisite checklist for a hazard type."""
    return SAFETY_PREREQUISITES.get(hazard_type, SAFETY_PREREQUISITES["_default"])


def init_prerequisites(hazard_type: str) -> dict[str, bool]:
    """Return {prereq_id: False} dict for a hazard type."""
    return {p["id"]: False for p in get_prerequisites_for_hazard(hazard_type)}


def update_prerequisites(
    hazard_type: str, prerequisites: dict[str, bool], user_text: str
) -> None:
    """Update prerequisites in-place from user_text (case-insensitive).

    Only marks a prerequisite True — never reverts a confirmed prerequisite.
    """
    lower = user_text.lower()
    for p in get_prerequisites_for_hazard(hazard_type):
        pid = p["id"]
        if prerequisites.get(pid):
            continue  # already confirmed
        if any(phrase in lower for phrase in p["confirmation_patterns"]):
            prerequisites[pid] = True


def all_prerequisites_met(hazard_type: str, prerequisites: dict[str, bool]) -> bool:
    """Return True if every prerequisite for the hazard type is confirmed."""
    return all(
        prerequisites.get(p["id"], False)
        for p in get_prerequisites_for_hazard(hazard_type)
    )


def get_unmet_prerequisites(
    hazard_type: str, prerequisites: dict[str, bool]
) -> list[dict]:
    """Return the list of prerequisite dicts that are not yet confirmed."""
    return [
        p for p in get_prerequisites_for_hazard(hazard_type)
        if not prerequisites.get(p["id"], False)
    ]


def build_safety_hold_response(
    hazard_type: str, unmet_prerequisites: list[dict]
) -> str:
    """Generate a code-based safety hold response for unmet prerequisites.

    Does NOT call the LLM. Returns ONLY what is needed to complete safety
    isolation. Does NOT ask about operational parameters, readings, root
    causes, or component failures.
    """
    if not unmet_prerequisites:
        return (
            "All safety confirmations received. "
            "Please describe the current state of the machine so I can begin "
            "the diagnostic process."
        )

    lines = [
        "**Safety Hold — the following must be confirmed before diagnosis begins:**",
        "",
    ]
    for i, prereq in enumerate(unmet_prerequisites, start=1):
        lines.append(f"{i}. {prereq['instruction_if_missing']}")
        lines.append("")

    lines.append(
        "Once all items above are confirmed, I will begin the diagnostic process."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Safety actions per hazard type
# ---------------------------------------------------------------------------

SAFETY_ACTIONS: dict[str, dict] = {
    "pneumatic_hazard": {
        "summary": (
            "Unexpected pneumatic movement has been reported. "
            "Do not approach any moving mechanism. Keep the Emergency Stop engaged."
        ),
        "immediate_actions": [
            # Source-grounded: equipment manuals for this class of machine
            # require the main air source switch to be turned off and locked
            # before equipment maintenance or investigation.
            # Do NOT add cleanup PPE, residual-pressure bleed, or actuator-position
            # checks here unless a retrieved source document explicitly supports them.
            {
                "text": (
                    "Keep the Emergency Stop engaged. Do not approach or reach into "
                    "any mechanism while there may be stored pneumatic energy."
                ),
                "source_doc": "First Glass Loading Machine Manual AT.pdf",
                "source_page": None,
                "source_context": "Equipment maintenance — machine safety before inspection",
                "validation_status": "source_grounded",
            },
            {
                "text": (
                    "Ensure all personnel are clear of moving mechanisms "
                    "before any further action."
                ),
                "source_doc": "First Glass Loading Machine Manual AT.pdf",
                "source_page": None,
                "source_context": "Equipment maintenance — personnel safety",
                "validation_status": "source_grounded",
            },
            {
                "text": (
                    "Turn off and lock the main air source switch before any "
                    "inspection or investigation of the machine."
                ),
                "source_doc": "First Glass Loading Machine Manual AT.pdf",
                "source_page": None,
                "source_context": (
                    "Equipment maintenance — main air source switch must be turned "
                    "off and locked before maintenance"
                ),
                "validation_status": "source_grounded",
            },
        ],
        # Pending actions — withheld from technician; for EHS/Equipment review only.
        "_pending_audit_only": [
            {
                "text": "Verify residual pressure has been released before investigation.",
                "validation_status": "pending_EHS_review",
            },
            {
                "text": "Confirm all actuators have returned to their rest positions.",
                "validation_status": "pending_EHS_review",
            },
        ],
        "safety_question": (
            "Is the Emergency Stop engaged, are all personnel clear of moving mechanisms, "
            "and is anyone injured?"
        ),
    },
    "broken_glass": {
        "summary": (
            "Broken glass inside an operating machine presents a serious "
            "laceration hazard. Do not reach into the machine or approach "
            "moving mechanisms."
        ),
        "immediate_actions": [
            # Source-grounded actions: directly supported by the Glass Loading
            # Manual hazard section.  Do NOT add more items here unless a
            # retrieved source document explicitly covers broken-glass cleanup
            # for this machine.
            {
                "text": (
                    "Keep machine doors closed and locked until it is confirmed "
                    "safe to open them."
                ),
                "source_doc": "First Glass Loading Machine Manual AT.pdf",
                "source_page": None,
                "source_context": "Hazard section — broken glass procedure",
                "validation_status": "source_grounded",
            },
            {
                "text": (
                    "Wear proper PPE before cleaning up broken glass. "
                    "Consult your site PPE requirements or the applicable "
                    "procedure for the specific items required."
                ),
                "source_doc": "First Glass Loading Machine Manual AT.pdf",
                "source_page": None,
                "source_context": "Hazard section — broken glass procedure",
                "validation_status": "source_grounded",
            },
            {
                "text": (
                    "If there is any immediate risk to personnel, press the "
                    "Emergency Stop as soon as it is safe to do so, and "
                    "immediately report the incident to the supervisor on duty "
                    "and to EHS."
                ),
                "source_doc": "First Glass Loading Machine Manual AT.pdf",
                "source_page": None,
                "source_context": "Hazard section — broken glass procedure",
                "validation_status": "source_grounded",
            },
        ],
        # Pending actions are NOT displayed to the technician as instructions.
        # They are retained here for internal audit/EHS review only.
        "_pending_audit_only": [
            {
                "text": "Use a broom and dustpan — never bare hands — to collect glass fragments.",
                "validation_status": "pending_EHS_review",
            },
            {
                "text": "Dispose of shards in a puncture-resistant container labeled 'Broken Glass'.",
                "validation_status": "pending_EHS_review",
            },
            {
                "text": "Inspect surrounding surfaces for additional fragments before restarting.",
                "validation_status": "pending_EHS_review",
            },
        ],
        "safety_question": (
            "Is everyone clear of the machine, and has the machine been safely "
            "stopped or isolated? Is anyone injured?"
        ),
    },
    "electrical_hazard": {
        "summary": (
            "An electrical hazard has been identified. Do not touch any "
            "energized components. Follow LOTO procedures before any "
            "inspection or repair."
        ),
        "immediate_actions": [
            {
                "text": (
                    "Immediately de-energize the affected equipment using the "
                    "site Lockout/Tagout (LOTO) procedure. Do not attempt any "
                    "work on energized equipment."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "If someone has received an electric shock, do not touch "
                    "them directly. Call emergency services (911) and notify "
                    "your supervisor immediately."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Wear appropriate PPE (insulated gloves, safety glasses) "
                    "when working near any electrical components, even after "
                    "LOTO is applied."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Do not reset a tripped breaker or fuse without first "
                    "identifying and correcting the root cause. Contact a "
                    "qualified electrician."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
        ],
        "safety_question": (
            "Has the equipment been fully de-energized and locked out/tagged "
            "out per the site LOTO procedure before you proceed?"
        ),
    },
    "chemical_hazard": {
        "summary": (
            "A chemical spill, leak, or exposure has been identified. "
            "Evacuate the immediate area and consult the Safety Data Sheet "
            "(SDS) before taking further action."
        ),
        "immediate_actions": [
            {
                "text": (
                    "Evacuate all non-essential personnel from the affected "
                    "area immediately and prevent re-entry until the hazard "
                    "is controlled."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Locate and review the Safety Data Sheet (SDS) for the "
                    "involved chemical before attempting cleanup. SDS binders "
                    "are located at each workstation and in the EHS office."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Wear chemical-resistant gloves, safety glasses or face "
                    "shield, and appropriate respiratory protection as "
                    "specified by the SDS before approaching the spill."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Notify your supervisor and EHS immediately. If the spill "
                    "is large or involves a highly toxic material, activate "
                    "the site emergency response plan."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
        ],
        "safety_question": (
            "Have you evacuated the area, located the SDS for this chemical, "
            "and notified your supervisor or EHS?"
        ),
    },
    "crush_pinch_hazard": {
        "summary": (
            "A crush or pinch-point hazard has been identified. Stop the "
            "machine immediately. Do not reach into moving machinery."
        ),
        "immediate_actions": [
            {
                "text": (
                    "Press the emergency stop (E-stop) immediately and apply "
                    "LOTO before accessing any pinch-point or nip-point area."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "If a body part is trapped, do not attempt to pull it free "
                    "forcefully. Call emergency services (911) and notify your "
                    "supervisor. Wait for qualified personnel."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Ensure all machine guards and safety interlocks are in "
                    "place and functioning before restarting equipment."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Do not bypass or disable safety guards or interlocks for "
                    "any reason. Report damaged or missing guards to your "
                    "supervisor before operating the machine."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
        ],
        "safety_question": (
            "Has the machine been brought to a complete stop and locked out/"
            "tagged out before anyone approaches the hazard area?"
        ),
    },
    "fire_hazard": {
        "summary": (
            "A fire or smoke hazard has been identified. Activate the fire "
            "alarm and evacuate immediately if the fire is not immediately "
            "controllable."
        ),
        "immediate_actions": [
            {
                "text": (
                    "If you see flames or heavy smoke, activate the nearest "
                    "fire alarm pull station and evacuate the building "
                    "immediately. Call 911."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Only attempt to use a fire extinguisher on a small, "
                    "contained fire if you have been trained to do so and have "
                    "a clear escape route. Use the PASS technique "
                    "(Pull, Aim, Squeeze, Sweep)."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Shut off electrical power to the affected equipment if "
                    "it is safe to do so and can be done without entering the "
                    "hazard area."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Do not re-enter the building until cleared by the fire "
                    "department or site emergency response team."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
        ],
        "safety_question": (
            "Has the fire alarm been activated, have all personnel evacuated "
            "to the designated muster point, and has 911 been called?"
        ),
    },
    "fall_hazard": {
        "summary": (
            "A fall hazard has been identified. Do not proceed with elevated "
            "work without proper fall protection in place."
        ),
        "immediate_actions": [
            {
                "text": (
                    "Stop work at height immediately if proper fall protection "
                    "(harness, guardrails, or safety netting) is not in place."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Inspect ladders and scaffolding before use. Do not use "
                    "damaged equipment. Ensure ladders are on stable, level "
                    "surfaces and secured at the top or held by a spotter."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Clean up any spills or wet surfaces that create slip "
                    "hazards. Place wet-floor signs and restrict access until "
                    "the area is dry."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
            {
                "text": (
                    "Notify your supervisor before performing any work at "
                    "height above 4 feet. A fall-protection plan may be "
                    "required per site policy."
                ),
                "source_doc": None,
                "source_page": None,
                "validation_status": "pending_EHS_review",
            },
        ],
        "safety_question": (
            "Is proper fall protection (harness, guardrails, or equivalent) "
            "in place and inspected before you proceed with elevated work?"
        ),
    },
}

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_safety_critical(text: str) -> str | None:
    """Return the first matching hazard type for *text*, or None.

    Matching is a case-insensitive substring search against SAFETY_TRIGGERS.
    Hazards are checked in insertion order (broken_glass first).
    """
    lower = text.lower()
    for hazard_type, phrases in SAFETY_TRIGGERS.items():
        for phrase in phrases:
            if phrase in lower:
                return hazard_type
    return None


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------

_PENDING_LABEL = "[Pending EHS/site validation — not yet a documented site procedure]"


def build_safety_response(hazard_type: str) -> str:
    """Render a markdown safety response for the given hazard type.

    Only source_grounded actions are shown as numbered instructions.
    Pending actions are withheld from the technician-facing response entirely.
    If documented steps are incomplete, an escalation instruction is appended.
    """
    action_data = SAFETY_ACTIONS.get(hazard_type)
    if action_data is None:
        return (
            f"**Safety Alert:** A potential hazard ({hazard_type}) was detected. "
            "Stop work immediately and contact your supervisor or EHS before proceeding."
        )

    lines: list[str] = []

    hazard_label = hazard_type.replace("_", " ").title()
    lines.append(f"## Safety Alert: {hazard_label}")
    lines.append("")
    lines.append(action_data["summary"])
    lines.append("")

    # Only show source_grounded actions as numbered steps
    grounded = [a for a in action_data["immediate_actions"]
                if a["validation_status"] == "source_grounded"]
    has_pending = (
        any(a["validation_status"] != "source_grounded"
            for a in action_data["immediate_actions"])
        or bool(action_data.get("_pending_audit_only"))
    )

    if grounded:
        lines.append("### Documented Immediate Actions")
        lines.append("")
        for i, action in enumerate(grounded, start=1):
            doc = action.get("source_doc", "")
            context = action.get("source_context", "")
            citation = f"{doc}" + (f" — {context}" if context else "")
            lines.append(f"{i}. {action['text']}")
            if citation.strip():
                lines.append(f"   _Source: {citation}_")
            lines.append("")
    else:
        lines.append(
            "_No site-specific documented procedure was found for this hazard type._"
        )
        lines.append("")

    # If there are pending actions (or documented steps are incomplete),
    # instruct escalation — do NOT list the pending steps as instructions.
    if has_pending or not grounded:
        lines.append(
            "> **For additional steps:** Follow your site-approved procedure "
            "for this hazard, or stop work and contact your supervisor or EHS "
            "before proceeding further."
        )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"**Before I continue:** {action_data['safety_question']}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Confirmation check
# ---------------------------------------------------------------------------

_SAFETY_CONFIRMED_KEYWORDS: frozenset[str] = frozenset(
    [
        "yes",
        "yeah",
        "yep",
        "yup",
        "confirmed",
        "confirm",
        "done",
        "complete",
        "completed",
        "finished",
        "stopped",
        "stopped the machine",
        "machine stopped",
        "e-stop",
        "estop",
        "emergency stop",
        "locked out",
        "locked-out",
        "tagged out",
        "tagged-out",
        "loto",
        "loto applied",
        "safe",
        "cleared",
        "clear",
        "de-energized",
        "deenergized",
        "area is clear",
        "all clear",
    ]
)


def is_safety_confirmed(user_response: str) -> bool:
    """Return True only if *user_response* contains a clear safety confirmation.

    Deliberately conservative: returns False for ambiguous or empty responses.
    """
    if not user_response or not user_response.strip():
        return False
    lower = user_response.lower()
    for keyword in _SAFETY_CONFIRMED_KEYWORDS:
        if keyword in lower:
            return True
    return False

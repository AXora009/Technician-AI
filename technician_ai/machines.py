"""The plant's machines, how technicians refer to them, and which manuals cover them.

Names and Chinese terms come from the plant's fault repair records.

Equipment codes look like W2-703-All-in-One Soldering Machine-B: workshop W2,
line 7, unit 03, side B. Most machine types share unit numbers, so "703" alone
does not identify a machine. A side letter does: on units 02-06 only the
All-in-One Soldering Machine has sides. Unit 01 also has glass loaders with
sides, so "501B" stays unknown and the agent asks.
"""
from __future__ import annotations

import re

SOLDERING = "All-in-One Soldering Machine"

# name: (terms technicians use, words found in the titles of its manuals)
_MACHINES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    SOLDERING: (
        ("all in one", "aio", "soldering machine", "solder machine", "ribbon holder", "串焊机", "串焊", "划焊一体机"),
        ("all in one", "soldering machine pm", "solder ribbon", "soldering el", "mac soldering"),
    ),
    "Busbar Soldering Machine": (("busbar soldering", "busbar solder", "叠焊机", "叠焊"), ("busbar soldering",)),
    "Busbar Leads Flattening Machine": (
        ("busbar flatten", "busbar flattener", "leads flattening", "压引线机"),
        ("flatten",),
    ),
    "Busbar Leads Lifting Machine": (
        ("tab lifting", "busbar lifting", "leads lifting", "铲引线机", "汇流带理料机"),
        ("tab lifting",),
    ),
    "1st Glass Loading Machine": (("1st glass", "first glass", "一道玻璃机"), ("glass loading",)),
    "2nd Glass Loading Machine": (("2nd glass", "second glass", "二道玻璃机", "合玻机"), ("glass loading",)),
    "1st EVA Layout Machine": (("1st eva", "first eva", "eva 1"), ("first eva", "tpteva")),
    "2nd EVA Layout Machine": (("2nd eva", "second eva", "eva 2"), ("tpteva",)),
    "String Positioning Tape Machine": (("string tape", "贴胶带机"), ("string tape",)),
    "Layup Machine": (("layup", "lay up", "排版机"), ("layup",)),
    "Pre-Lam EL Tester": (("pre lam el", "prelam el", "前el"), ("pre lam el", "pre lam tester")),
    "Post-Lam EL Tester": (("post lam el", "postlam el", "后el"), ("post lam el", "el tester")),
    "Laminator": (("laminator", "层压机"), ("laminator", "lamination")),
    "Labeling Machine": (("labeling machine", "label machine", "labeler", "nameplate", "铭牌机", "铭牌"), ("label",)),
    "Labeling&EPE Placing Machine": (("epe", "贴条码", "小料机"), ("label and epe", "barcode epe")),
    "Edge Taping Machine": (("edge tape", "edge taping", "封边机"), ("edge tape", "封边机")),
    "Edge Trimming Machine": (("edge trimming", "削边机", "切边机", "边缘打磨机"), ("edge trimming",)),
    "Tape Removal Machine": (("tape removal", "撕胶带机"), ("tape removal",)),
    "Corner Wrapping Machine": (("corner wrapping", "护角机", "包角机", "包边机", "封边胶带机"), ("corner wrapping",)),
    "Corner Filing Machine": (("corner filing", "corner sanding", "搓角机"), ()),
    "Framing Machine": (("framing machine", "装框机"), ()),
    "Frame Gluing Machine": (("frame gluing", "边框打胶机"), ("frame sealant",)),
    "Junction Box Installation Machine": (
        ("junction box install", "j box install", "接线盒安装机"),
        ("j box install", "junction box install"),
    ),
    "Junction Box Cap Installation Machine": (("junction box cap", "j box cap", "盒盖机"), ()),
    "Junction Box Soldering Machine": (
        ("junction box solder", "j box solder", "接线盒焊接机"),
        ("j box soldering", "junction box soldering"),
    ),
    "Junction Box Gluing Machine": (("junction box glu", "j box glu", "接线盒打胶机"), ("junction box gluing",)),
    "Junction Box Potting Machine": (("potting machine", "potting"), ("potting",)),
    "IV Tester": (("iv tester", "iv test", "iv测试", "iv 测试仪"), ("iv jig",)),
    "HiPot Tester": (("hipot", "hi pot", "绝缘耐压"), ()),
    "Jig Installation Machine": (("jig installation", "上工装机械手"), ()),
    "Jig Removal Machine": (("jig removal", "下工装机械手"), ()),
    "Final Visual Inspection Machine": (("final visual", "终检ai"), ()),
    "Palletizing Machine": (("palletizing", "分档机"), ()),
    "Conveyor": (("belt conveyor", "conveyor", "流水线"), ("belt conveyor",)),
    "AGV": (("agv",), ()),
}

_ALIASES = sorted(
    (
        (alias, name)
        for name, (aliases, _) in _MACHINES.items()
        for alias in (name.lower().replace("-", " "), *aliases)
    ),
    key=lambda item: len(item[0]),
    reverse=True,
)
_SIDED_CODE = re.compile(r"(?<![a-z0-9])(?:w[12]-?)?[1-8]0[2-6]-?[ab](?![a-z0-9])", re.IGNORECASE)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", text.lower())).strip()


def names() -> list[str]:
    return list(_MACHINES)


def detect(text: str) -> str | None:
    """Return the machine named in the text, or None when it isn't clear.

    Longest term wins, so "busbar soldering" is not read as "soldering machine".
    """
    normalized = _normalize(text)
    for alias, name in _ALIASES:
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}", normalized):
            return name
    return SOLDERING if _SIDED_CODE.search(text) else None


def manual_terms(name: str | None) -> tuple[str, ...]:
    """Lowercase words found in the titles of this machine's manuals."""
    return _MACHINES[name][1] if name in _MACHINES else ()


def title_matches(title: str, terms: tuple[str, ...]) -> bool:
    normalized = _normalize(title)
    return any(term in normalized for term in terms)

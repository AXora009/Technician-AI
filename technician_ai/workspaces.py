"""Per-tester workspaces: each access code maps to its own DB file and manuals folder.

The registry lives in data/workspaces.json:
    {"<access code>": {"name": "...", "db": "data/workspaces/x/tech.db", "manuals": "data/workspaces/x/manuals"}}

The API middleware sets the current workspace for each request; database.connect()
and the manual file endpoints read it from here.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from contextvars import ContextVar
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = Path(os.environ.get("TECHNICIAN_AI_WORKSPACES", PROJECT_ROOT / "data" / "workspaces.json"))

_current: ContextVar[dict | None] = ContextVar("workspace", default=None)


def _load() -> dict[str, dict]:
    if not REGISTRY_PATH.exists():
        return {}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def lookup(code: str | None) -> dict | None:
    if not code:
        return None
    for known, ws in _load().items():
        if secrets.compare_digest(known, code):
            return ws
    return None


def create(name: str, use_existing_data: bool = False) -> tuple[str, dict]:
    """Register a new workspace and return (access code, workspace)."""
    registry = _load()
    if use_existing_data:
        ws = {"name": name, "db": "data/tech.db", "manuals": "manuals"}
    else:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "ws"
        folder = f"data/workspaces/{slug}-{secrets.token_hex(3)}"
        ws = {"name": name, "db": f"{folder}/tech.db", "manuals": f"{folder}/manuals"}
    code = secrets.token_urlsafe(9)
    registry[code] = ws
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return code, ws


def list_all() -> dict[str, dict]:
    return _load()


def set_current(ws: dict | None):
    return _current.set(ws)


def reset_current(token) -> None:
    _current.reset(token)


def current() -> dict | None:
    return _current.get()


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else PROJECT_ROOT / path


def current_db_path() -> Path | None:
    ws = current()
    return _resolve(ws["db"]) if ws else None


def manuals_dir() -> Path:
    ws = current()
    return _resolve(ws["manuals"]) if ws else PROJECT_ROOT / "manuals"

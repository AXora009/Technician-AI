from __future__ import annotations

import json
import os
import re
import sqlite3
import struct
from pathlib import Path

import numpy as np

EMBED_DIM = int(os.environ.get("EMBED_DIM", "512"))
DB_PATH = os.environ.get("TECHNICIAN_AI_DB", "./data/tech.db")


def _pack(vec: list[float] | None) -> bytes | None:
    if vec is None:
        return None
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                embedding BLOB,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                retrieved_doc_ids_json TEXT NOT NULL DEFAULT '[]',
                status TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS diagnose_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                machine TEXT,
                question TEXT NOT NULL,
                history_json TEXT NOT NULL DEFAULT '[]',
                retrieved_doc_ids_json TEXT NOT NULL DEFAULT '[]',
                final_resolution TEXT,
                confidence TEXT,
                rating INTEGER,
                feedback_comment TEXT,
                is_resolved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Migrate existing installs: add new columns if missing
        for col, definition in [
            ("rating", "INTEGER"),
            ("feedback_comment", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE diagnose_sessions ADD COLUMN {col} {definition}")
            except Exception:
                pass
            try:
                conn.execute(f"ALTER TABLE conversations ADD COLUMN {col} {definition}")
            except Exception:
                pass
        conn.commit()

        columns = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
        if "status" not in columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN status TEXT")
            conn.commit()
        if "feedback_note" not in columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN feedback_note TEXT")
            conn.commit()
    finally:
        conn.close()


def insert_document(
    kind: str,
    text: str,
    embedding: list[float] | None,
    metadata: dict | None = None,
) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO documents (kind, text, metadata_json, embedding) VALUES (?, ?, ?, ?)",
            (kind, text, json.dumps(metadata or {}), _pack(embedding)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_documents_batch(
    rows: list[tuple[str, str, list[float] | None, dict]],
) -> list[int]:
    if not rows:
        return []
    conn = connect()
    try:
        ids: list[int] = []
        for kind, text, embedding, metadata in rows:
            cur = conn.execute(
                "INSERT INTO documents (kind, text, metadata_json, embedding) VALUES (?, ?, ?, ?)",
                (kind, text, json.dumps(metadata or {}), _pack(embedding)),
            )
            ids.append(cur.lastrowid)
        conn.commit()
        return ids
    finally:
        conn.close()


def search_similar(embedding: list[float], k: int = 6) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, kind, text, metadata_json, embedding FROM documents WHERE embedding IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    query = np.asarray(embedding, dtype=np.float32)
    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return []
    query = query / query_norm

    scored = []
    for r in rows:
        vec = _unpack(r["embedding"])
        norm = np.linalg.norm(vec)
        if norm == 0:
            continue
        sim = float(np.dot(query, vec / norm))
        scored.append((sim, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "id": r["id"],
            "kind": r["kind"],
            "text": r["text"],
            "metadata": json.loads(r["metadata_json"]),
            "score": sim,
        }
        for sim, r in scored[:k]
    ]


def list_all_documents(limit: int = 20) -> list[dict]:
    """Used in no-embeddings mode: return the most recent docs as 'all sources'."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, kind, text, metadata_json FROM documents ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "kind": r["kind"],
                "text": r["text"],
                "metadata": json.loads(r["metadata_json"]),
                "score": None,
            }
            for r in rows
        ]
    finally:
        conn.close()


def list_machines() -> list[str]:
    """Return distinct machine names extracted from ingested manual chunks."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT json_extract(metadata_json, '$.machine') AS machine "
            "FROM documents WHERE kind = 'manual_chunk' "
            "AND json_extract(metadata_json, '$.machine') IS NOT NULL"
        ).fetchall()
        return sorted(r["machine"] for r in rows)
    finally:
        conn.close()


def search_by_keywords(query: str, k: int = 6, machine: str | None = None) -> list[dict]:
    """Keyword-based fallback retrieval when embeddings are disabled.

    Scores each document by how many unique query terms appear in its text,
    then returns the top-k by score. Falls back to most-recent if no matches.

    When the query mentions a specific machine name, retrieval is first scoped
    to that machine's manual chunks to avoid cross-manual contamination.
    """
    _STOPWORDS = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "and", "or", "but", "not", "this",
        "that", "it", "its", "what", "which", "who", "how", "when", "where",
        "i", "my", "we", "our", "you", "your", "they", "their",
    }
    words = [w.lower() for w in re.split(r"\W+", query) if len(w) > 2 and w.lower() not in _STOPWORDS]
    if not words:
        return list_all_documents(limit=k)

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, kind, text, metadata_json FROM documents"
        ).fetchall()
    finally:
        conn.close()

    # Scope to a specific machine's chunks when one is identified.
    if machine:
        scoped = [
            r for r in rows
            if r["kind"] != "manual_chunk"
            or json.loads(r["metadata_json"]).get("machine") == machine
        ]
        if scoped:
            rows = scoped

    scored = []
    for r in rows:
        text_lower = r["text"].lower()
        score = sum(1 for w in words if w in text_lower)
        if score > 0:
            scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return list_all_documents(limit=k)

    return [
        {
            "id": r["id"],
            "kind": r["kind"],
            "text": r["text"],
            "metadata": json.loads(r["metadata_json"]),
            "score": score,
        }
        for score, r in scored[:k]
    ]


def insert_conversation(
    question: str, answer: str, retrieved_doc_ids: list[int]
) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO conversations (question, answer, retrieved_doc_ids_json) VALUES (?, ?, ?)",
            (question, answer, json.dumps(retrieved_doc_ids)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_conversation_status(conversation_id: int, status: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "UPDATE conversations SET status = ? WHERE id = ?",
            (status, conversation_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_conversation_feedback_note(conversation_id: int, note: str | None) -> None:
    conn = connect()
    try:
        conn.execute(
            "UPDATE conversations SET feedback_note = ? WHERE id = ?",
            (note, conversation_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_conversations(limit: int = 100) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT id, question, answer, rating, feedback_comment, created_at
               FROM conversations ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "question": r["question"],
                "answer": r["answer"],
                "rating": r["rating"],
                "feedback_comment": r["feedback_comment"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_conversation(conversation_id: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, question, answer, retrieved_doc_ids_json, status, feedback_note FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "question": row["question"],
            "answer": row["answer"],
            "retrieved_doc_ids": json.loads(row["retrieved_doc_ids_json"]),
            "status": row["status"],
            "feedback_note": row["feedback_note"],
        }
    finally:
        conn.close()


def update_conversation_rating(conversation_id: int, rating: int, comment: str | None = None) -> bool:
    conn = connect()
    try:
        cur = conn.execute(
            "UPDATE conversations SET rating = ?, feedback_comment = ? WHERE id = ?",
            (rating, comment, conversation_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_topics(include_documents: bool = False) -> list[dict]:
    """Distinct topic paths with per-kind counts. Powers the topic browser.

    With include_documents=True, each topic carries its full document list so
    the UI can render an expandable tree.
    """
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, kind, text, metadata_json, created_at FROM documents ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    buckets: dict[tuple, dict] = {}
    for r in rows:
        meta = json.loads(r["metadata_json"])
        path = meta.get("topic_path")
        if not path:
            continue
        key = tuple(path)
        bucket = buckets.setdefault(
            key,
            {
                "path": list(path),
                "manual_count": 0,
                "knowledge_count": 0,
                "documents": [],
            },
        )
        if r["kind"] == "manual_chunk":
            bucket["manual_count"] += 1
        elif r["kind"] == "knowledge_entry":
            bucket["knowledge_count"] += 1

        if include_documents:
            bucket["documents"].append(
                {
                    "id": r["id"],
                    "kind": r["kind"],
                    "text": r["text"],
                    "metadata": meta,
                    "created_at": r["created_at"],
                }
            )

    out = sorted(buckets.values(), key=lambda x: " > ".join(x["path"]))
    if not include_documents:
        for b in out:
            del b["documents"]
    return out


def list_existing_topic_paths(limit: int = 2000) -> list[list[str]]:
    """All distinct topic paths in the DB, for tagger consistency."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT metadata_json FROM documents LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    seen: set[tuple] = set()
    out: list[list[str]] = []
    for r in rows:
        meta = json.loads(r["metadata_json"])
        tp = meta.get("topic_path")
        if not tp:
            continue
        key = tuple(tp)
        if key not in seen:
            seen.add(key)
            out.append(tp)
    return out


def list_manuals() -> list[dict]:
    """Return distinct manuals with chunk count and source path."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT metadata_json FROM documents WHERE kind = 'manual_chunk'"
        ).fetchall()
    finally:
        conn.close()
    seen: dict[str, dict] = {}
    for r in rows:
        meta = json.loads(r["metadata_json"])
        title = meta.get("manual_title", "")
        if not title:
            continue
        if title not in seen:
            seen[title] = {"title": title, "chunks": 0, "source_path": meta.get("source_path", "")}
        seen[title]["chunks"] += 1
    return list(seen.values())


def delete_manual(title: str) -> int:
    """Delete all chunks for a manual. Returns number of rows deleted."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id FROM documents WHERE json_extract(metadata_json, '$.manual_title') = ?",
            (title,)
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            conn.execute(
                f"DELETE FROM documents WHERE id IN ({','.join('?' for _ in ids)})", ids
            )
            conn.commit()
        return len(ids)
    finally:
        conn.close()


def upsert_diagnose_session(
    session_id: str,
    question: str,
    machine: str | None,
    history: list[dict],
    retrieved_doc_ids: list[int],
    is_resolved: bool,
    final_resolution: str | None = None,
    confidence: str | None = None,
) -> None:
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO diagnose_sessions
                (session_id, machine, question, history_json, retrieved_doc_ids_json,
                 is_resolved, final_resolution, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                history_json = excluded.history_json,
                retrieved_doc_ids_json = excluded.retrieved_doc_ids_json,
                is_resolved = excluded.is_resolved,
                final_resolution = excluded.final_resolution,
                confidence = excluded.confidence,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                session_id, machine, question,
                json.dumps(history, ensure_ascii=False),
                json.dumps(retrieved_doc_ids),
                int(is_resolved), final_resolution, confidence,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_diagnose_sessions(limit: int = 200) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT session_id, machine, question, is_resolved, final_resolution,
                   confidence, rating, feedback_comment, created_at, updated_at,
                   (SELECT COUNT(*) FROM json_each(history_json)) AS turn_count
            FROM diagnose_sessions
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "session_id": r["session_id"],
                "machine": r["machine"],
                "question": r["question"],
                "is_resolved": bool(r["is_resolved"]),
                "final_resolution": r["final_resolution"],
                "confidence": r["confidence"],
                "rating": r["rating"],
                "feedback_comment": r["feedback_comment"],
                "turn_count": r["turn_count"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_diagnose_session(session_id: str) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT session_id, machine, question, history_json, retrieved_doc_ids_json,
                   is_resolved, final_resolution, confidence, feedback, created_at, updated_at
            FROM diagnose_sessions WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "machine": row["machine"],
            "question": row["question"],
            "history": json.loads(row["history_json"]),
            "retrieved_doc_ids": json.loads(row["retrieved_doc_ids_json"]),
            "is_resolved": bool(row["is_resolved"]),
            "final_resolution": row["final_resolution"],
            "confidence": row["confidence"],
            "feedback": row["feedback"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


def update_diagnose_feedback(session_id: str, rating: int, comment: str | None = None) -> bool:
    conn = connect()
    try:
        cur = conn.execute(
            "UPDATE diagnose_sessions SET rating = ?, feedback_comment = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
            (rating, comment, session_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_knowledge_entries(limit: int = 100) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT id, text, metadata_json, created_at
            FROM documents
            WHERE kind = 'knowledge_entry'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "text": r["text"],
                "metadata": json.loads(r["metadata_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()

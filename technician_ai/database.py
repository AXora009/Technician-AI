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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
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


def search_by_keywords(query: str, k: int = 6) -> list[dict]:
    """Keyword-based fallback retrieval when embeddings are disabled.

    Scores each document by how many unique query terms appear in its text,
    then returns the top-k by score. Falls back to most-recent if no matches.
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


def get_conversation(conversation_id: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, question, answer, retrieved_doc_ids_json FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "question": row["question"],
            "answer": row["answer"],
            "retrieved_doc_ids": json.loads(row["retrieved_doc_ids_json"]),
        }
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
            "SELECT id FROM documents WHERE metadata_json LIKE ?",
            (f'%"manual_title": "{title}"%',)
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

"""Backfill topic_path / entry_type / title on documents missing them.

Idempotent: rows that already carry a topic_path are skipped.
Run after upgrading from a pre-tagging build, or any time tagging gets
extended. Safe to re-run.
"""
import json

from dotenv import load_dotenv

load_dotenv(override=True)

from technician_ai import database as db
from technician_ai import tagging as tagger


def main() -> None:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id, kind, text, metadata_json FROM documents ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    untagged = []
    existing_topics: list[list[str]] = []
    seen: set[tuple] = set()
    for r in rows:
        meta = json.loads(r["metadata_json"])
        tp = meta.get("topic_path")
        if tp:
            key = tuple(tp)
            if key not in seen:
                seen.add(key)
                existing_topics.append(tp)
        else:
            untagged.append((r["id"], r["kind"], r["text"], meta))

    print(f"{len(untagged)} of {len(rows)} documents need tagging")
    if not untagged:
        return

    conn = db.connect()
    try:
        for i, (doc_id, kind, text, meta) in enumerate(untagged, start=1):
            source_label = meta.get("manual_title") or (
                "(field knowledge)" if kind == "knowledge_entry" else "(unknown)"
            )
            tags = tagger.tag_content(text, source_label=source_label, existing_topics=existing_topics)
            meta.update(
                {
                    "topic_path": tags["topic_path"],
                    "entry_type": tags["entry_type"],
                    "title": tags["title"],
                }
            )
            conn.execute(
                "UPDATE documents SET metadata_json = ? WHERE id = ?",
                (json.dumps(meta), doc_id),
            )
            existing_topics.append(tags["topic_path"])
            print(
                f"  {i}/{len(untagged)}  #{doc_id:<4} {tags['title']!r:<40} "
                f"[{' > '.join(tags['topic_path'])} / {tags['entry_type']}]"
            )
        conn.commit()
    finally:
        conn.close()
    print("done")


if __name__ == "__main__":
    main()

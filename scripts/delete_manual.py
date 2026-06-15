"""Delete all chunks from a specific manual so it can be re-ingested."""
import json
import sys

from technician_ai import database as db

title = sys.argv[1] if len(sys.argv) > 1 else None
if not title:
    conn = db.connect()
    rows = conn.execute("SELECT DISTINCT metadata_json FROM documents").fetchall()
    conn.close()
    titles = set()
    for r in rows:
        t = json.loads(r[0]).get("manual_title", "")
        if t:
            titles.add(t)
    print("Available manuals:")
    for t in sorted(titles):
        print(f"  {t!r}")
    sys.exit(0)

conn = db.connect()
rows = conn.execute("SELECT id, metadata_json FROM documents").fetchall()
to_delete = [r["id"] for r in rows if json.loads(r["metadata_json"]).get("manual_title") == title]
if not to_delete:
    print(f"No chunks found for {title!r}")
    conn.close()
    sys.exit(1)
conn.execute(f"DELETE FROM documents WHERE id IN ({','.join('?' for _ in to_delete)})", to_delete)
conn.commit()
conn.close()
print(f"Deleted {len(to_delete)} chunks for {title!r}")

import json

from technician_ai import database as db

conn = db.connect()
rows = conn.execute("SELECT id, text, metadata_json FROM documents").fetchall()
conn.close()

manuals = {}
for r in rows:
    meta = json.loads(r['metadata_json'])
    title = meta.get('manual_title', 'unknown')
    manuals.setdefault(title, []).append((r['id'], r['text']))

for title, chunks in manuals.items():
    print(f"MANUAL: {title} | chunks: {len(chunks)}")

# Search for voltage-related content
print("\n--- Voltage keyword search ---")
results = db.search_by_keywords('voltage control power supply camera light source', k=6)
for r in results:
    print(f"score={r['score']} id={r['id']} manual={json.loads(conn.execute('SELECT metadata_json FROM documents WHERE id=?',(r['id'],)).fetchone()[0] if False else r['metadata'].get('manual_title','?'))} | {r['text'][:200]}")
    print()

import json

from technician_ai import database as db

conn = db.connect()
rows = conn.execute(
    "SELECT id, text, metadata_json FROM documents ORDER BY id"
).fetchall()
conn.close()

# Show all manuals
manuals = {}
for r in rows:
    meta = json.loads(r['metadata_json'])
    title = meta.get('manual_title', 'unknown')
    manuals.setdefault(title, 0)
    manuals[title] += 1

print("=== Manuals in DB ===")
for t, c in manuals.items():
    print(f"  {t}: {c} chunks")

# Search for potential/overview related chunks
print("\n=== Chunks containing 'potential' or 'overview' or '12V' or '12 VDC' ===")
keywords = ['potential', 'overview', '12v', '12 vdc', 'c102', 'c103']
for r in rows:
    text_lower = r['text'].lower()
    if any(k in text_lower for k in keywords):
        meta = json.loads(r['metadata_json'])
        page = meta.get('page', meta.get('slide', '?'))
        title = meta.get('manual_title', '?')
        print(f"\n[id={r['id']} | {title} | p.{page}]")
        print(r['text'][:400])
        print("---")

"""Vocabulary for entry types and topic structure.

Designed so the move from Option B (chunk-level tagging) to Option C
(atomic-entry extraction) is purely additive. The fields below land in
`documents.metadata_json` today, and the same names will apply to atomic
entries when we ship C — Option C just adds `content`, `conditions`, and
`parent_chunk_id` alongside what's already here.
"""

ENTRY_TYPES = [
    "spec",             # torque values, dimensions, tolerances, numeric specs
    "procedure",        # how-to steps, sequences, workflows
    "warning",          # safety, caution, limits, do-not
    "troubleshooting",  # symptom → diagnosis → fix
    "part_info",        # part descriptions, identifiers, BOM details
    "reference",        # overview, index, glossary, contextual material
    "unknown",          # fallback when content can't be classified
]

# Forward-compatible field set. B uses the first three; C will add the rest.
TAG_FIELDS = ["topic_path", "entry_type", "title"]
ATOMIC_ENTRY_FIELDS = TAG_FIELDS + ["content", "conditions", "parent_chunk_id"]

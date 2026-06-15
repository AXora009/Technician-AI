"""Check text extraction for a specific PDF page."""
import sys
from pathlib import Path
from pypdf import PdfReader
import os
from dotenv import load_dotenv
load_dotenv(override=True)

print("USE_VISION_INGEST =", os.environ.get("USE_VISION_INGEST"))

pdf_path = Path("manuals/04_02 All in one soldering machine Circuit Diagram.pdf")
reader = PdfReader(str(pdf_path))
print(f"Total pages: {len(reader.pages)}\n")

# Check pages 1-10
for page_num in range(1, min(11, len(reader.pages) + 1)):
    page = reader.pages[page_num - 1]
    text = (page.extract_text() or "").strip()
    print(f"Page {page_num}: {len(text)} chars | preview: {text[:80].replace(chr(10), ' ')!r}")

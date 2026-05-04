"""
RAGEngine — Indexes documents in the data/ folder and retrieves relevant chunks.
Supports .txt, .md, and optionally .pdf (requires pypdf or pdfplumber).
"""

import re
import math
from pathlib import Path
from typing import List, Optional


class RAGEngine:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.chunks: List[dict] = []  # {"source": str, "text": str, "tokens": frozenset}
        self._load_documents()

    def _load_documents(self):
        if not self.data_dir.exists():
            return
        for path in sorted(self.data_dir.iterdir()):
            if path.suffix in (".txt", ".md"):
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    self._index(text, path.name)
                except OSError:
                    pass
            elif path.suffix == ".pdf":
                text = self._read_pdf(path)
                if text:
                    self._index(text, path.name)

    def _read_pdf(self, path: Path) -> Optional[str]:
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            pass
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except ImportError:
            return None

    def _index(self, text: str, source: str):
        for chunk_text in self._split(text):
            tokens = frozenset(re.findall(r'\b\w+\b', chunk_text.lower()))
            self.chunks.append({"source": source, "text": chunk_text, "tokens": tokens})

    def _split(self, text: str, max_chars: int = 600) -> List[str]:
        paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
        result = []
        for para in paragraphs:
            if len(para) <= max_chars:
                result.append(para)
            else:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                buf = ""
                for sent in sentences:
                    if buf and len(buf) + len(sent) > max_chars:
                        result.append(buf.strip())
                        buf = sent
                    else:
                        buf = (buf + " " + sent).strip()
                if buf:
                    result.append(buf)
        return result

    def search(self, query: str, top_k: int = 3) -> List[dict]:
        if not self.chunks:
            return []
        query_tokens = frozenset(re.findall(r'\b\w+\b', query.lower()))
        scored = []
        for chunk in self.chunks:
            overlap = len(query_tokens & chunk["tokens"])
            if overlap:
                # Normalize by chunk length to favour focused snippets
                score = overlap / math.sqrt(len(chunk["tokens"]))
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    def has_documents(self) -> bool:
        return bool(self.chunks)

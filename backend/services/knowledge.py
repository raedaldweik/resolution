"""Local policy retrieval over knowledge_base/ — the Knowledge & Policy
agent's grounding source on this branch (no RAM collections).

Indexes every PDF/MD/TXT in knowledge_base/ at startup: PDFs page by page
(pypdf, falling back to poppler's pdftotext), chunked per page, scored by
token overlap. Deliberately simple and fully local — the citations shown in
the UI (filename + page) point at real text in this repo."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

KB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base"))

_chunks: list[dict] = []


def _pdf_pages(path: str) -> list[str]:
    try:
        from pypdf import PdfReader
        return [(p.extract_text() or "") for p in PdfReader(path).pages]
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        # BaseException on purpose: a broken system pypdf/cryptography pairing
        # raises a pyo3 PanicException that is NOT an Exception subclass —
        # fall through to poppler either way.
        pass
    try:  # poppler fallback (pdftotext ships in the Docker image)
        with tempfile.NamedTemporaryFile(suffix=".txt") as tmp:
            subprocess.run(["pdftotext", "-layout", path, tmp.name], check=True,
                           capture_output=True, timeout=60)
            return open(tmp.name, encoding="utf-8", errors="replace").read().split("\f")
    except Exception:
        return []


def _split(text: str, max_chars: int = 900) -> list[str]:
    parts, current = [], ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) > max_chars and current:
            parts.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        parts.append(current)
    return parts


def load_index() -> int:
    _chunks.clear()
    if not os.path.isdir(KB_DIR):
        return 0
    for fname in sorted(os.listdir(KB_DIR)):
        path = os.path.join(KB_DIR, fname)
        if fname.lower().endswith(".pdf"):
            for page_no, page_text in enumerate(_pdf_pages(path), start=1):
                for part in _split(page_text):
                    _chunks.append({"filename": fname, "page": page_no, "text": part})
        elif fname.lower().endswith((".md", ".txt")) and fname.lower() != "readme.md":
            for part in _split(open(path, encoding="utf-8", errors="replace").read()):
                _chunks.append({"filename": fname, "page": None, "text": part})
    return len(_chunks)


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[\w؀-ۿ]{3,}", s.lower())}


def search(query: str, k: int = 4) -> list[dict]:
    q = _tokens(query)
    if not q:
        return []
    scored = []
    for ch in _chunks:
        t = _tokens(ch["text"])
        overlap = len(q & t)
        if overlap:
            scored.append((overlap / (len(q) ** 0.5), ch))
    scored.sort(key=lambda x: -x[0])
    return [{"filename": c["filename"], "page": c["page"],
             "text": c["text"][:1200], "score": round(s, 2)}
            for s, c in scored[:k]]


def stats() -> dict:
    files = sorted({c["filename"] for c in _chunks})
    return {"chunks": len(_chunks), "documents": files}

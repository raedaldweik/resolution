"""API routes the frontend calls. Thin layer over services.ram."""
from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from services import ram

router = APIRouter(prefix="/api", tags=["ram"])

# Attached documents are inlined into the query text — keep them inside a
# sane prompt budget for the agent's LLM.
MAX_ATTACH_CHARS = 20_000


class Attachment(BaseModel):
    name: str
    text: str


class QueryRequest(BaseModel):
    content: str
    agentId: str | None = None
    collectionIds: list[str] | None = None
    querySessionId: str | None = None
    attachments: list[Attachment] | None = None


class AuthCode(BaseModel):
    code: str


def _wrap(coro):
    async def run():
        try:
            return await coro
        except ram.RamError as e:
            raise HTTPException(status_code=e.status if 400 <= e.status < 600 else 502, detail=e.message)
        except Exception as e:  # network errors, DNS, TLS …
            raise HTTPException(status_code=502, detail=f"Could not reach SAS RAM: {e}")
    return run()


@router.get("/health")
async def health():
    return await ram.status_async()


# ─── Interactive sign-in ─────────────────────────────────────────────
@router.post("/auth/device/start")
async def auth_device_start():
    return await _wrap(ram.device_start())


@router.post("/auth/device/poll")
async def auth_device_poll():
    return await _wrap(ram.device_poll())


@router.post("/auth/viya/code")
async def auth_viya_code(body: AuthCode):
    if not body.code.strip():
        raise HTTPException(status_code=400, detail="Paste the authorization code first.")
    return await _wrap(ram.viya_code_exchange(body.code))


# ─── Attachments (ad-hoc documents, inlined into the query) ─────────
@router.post("/extract")
async def extract(file: UploadFile = File(...)):
    """Extract plain text from an uploaded document so it can be sent
    inline with a question. RAM's query API is text-only, so this is how
    ad-hoc files reach the agent without indexing them into a collection."""
    data = await file.read()
    name = file.filename or "attachment"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if ext == "pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not read PDF: {e}")
        if not text.strip():
            raise HTTPException(status_code=422, detail=(
                "This PDF contains no extractable text (it looks scanned). "
                "Export the page as a PNG/JPG and attach that instead — images are OCR'd."))
    elif ext == "docx":
        try:
            from docx import Document
        except ImportError:
            raise HTTPException(status_code=415, detail="DOCX support requires python-docx (pip install python-docx).")
        try:
            doc = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not read DOCX: {e}")
    elif ext in ("txt", "md", "csv", "json", "log", "xml", "html", "yaml", "yml", "sas", "sql", "py"):
        text = data.decode("utf-8", errors="replace")
    elif ext in ("png", "jpg", "jpeg", "bmp", "webp", "tif", "tiff"):
        # Scanned documents are OCR'd locally (tesseract, Arabic + English) —
        # the same engine behind the Document Processing agent's MCP server.
        try:
            import pytesseract
            from PIL import Image
            text = pytesseract.image_to_string(Image.open(io.BytesIO(data)), lang="ara+eng")
        except ImportError:
            raise HTTPException(status_code=415, detail=(
                "OCR isn't installed on this server (pip install pytesseract Pillow "
                "+ the tesseract-ocr system package)."))
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"OCR failed: {e}")
        if not text.strip():
            raise HTTPException(status_code=422, detail=(
                "OCR found no readable text in this image — try a sharper scan."))
    else:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: .{ext or '?'}")

    truncated = len(text) > MAX_ATTACH_CHARS
    return {"name": name, "text": text[:MAX_ATTACH_CHARS], "chars": len(text), "truncated": truncated}


# ─── RAM proxy ───────────────────────────────────────────────────────
@router.get("/agents")
async def agents():
    return await _wrap(ram.list_agents())


@router.get("/collections")
async def collections():
    return await _wrap(ram.list_collections())


@router.get("/sessions")
async def sessions():
    return await _wrap(ram.list_sessions())


@router.get("/sessions/{session_id}/queries")
async def session_queries(session_id: str):
    return await _wrap(ram.list_session_queries(session_id))


@router.post("/query")
async def query(body: QueryRequest):
    """Submit a query asynchronously. Returns {queryId, querySessionId,
    pollInterval, timeout} — poll GET /api/query/{queryId} for the result
    (a `result` key is included directly when RAM answered inline)."""
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Empty query.")
    content = body.content
    if body.attachments:
        for a in body.attachments:
            content += f"\n\n--- Attached document: {a.name} ---\n{a.text[:MAX_ATTACH_CHARS]}\n--- End of attached document ---"
        content += "\n\nUse the attached document content above to answer the question where relevant."
    return await _wrap(ram.submit_query(
        content,
        agent_id=body.agentId,
        collection_ids=body.collectionIds,
        session_id=body.querySessionId,
    ))


@router.get("/query/{query_id}")
async def query_status(query_id: str):
    return await _wrap(ram.query_status(query_id))


@router.get("/query/{query_id}/trace")
async def query_trace(query_id: str):
    return await _wrap(ram.query_trace(query_id))

"""API routes the frontend calls. Thin layer over services.ram."""
from __future__ import annotations

import io
import os
import uuid
from collections import OrderedDict

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File
from pydantic import BaseModel

from services import ram

router = APIRouter(prefix="/api", tags=["ram"])

# Attached documents are inlined into the query text — keep them inside a
# sane prompt budget for the agent's LLM.
MAX_ATTACH_CHARS = 20_000

# Uploaded scans, held in memory and served at /api/files/{id} so the RAM
# Document Processing agent can fetch them with its ocr_document tool
# (image_url). Capability URLs: unguessable UUID ids, bounded buffer.
_FILES: OrderedDict[str, tuple[bytes, str, str]] = OrderedDict()  # id -> (bytes, content_type, name)
MAX_STORED_FILES = 24


def _store_file(data: bytes, content_type: str, name: str) -> str:
    file_id = uuid.uuid4().hex
    _FILES[file_id] = (data, content_type, name)
    while len(_FILES) > MAX_STORED_FILES:
        _FILES.popitem(last=False)
    return file_id


def _public_base(request: Request) -> str:
    """Absolute base URL the MCP container can fetch from. PUBLIC_BASE_URL
    wins (set it to the deployed domain, e.g. https://moce-ui.up.railway.app);
    otherwise derive from the request, honoring the proxy's forwarded proto."""
    explicit = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if explicit:
        return explicit
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


class Attachment(BaseModel):
    name: str
    text: str | None = None
    imageUrl: str | None = None   # scanned document → agent reads it via ocr_document


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


# ─── Attachments ─────────────────────────────────────────────────────
# Text documents (PDF/DOCX/TXT…) are extracted here and inlined into the
# query — RAM's query API is text-only. Scanned images are different: they
# are stored and served at /api/files/{id}, and the query instructs the
# Document Processing agent to read them itself with its ocr_document MCP
# tool — so the parsing genuinely happens in the RAM agent.
@router.get("/files/{file_id}")
async def serve_file(file_id: str):
    entry = _FILES.get(file_id)
    if not entry:
        raise HTTPException(status_code=404, detail="File expired or unknown.")
    data, content_type, name = entry
    return Response(content=data, media_type=content_type,
                    headers={"Content-Disposition": f'inline; filename="{name}"'})


@router.post("/extract")
async def extract(request: Request, file: UploadFile = File(...)):
    """Prepare an uploaded document to be sent with the next question:
    text formats come back as extracted text; images come back as a hosted
    URL for the agent's OCR tool (plus kind="image")."""
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
        # Scanned document: host it and hand the AGENT the URL — its
        # ocr_document MCP tool does the reading (real agent-side OCR).
        content_type = file.content_type or f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
        file_id = _store_file(data, content_type, name)
        return {"name": name, "kind": "image",
                "url": f"{_public_base(request)}/api/files/{file_id}",
                "chars": 0, "truncated": False}
    else:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: .{ext or '?'}")

    truncated = len(text) > MAX_ATTACH_CHARS
    return {"name": name, "kind": "text", "text": text[:MAX_ATTACH_CHARS],
            "chars": len(text), "truncated": truncated}


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
            if a.imageUrl:
                content += (
                    f"\n\n--- Attached scanned document: {a.name} ---\n"
                    f"The user attached a scanned document image. Read it yourself with your "
                    f"OCR tooling before answering: call ocr_document with "
                    f"image_url=\"{a.imageUrl}\" to extract the text, then classify_document "
                    f"and extract_fields on that text as needed. Do not guess the document's "
                    f"contents without reading it, and quote extracted values exactly.")
            elif a.text:
                content += f"\n\n--- Attached document: {a.name} ---\n{a.text[:MAX_ATTACH_CHARS]}\n--- End of attached document ---"
        content += "\n\nUse the attached document(s) above to answer the question where relevant."
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

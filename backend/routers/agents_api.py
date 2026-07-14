"""API routes for the no-RAM branch — same paths and shapes the frontend
already uses, backed by the local Claude-agent runtime instead of RAM."""
from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, HTTPException, Response, UploadFile, File
from pydantic import BaseModel

from services import agents

router = APIRouter(prefix="/api", tags=["agents"])

MAX_ATTACH_CHARS = 8000
MAX_STORED_FILES = 24


class Attachment(BaseModel):
    name: str
    text: str | None = None
    imageUrl: str | None = None
    fileId: str | None = None


class QueryRequest(BaseModel):
    content: str
    agentId: str | None = None
    collectionIds: list[str] | None = None
    querySessionId: str | None = None
    attachments: list[Attachment] | None = None


@router.get("/health")
async def health():
    return agents.health()


# Sign-in endpoints exist so the frontend's calls never 404; there is no
# interactive auth on this branch (the key is an env var).
@router.post("/auth/device/start")
async def auth_start():
    raise HTTPException(400, "No sign-in needed — set ANTHROPIC_API_KEY on the service.")


@router.post("/auth/device/poll")
async def auth_poll():
    raise HTTPException(400, "No sign-in needed on this deployment.")


@router.post("/auth/viya/code")
async def auth_code():
    raise HTTPException(400, "No sign-in needed on this deployment.")


# ─── Attachments ─────────────────────────────────────────────────────
@router.get("/files/{file_id}")
async def serve_file(file_id: str):
    entry = agents.FILES.get(file_id)
    if not entry:
        raise HTTPException(404, "File expired or unknown.")
    data, content_type, name = entry
    return Response(content=data, media_type=content_type,
                    headers={"Content-Disposition": f'inline; filename="{name}"'})


@router.post("/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    name = file.filename or "attachment"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if ext == "pdf":
        try:
            from pypdf import PdfReader
            text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        except Exception as e:
            raise HTTPException(422, f"Could not read PDF: {e}")
        if not text.strip():
            raise HTTPException(422, "This PDF has no text layer (scanned) — attach it as PNG/JPG instead.")
    elif ext == "docx":
        try:
            from docx import Document
            text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        except Exception as e:
            raise HTTPException(422, f"Could not read DOCX: {e}")
    elif ext in ("txt", "md", "csv", "json", "log", "xml", "html", "yaml", "yml", "sas", "sql", "py"):
        text = data.decode("utf-8", errors="replace")
    elif ext in ("png", "jpg", "jpeg", "bmp", "webp", "tif", "tiff"):
        # Scanned document: keep the bytes; the agent reads them itself with
        # its ocr_document tool (file_id) — no OCR here, no networking needed.
        file_id = uuid.uuid4().hex
        agents.FILES[file_id] = (data, file.content_type or f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}", name)
        while len(agents.FILES) > MAX_STORED_FILES:
            agents.FILES.pop(next(iter(agents.FILES)))
        return {"name": name, "kind": "image", "fileId": file_id,
                "url": f"/api/files/{file_id}", "chars": 0, "truncated": False}
    else:
        raise HTTPException(415, f"Unsupported file type: .{ext or '?'}")

    truncated = len(text) > MAX_ATTACH_CHARS
    return {"name": name, "kind": "text", "text": text[:MAX_ATTACH_CHARS],
            "chars": len(text), "truncated": truncated}


# ─── Agents / sessions / queries ─────────────────────────────────────
@router.get("/agents")
async def list_agents():
    return agents.list_agents()


@router.get("/collections")
async def collections():
    return []   # no RAM collections — knowledge lives in the Knowledge agent


@router.get("/sessions")
async def sessions():
    return agents.list_sessions()


@router.get("/sessions/{session_id}/queries")
async def session_queries(session_id: str):
    return agents.session_queries(session_id)


@router.post("/query")
async def query(body: QueryRequest):
    if not body.content.strip():
        raise HTTPException(400, "Empty query.")
    content = body.content
    if body.attachments:
        for a in body.attachments:
            file_id = a.fileId or (a.imageUrl.rsplit("/", 1)[-1] if a.imageUrl and "/api/files/" in a.imageUrl else None)
            if file_id:
                content += (
                    f"\n\n--- Attached scanned document: {a.name} ---\n"
                    f"The user attached a scanned document image. Read it yourself before "
                    f"answering: call ocr_document with file_id=\"{file_id}\", then "
                    f"classify_document and extract_fields on the OCR text. Do not guess "
                    f"the document's contents, and quote extracted values exactly.")
            elif a.text:
                content += f"\n\n--- Attached document: {a.name} ---\n{a.text[:MAX_ATTACH_CHARS]}\n--- End of attached document ---"
        content += "\n\nUse the attached document(s) above to answer the question where relevant."
    try:
        return agents.submit(content, body.agentId, body.querySessionId)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(400, str(e))


@router.get("/query/{query_id}")
async def query_status(query_id: str):
    try:
        return agents.status(query_id)
    except KeyError:
        raise HTTPException(404, "Unknown query id.")


@router.get("/query/{query_id}/trace")
async def query_trace(query_id: str):
    return agents.trace(query_id)


@router.get("/query/{query_id}/raw")
async def query_raw(query_id: str):
    try:
        return agents.raw(query_id)
    except KeyError:
        raise HTTPException(404, "Unknown query id.")

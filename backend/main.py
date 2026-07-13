"""MoCE Agent Ecosystem Demo — API.

Serves the demo API and (in production builds) the compiled frontend.
Every /api route is a thin shell over the simulated SAS layer in engine/;
swapping to live SAS Viya + RAM replaces engine/ internals, not this surface.
"""

import asyncio
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import live_ram
import llm_agent
import sas_id
from store import store
from engine import cases as case_engine
from engine import decisioning, documents, resolution

app = FastAPI(title="MoCE Agent Ecosystem Demo", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ schemas

class SessionIn(BaseModel):
    channel: str = "citizen"          # citizen | contact_center
    citizenId: str = "784-1985-9384756-1"
    lang: str = "en"


class ChatIn(BaseModel):
    sessionId: str
    message: str
    lang: str = "en"


class UploadIn(BaseModel):
    sessionId: str
    docKey: str                       # salary_cert_clean | salary_cert_blurry


class ReviewIn(BaseModel):
    corrections: dict = {}
    reviewer: str = "l.alshamsi@moce.gov.ae"


class RuleUpdateIn(BaseModel):
    params: dict
    actor: str = "s.alketbi@moce.gov.ae"


class PublishIn(BaseModel):
    note: str = "Threshold update"
    actor: str = "s.alketbi@moce.gov.ae"


class FlowTestIn(BaseModel):
    citizenId: str
    version: int | None = None


class ApproveIn(BaseModel):
    stage: int
    actor: str
    decision: str = "APPROVE_RECOMMENDATION"
    comment: str = ""


# ------------------------------------------------------------------ meta

def _mode() -> str:
    if live_ram.sas_chat_enabled():
        return "SAS_LIVE"
    if llm_agent.llm_chat_enabled():
        return "LLM_LIVE"
    return "SIMULATION"


def _badge(mode: str) -> str:
    if mode == "SAS_LIVE":
        return "LIVE · SAS RAM"
    if mode == "LLM_LIVE":
        return ("LIVE · Claude agent + SAS Intelligent Decisioning"
                if sas_id.enabled() else "LIVE · Claude agent")
    return "SIMULATION · SAS swap-ready"


@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": _mode(),
            "ram": await live_ram.health(),
            "llm": llm_agent.health(),
            "sasDecisioning": sas_id.health()}


@app.get("/api/meta")
def meta():
    mode = _mode()
    return {
        "mode": mode,
        "badge": _badge(mode),
        "capabilities": {"chat": {"SAS_LIVE": "sas", "LLM_LIVE": "claude"}.get(mode, "simulation"),
                         "documents": "simulation", "cases": "simulation",
                         "decisioning": "sas-id-mcp" if sas_id.enabled() else "simulation",
                         "governance": "simulation"},
        "title": "MoCE Agent Ecosystem",
        "agents": [
            {"key": "documents", "nameEn": "Document Processing", "sas": "SAS RAM agent + OCR pipeline + VTA"},
            {"key": "knowledge", "nameEn": "Knowledge & Decision", "sas": "SAS RAM agent + Intelligent Decisioning (MAS)"},
            {"key": "case", "nameEn": "Case Management", "sas": "RAM orchestrator + SAS Workflow Manager"},
            {"key": "resolution", "nameEn": "Customer Resolution", "sas": "RAM orchestrator + governed MCP action tools"},
        ],
        "citizens": [{"emiratesId": c["emiratesId"], "nameEn": c["nameEn"], "nameAr": c["nameAr"]}
                     for c in store.citizens.values()],
    }


@app.post("/api/demo/reset")
def reset():
    store.reset()
    return {"status": "reset"}


# ------------------------------------------------------------------ chat

@app.post("/api/session")
def create_session(body: SessionIn):
    s = resolution.create_session(body.channel, body.citizenId, body.lang)
    citizen = store.citizens[body.citizenId]
    return {"sessionId": s["sessionId"], "citizen": {
        "emiratesId": citizen["emiratesId"], "nameEn": citizen["nameEn"], "nameAr": citizen["nameAr"]},
        "suggestions": resolution._suggestions("start")}


@app.post("/api/chat")
async def chat(body: ChatIn):
    if body.sessionId not in store.sessions:
        raise HTTPException(404, "session not found")
    if live_ram.sas_chat_enabled():
        try:
            return await live_ram.chat(body.sessionId, body.message, body.lang)
        except Exception as e:
            raise HTTPException(502, f"SAS RAM error: {str(e)[:300]}")
    if llm_agent.llm_chat_enabled():
        try:
            return await llm_agent.chat(body.sessionId, body.message, body.lang)
        except Exception as e:
            raise HTTPException(502, f"Claude API error: {str(e)[:300]}")
    await asyncio.sleep(0.4)  # a touch of realism
    return resolution.handle_message(body.sessionId, body.message, body.lang)


@app.get("/api/session/{session_id}/events")
def poll_events(session_id: str):
    s = store.sessions.get(session_id)
    if not s:
        raise HTTPException(404, "session not found")
    events, s["events"] = s["events"], []
    return {"events": events, "stage": s["stage"],
            "suggestions": resolution._suggestions(s["stage"])}


# ------------------------------------------------------------------ documents

@app.post("/api/documents/upload")
async def upload(body: UploadIn):
    if body.docKey not in documents.SAMPLE_DOCS:
        raise HTTPException(400, "unknown sample document")
    s = store.sessions.get(body.sessionId)
    if not s:
        raise HTTPException(404, "session not found")
    await asyncio.sleep(1.2)  # OCR feel
    result = documents.process_document(body.sessionId, body.docKey, s["citizenId"])
    followup = resolution.on_document_processed(body.sessionId, result)
    llm_agent.note_event(body.sessionId, followup["answerEn"])
    return {"document": result, "chat": followup}


@app.get("/api/documents/queue")
def review_queue():
    return {"queue": store.review_queue}


@app.post("/api/documents/{document_id}/review")
def complete_review(document_id: str, body: ReviewIn):
    item = documents.complete_review(document_id, body.corrections, body.reviewer)
    resolution.on_review_completed(item["sessionId"], item)
    events = store.sessions.get(item["sessionId"], {}).get("events", [])
    if events:  # keep the Claude history in step with the injected agent message
        llm_agent.note_event(item["sessionId"], events[-1]["answerEn"])
    return {"document": item, "status": "APPROVED"}


@app.get("/api/documents/schemas")
def schemas():
    return {"schemas": list(store.doc_schemas.values())}


# ------------------------------------------------------------------ citizens (contact center)

@app.get("/api/citizens/{emirates_id}")
def citizen_360(emirates_id: str):
    c = store.citizens.get(emirates_id)
    if not c:
        raise HTTPException(404, "citizen not found")
    return {**c, "notifications": [n for n in store.notifications if n["to"] == c["nameEn"]]}


@app.get("/api/escalations")
def escalations():
    return {"escalations": store.escalations}


# ------------------------------------------------------------------ cases

@app.get("/api/cases")
def list_cases():
    return {"cases": sorted(store.cases, key=lambda c: c["createdAt"], reverse=True)}


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    case = next((c for c in store.cases if c["caseId"] == case_id), None)
    if not case:
        raise HTTPException(404, "case not found")
    return case


@app.post("/api/cases/{case_id}/approve")
def approve(case_id: str, body: ApproveIn):
    try:
        case, trace_id = case_engine.approve_stage(case_id, body.stage, body.actor,
                                                   body.decision, body.comment)
    except ValueError as e:
        raise HTTPException(400, str(e))
    events = store.sessions.get(case.get("sessionId"), {}).get("events", [])
    if trace_id and events:  # stage-2 close notifies the citizen chat — sync history
        llm_agent.note_event(case["sessionId"], events[-1]["answerEn"])
    return {"case": case, "executionTraceId": trace_id}


@app.get("/api/autonomy")
def autonomy():
    a = store.autonomy
    rate = a["aligned"] / a["casesEvaluated"]
    return {**a, "currentAlignment": round(rate, 4)}


# ------------------------------------------------------------------ decisioning

@app.get("/api/decisioning")
def decisioning_state():
    return decisioning.get_state()


@app.post("/api/decisioning/rules/{rule_id}")
def update_rule(rule_id: str, body: RuleUpdateIn):
    try:
        return decisioning.update_rule(rule_id, body.params, body.actor)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/decisioning/publish")
def publish(body: PublishIn):
    try:
        return decisioning.publish(body.note, body.actor)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/decisioning/test")
def test_flow(body: FlowTestIn):
    c = store.citizens.get(body.citizenId)
    if not c:
        raise HTTPException(404, "citizen not found")
    income = c["employment"]["monthlyIncomeAED"] or 23500
    result = decisioning.execute_flow({
        "monthlyIncomeAED": income, "nationality": c["nationality"],
        "familySize": c["familySize"], "verifiedWithinMonths": 0,
    }, version=body.version)
    return {"citizen": {"nameEn": c["nameEn"], "incomeAED": income}, **result}


# ------------------------------------------------------------------ governance

@app.get("/api/governance/traces")
def traces(limit: int = 40):
    items = list(reversed(store.traces))[:limit]
    return {"traces": [{k: t[k] for k in
                        ("traceId", "queryId", "agent", "channel", "prompt", "answerPreview",
                         "status", "ms", "costUSD")} |
                       {"toolCalls": len(t["toolCalls"]), "llmCalls": len(t["llmCalls"]),
                        "retrievalCalls": len(t["retrievalCalls"]),
                        "guardrails": len(t["guardrails"])}
                       for t in items]}


@app.get("/api/governance/traces/{trace_id}")
async def trace_detail(trace_id: str):
    t = next((t for t in store.traces if t["traceId"] == trace_id), None)
    if t:
        return t
    if live_ram.sas_chat_enabled():  # RAM query ids double as trace ids in live mode
        try:
            return await live_ram.get_trace(trace_id)
        except Exception:
            pass
    raise HTTPException(404, "trace not found")


@app.get("/api/governance/metrics")
def metrics():
    live_blocks = len(store.hallucination_log)
    return {**store.metrics,
            "liveTraces": len(store.traces),
            "liveHallucinationBlocks": live_blocks,
            "notifications": store.notifications[-6:]}


# ------------------------------------------------------------------ static frontend (production)

DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        target = os.path.join(DIST, path)
        if path and os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(DIST, "index.html"))

"""SAS-live adapter — routes the chat through a real SAS RAM agent.

Activated when APP_MODE=sas and RAM_API_URL is set. The rest of the demo
(documents, cases, decisioning, governance seeds) keeps running on the
simulation until those SAS pieces are wired; /api/meta reports per-capability
mode so the UI can badge honestly.

Environment:
  APP_MODE            simulation (default) | sas
  RAM_API_URL         https://<host>/SASRetrievalAgentManager/api/v1
  RAM_AGENT_NAME      RAM agent (or orchestrator agent) to converse with
  RAM_TOKEN           option A — static bearer token
  SAS_CLIENT_ID / SAS_CLIENT_SECRET   option B — client-credentials grant
  SAS_USERNAME / SAS_PASSWORD         option C — password grant (adds to B's client)
  SAS_LOGON_URL       token endpoint override (default <viya>/SASLogon/oauth/token)
  RAM_VERIFY_SSL      false to accept self-signed certs
"""

import asyncio
import os
import time

import httpx

APP_MODE = os.getenv("APP_MODE", "simulation").strip().lower()
RAM_API_URL = os.getenv("RAM_API_URL", "").rstrip("/")
RAM_AGENT_NAME = os.getenv("RAM_AGENT_NAME", "")
RAM_VERIFY_SSL = os.getenv("RAM_VERIFY_SSL", "true").strip().lower() != "false"
QUERY_TIMEOUT = int(os.getenv("RAM_QUERY_TIMEOUT", "180"))
POLL_INTERVAL = float(os.getenv("RAM_POLL_INTERVAL", "1.5"))

_token: dict = {"value": os.getenv("RAM_TOKEN", ""), "exp": 0}
_agent_id: dict = {"value": None}
_sessions: dict = {}  # our sessionId -> RAM querySessionId


def sas_chat_enabled() -> bool:
    return APP_MODE == "sas" and bool(RAM_API_URL)


def _logon_url() -> str:
    url = os.getenv("SAS_LOGON_URL")
    if url:
        return url
    return RAM_API_URL.split("/SASRetrievalAgentManager")[0] + "/SASLogon/oauth/token"


async def _get_token() -> str:
    if _token["value"] and (not _token["exp"] or _token["exp"] - time.time() > 60):
        return _token["value"]
    cid, secret = os.getenv("SAS_CLIENT_ID"), os.getenv("SAS_CLIENT_SECRET", "")
    if not cid:
        raise RuntimeError("No RAM_TOKEN and no SAS_CLIENT_ID configured")
    data = {"grant_type": "client_credentials"}
    if os.getenv("SAS_USERNAME"):
        data = {"grant_type": "password", "username": os.getenv("SAS_USERNAME"),
                "password": os.getenv("SAS_PASSWORD", "")}
    async with httpx.AsyncClient(verify=RAM_VERIFY_SSL, timeout=30) as c:
        r = await c.post(_logon_url(), data=data, auth=(cid, secret))
        r.raise_for_status()
        body = r.json()
    _token["value"] = body["access_token"]
    _token["exp"] = time.time() + int(body.get("expires_in", 3600))
    return _token["value"]


async def _req(method: str, path: str, *, params=None, json=None):
    tok = await _get_token()
    async with httpx.AsyncClient(verify=RAM_VERIFY_SSL, timeout=60) as c:
        r = await c.request(method, f"{RAM_API_URL}{path}", params=params, json=json,
                            headers={"Authorization": f"Bearer {tok}"})
        if r.status_code == 401:  # token expired mid-flight — refresh once
            _token["exp"] = 0
            tok = await _get_token()
            r = await c.request(method, f"{RAM_API_URL}{path}", params=params, json=json,
                                headers={"Authorization": f"Bearer {tok}"})
        r.raise_for_status()
        return r.json() if r.content else {}


async def _resolve_agent_id() -> str:
    if _agent_id["value"]:
        return _agent_id["value"]
    body = await _req("GET", "/agents", params={"limit": 100})
    for a in body.get("items", []):
        if a.get("name") == RAM_AGENT_NAME or a.get("id") == RAM_AGENT_NAME:
            _agent_id["value"] = a["id"]
            return a["id"]
    raise RuntimeError(f"RAM agent '{RAM_AGENT_NAME}' not found")


async def chat(session_id: str, text: str, lang: str = "en") -> dict:
    """Submit to the RAM agent and normalize into the demo's message shape."""
    agent_id = await _resolve_agent_id()
    payload = {"content": text, "agentId": agent_id}
    if session_id in _sessions:
        payload["querySessionId"] = _sessions[session_id]
    body = await _req("POST", "/query", params={"synchronous": "false", "persistent": "true"},
                      json=payload)
    qid = body.get("id") or body.get("queryId")
    if body.get("querySessionId"):
        _sessions[session_id] = body["querySessionId"]

    answer, deadline = None, time.time() + QUERY_TIMEOUT
    q = body
    while time.time() < deadline:
        state = (q.get("state") or q.get("status") or "").lower()
        if q.get("response") or state in ("completed", "failed", "error", "canceled"):
            break
        await asyncio.sleep(POLL_INTERVAL)
        res = await _req("GET", "/query", params={"filter": f"eq(id,'{qid}')", "limit": 1})
        items = res.get("items", [])
        q = items[0] if items else q
    resp = q.get("response") or {}
    answer = (resp.get("answer") if isinstance(resp, dict) else str(resp)) or \
             "(RAM returned no answer — check the agent's log in RAM)"

    trace = await get_trace(qid)
    citations = []
    for rc in trace["retrievalCalls"]:
        for ch in rc.get("chunks", [])[:3]:
            citations.append(ch)
    return {
        "messageId": qid, "answerEn": answer, "answerAr": answer,
        "traceId": qid, "blocked": False, "escalationId": None,
        "activity": [{"agent": "resolution", "labelEn": f"SAS RAM agent '{RAM_AGENT_NAME}' "
                      f"({len(trace['toolCalls'])} tool, {len(trace['llmCalls'])} LLM, "
                      f"{len(trace['retrievalCalls'])} retrieval calls)", "labelAr": ""}],
        "citations": citations, "sentiment": {"score": 0.2, "label": "neutral"},
        "stage": "live", "suggestions": [], "caseId": None, "triage": None, "live": True,
    }


async def get_trace(query_id: str) -> dict:
    flt = {"filter": f"eq(parentQueryId,'{query_id}')", "limit": 100}
    tool, llm, ret = await asyncio.gather(
        _req("GET", "/toolCalls", params=flt),
        _req("GET", "/llmCalls", params=flt),
        _req("GET", "/retrievalCalls", params=flt),
        return_exceptions=True)

    def items(x):
        return x.get("items", []) if isinstance(x, dict) else []

    def chunks_of(rc):
        out = []
        for ch in rc.get("retrievedChunks") or rc.get("chunks") or []:
            out.append({"docId": ch.get("documentName") or ch.get("docId", "?"),
                        "title": ch.get("documentName", ""), "article": "",
                        "page": ch.get("pageNumber") or ch.get("page", ""),
                        "score": ch.get("score", 0),
                        "textPreview": (ch.get("content") or ch.get("text", ""))[:260],
                        "textPreviewAr": (ch.get("content") or ch.get("text", ""))[:260]})
        return out

    return {
        "traceId": query_id, "queryId": query_id, "agent": f"SAS RAM · {RAM_AGENT_NAME}",
        "channel": "live", "prompt": "", "answerPreview": "", "status": "completed",
        "startedAt": 0, "ms": 0, "costUSD": 0.0, "guardrails": [],
        "toolCalls": [{"id": t.get("id", ""), "tool": t.get("toolName") or t.get("name", "?"),
                       "server": t.get("serverName", "mcp"), "args": t.get("input") or t.get("arguments"),
                       "result": t.get("output") or t.get("result"), "ms": t.get("durationMs", 0),
                       "status": "ok"} for t in items(tool)],
        "llmCalls": [{"id": l.get("id", ""), "model": l.get("model", "?"),
                      "purpose": l.get("purpose", "llm"),
                      "promptPreview": str(l.get("prompt", ""))[:300],
                      "completionPreview": str(l.get("completion", ""))[:300],
                      "promptTokens": l.get("promptTokens", 0),
                      "completionTokens": l.get("completionTokens", 0),
                      "costUSD": l.get("cost", 0) or 0, "ms": l.get("durationMs", 0)} for l in items(llm)],
        "retrievalCalls": [{"id": r.get("id", ""), "collection": r.get("collectionName", "?"),
                            "query": r.get("query", ""), "chunks": chunks_of(r),
                            "ms": r.get("durationMs", 0)} for r in items(ret)],
    }


async def health() -> dict:
    if not sas_chat_enabled():
        return {"enabled": False}
    try:
        await _resolve_agent_id()
        return {"enabled": True, "ram": RAM_API_URL, "agent": RAM_AGENT_NAME, "ok": True}
    except Exception as e:  # surface the reason, keep the app up
        return {"enabled": True, "ram": RAM_API_URL, "agent": RAM_AGENT_NAME, "ok": False,
                "error": str(e)[:300]}

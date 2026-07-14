"""The three MoCE agents as real Claude agentic loops — no RAM.

Same observable surface as the RAM proxy (async query records, tool/LLM/
retrieval traces, sessions), so the frontend is untouched: the dropdown
lists these agents, the live activity feed shows their real tool calls, and
Query Details shows real token usage.

  MoCE Document Processing  — reads scanned documents (tesseract OCR tools)
  MoCE Knowledge & Policy   — grounded policy answers from knowledge_base/
  MoCE Customer Resolution  — records + policy + documents + the PUBLISHED
                              decision flow on SAS Viya (score_data via the
                              sas-mcp-server MCP)

Environment:
  ANTHROPIC_API_KEY   required — powers the agents
  ANTHROPIC_MODEL     default claude-opus-4-8
  (SAS_MCP_URL / DECISION_MODULE_ID … — see services/viya_decision.py)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

from services import citizens, doc_tools, knowledge, viya_decision

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")
MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096"))
MAX_LOOP = 12
_PRICES = {"claude-opus-4-8": (5.0, 25.0), "claude-opus-4-7": (5.0, 25.0),
           "claude-fable-5": (10.0, 50.0), "claude-sonnet-5": (3.0, 15.0),
           "claude-sonnet-4-6": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0)}

_client = None
QUERIES: dict[str, dict] = {}
SESSIONS: dict[str, dict] = {}
FILES: dict[str, tuple[bytes, str, str]] = {}   # shared with the router (uploads)


def enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _anthropic():
    global _client
    if _client is None:
        from anthropic import AsyncAnthropic
        _client = AsyncAnthropic()
    return _client


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


# ─── Tool schemas ────────────────────────────────────────────────────

TOOL_OCR = {
    "name": "ocr_document",
    "description": "Read a scanned document. Pass the file_id from the query's "
                   "'Attached scanned document' block (preferred), or an image_url. "
                   "Returns the OCR text, mean word confidence (0-100), and any "
                   "low-confidence words — flag those for human verification instead "
                   "of guessing. languages: 'ara', 'eng' or 'ara+eng' (default).",
    "input_schema": {"type": "object", "properties": {
        "file_id": {"type": "string"}, "image_url": {"type": "string"},
        "languages": {"type": "string"}}},
}
TOOL_EXTRACT = {
    "name": "extract_fields",
    "description": "Extract structured fields from OCR'd text: Emirates ID, IBAN "
                   "(OCR-confusion corrected), AED amounts, dates, UAE phones, emails. "
                   "Pattern-based — every value exists verbatim in the text.",
    "input_schema": {"type": "object", "properties": {"text": {"type": "string"}},
                     "required": ["text"]},
}
TOOL_CLASSIFY = {
    "name": "classify_document",
    "description": "Classify OCR'd text into a document type (salary_certificate, "
                   "emirates_id_card, iban_letter, family_book, utility_bill, other).",
    "input_schema": {"type": "object", "properties": {"text": {"type": "string"}},
                     "required": ["text"]},
}
TOOL_SEARCH = {
    "name": "search_policy",
    "description": "Semantic search over the MoCE Policy Library (Inflation Allowance "
                   "operations manual, verification SOP, programme pages). Returns "
                   "passages with filename + page — cite them for every rule you state.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                     "required": ["query"]},
}
TOOL_CITIZEN = {
    "name": "get_citizen_record",
    "description": "Look up a citizen's registry record (benefit status + reason, "
                   "monthly amount, months suspended, income verification validity) "
                   "by Emirates ID.",
    "input_schema": {"type": "object", "properties": {"emirates_id": {"type": "string"}},
                     "required": ["emirates_id"]},
}
TOOL_DECIDE = {
    "name": "execute_decision_flow",
    "description": "Execute the PUBLISHED Inflation Allowance decision flow on SAS "
                   "Intelligent Decisioning (via SAS Viya). This is the ONLY authority "
                   "on eligibility, reinstatement, back-pay and approval routing — "
                   "never decide these yourself. Quote its outputs exactly.",
    "input_schema": {"type": "object", "properties": {
        "monthly_income_aed": {"type": "number", "description": "verified gross monthly income"},
        "nationality": {"type": "string", "description": "e.g. UAE"},
        "family_size": {"type": "number"},
        "verified_within_months": {"type": "number", "description": "months since income verification; 0 = just verified"},
        "suspension_reason": {"type": "string", "description": "e.g. INCOME_VERIFICATION_EXPIRED, or NONE"},
        "months_suspended": {"type": "number"},
        "monthly_amount_aed": {"type": "number", "description": "the benefit's monthly amount (2350 standard)"}},
        "required": ["monthly_income_aed", "nationality", "family_size",
                     "verified_within_months", "suspension_reason",
                     "months_suspended", "monthly_amount_aed"]},
}


# ─── Agent definitions ───────────────────────────────────────────────

_STYLE = ("Answer in the language of the user's message (Arabic or English). Be warm and "
          "concise; use Markdown bold for key figures. Never mention internal tool or "
          "system names — describe actions in plain terms.")

AGENTS = {
    "agent-doc-processing": {
        "id": "agent-doc-processing", "name": "MoCE Document Processing",
        "description": "Reads scanned citizen documents: OCR (Arabic + English), type classification, field extraction.",
        "tools": [TOOL_OCR, TOOL_CLASSIFY, TOOL_EXTRACT],
        "system": (
            "You are the document processing agent of the UAE Ministry of Community "
            "Empowerment. When the query includes an 'Attached scanned document' block, "
            "always work in this order: ocr_document (with its file_id) → "
            "classify_document → extract_fields. Then report: document type, who it "
            "belongs to, the key values (amounts, dates, IDs) quoted EXACTLY as the "
            "tools returned them, and the OCR mean confidence. If meanConfidence is "
            "below 90 or a financial field appears among the low-confidence words, say "
            "the document needs human verification per SOP-DOC-009 instead of treating "
            "the value as final. If there is no attached document, explain what you can "
            "read (salary certificates, Emirates ID cards, IBAN letters, family books, "
            "scans in Arabic or English) and ask for one. " + _STYLE),
    },
    "agent-knowledge": {
        "id": "agent-knowledge", "name": "MoCE Knowledge & Policy",
        "description": "Answers Inflation Allowance / Social Welfare Programme policy questions with citations.",
        "tools": [TOOL_SEARCH],
        "system": (
            "You are the policy knowledge agent of the UAE Ministry of Community "
            "Empowerment for the Social Welfare Programme and its Inflation Allowance. "
            "ALWAYS call search_policy before answering, and answer ONLY from the "
            "retrieved passages, citing document and article for every rule (e.g. "
            "POL-2024-017 Art. 7.1). If the passages don't answer the question, say so "
            "plainly — never fill gaps from general knowledge. Key topics: eligibility "
            "and the AED 25,000 income threshold (Art 4.2 / Schedule B), required "
            "documents (Art 5.3), suspension vs termination (Art 6.2), reinstatement "
            "and back-pay (Art 7.1), two-stage approval (Art 8.4). " + _STYLE),
    },
    "agent-resolution": {
        "id": "agent-resolution", "name": "MoCE Customer Resolution",
        "description": "Investigates benefit issues end-to-end: records, policy, documents, and the published decision flow on SAS Viya.",
        "tools": [TOOL_CITIZEN, TOOL_SEARCH, TOOL_OCR, TOOL_CLASSIFY, TOOL_EXTRACT, TOOL_DECIDE],
        "system": (
            "You are the customer resolution agent of the UAE Ministry of Community "
            "Empowerment, handling Inflation Allowance enquiries and complaints.\n\n"
            "Method — always in this order:\n"
            "1. General policy questions → search_policy, answer with citations; do NOT "
            "look up personal records for general questions.\n"
            "2. A personal issue (payment stopped, wrong amount) → get_citizen_record "
            "first (ask for the Emirates ID if missing), then search_policy for the "
            "governing rule, and explain the cause with the citation.\n"
            "3. If resolving needs a document (expired income verification needs a fresh "
            "salary certificate ≤90 days old), ask for it. When the query includes an "
            "'Attached scanned document' block, read it via ocr_document (file_id) → "
            "classify_document → extract_fields, and use the verified income from it.\n"
            "4. Eligibility, reinstatement, back-pay and approval routing are decided "
            "ONLY by execute_decision_flow — the published rules on SAS Intelligent "
            "Decisioning. Call it with the citizen's real values (verified income, "
            "family size, suspension reason, months suspended, monthly amount; "
            "verified_within_months=0 right after a document is verified). Quote its "
            "outputs exactly: outcome, action, backpayaed, approvalpath. approvalpath "
            "TWO_STAGE means a Social Worker then a Social Auditor must approve the "
            "back-payment (48h SLA) — you cannot release money yourself.\n"
            "5. State amounts, dates and entitlements ONLY if they came from a record, "
            "a document reading, a policy passage, or the decision flow. If you cannot "
            "verify something (e.g. a bonus with no record), say so and refer the "
            "citizen to the contact centre — never guess.\n\n" + _STYLE),
    },
}


# ─── Tool execution ──────────────────────────────────────────────────

async def _exec_tool(name: str, args: dict, rec: dict) -> dict:
    if name == "ocr_document":
        if args.get("file_id"):
            entry = FILES.get(args["file_id"])
            if not entry:
                return {"error": "unknown or expired file_id"}
            data = entry[0]
        elif args.get("image_url"):
            data = await asyncio.to_thread(doc_tools.fetch_image, args["image_url"])
        else:
            return {"error": "pass file_id (from the attachment block) or image_url"}
        return await asyncio.to_thread(doc_tools.ocr_image, data, args.get("languages", ""))

    if name == "extract_fields":
        return doc_tools.extract_fields(args.get("text", ""))

    if name == "classify_document":
        return doc_tools.classify_document(args.get("text", ""))

    if name == "search_policy":
        chunks = knowledge.search(args.get("query", ""))
        rec["trace"]["retrievalCalls"].append({
            "id": uuid.uuid4().hex, "parentQueryId": rec["id"],
            "input": {"query": args.get("query", ""), "k": 4},
            "output": {"documents": len(chunks)}})
        for c in chunks:  # citations for the answer bubble
            key = (c["filename"], c["page"])
            if key not in {(x["metadata"]["filename"], x["metadata"].get("page"))
                           for x in rec["context"]}:
                rec["context"].append({"pageContent": c["text"],
                                       "metadata": {"filename": c["filename"], "page": c["page"]}})
        return {"passages": chunks}

    if name == "get_citizen_record":
        c = citizens.lookup(args.get("emirates_id", ""))
        return c if c else {"error": "no citizen found for that Emirates ID"}

    if name == "execute_decision_flow":
        return await asyncio.to_thread(viya_decision.execute, **args)

    return {"error": f"unknown tool {name}"}


# ─── The agentic loop ────────────────────────────────────────────────

async def _run_agent(rec: dict, agent: dict, messages: list) -> str:
    client = _anthropic()
    in_rate, out_rate = _PRICES.get(MODEL, (5.0, 25.0))
    for _ in range(MAX_LOOP):
        t0 = time.time()
        resp = await client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=agent["system"],
            messages=messages, tools=agent["tools"], thinking={"type": "adaptive"})
        pt, ct = resp.usage.input_tokens, resp.usage.output_tokens
        rec["usage"]["llmPromptTokens"] += pt
        rec["usage"]["llmCompletionTokens"] += ct
        rec["usage"]["llmTotalTokens"] += pt + ct
        rec["usage"]["llmTotalCost"] = round(
            rec["usage"]["llmTotalCost"] + (pt * in_rate + ct * out_rate) / 1_000_000, 6)
        text_preview = next((b.text for b in resp.content if b.type == "text"), "")
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        rec["trace"]["llmCalls"].append({
            "id": uuid.uuid4().hex, "parentQueryId": rec["id"],
            "input": {"modelName": MODEL, "modelProvider": "anthropic",
                      "content": str(messages[-1])[:400]},
            "output": {"response": (text_preview or f"[tool_use: {', '.join(t.name for t in tool_uses)}]")[:400]},
            "promptTokens": pt, "completionTokens": ct,
            "promptCost": round(pt * in_rate / 1_000_000, 6),
            "completionCost": round(ct * out_rate / 1_000_000, 6),
            "durationMs": int((time.time() - t0) * 1000)})

        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "pause_turn":
            continue
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text").strip()

        results = []
        for block in tool_uses:
            t1 = time.time()
            try:
                out = await _exec_tool(block.name, block.input or {}, rec)
                is_error = isinstance(out, dict) and bool(out.get("error"))
            except Exception as e:
                out, is_error = {"error": f"{type(e).__name__}: {str(e)[:300]}"}, True
            rec["trace"]["toolCalls"].append({
                "id": uuid.uuid4().hex, "parentQueryId": rec["id"],
                "toolName": block.name, "input": block.input or {},
                "output": {"content": [json.dumps(out, ensure_ascii=False, default=str)[:2000]],
                           "isError": is_error},
                "durationMs": int((time.time() - t1) * 1000)})
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": json.dumps(out, ensure_ascii=False, default=str)})
        messages.append({"role": "user", "content": results})
    return "I could not complete this request — please try again."


async def _process(query_id: str):
    rec = QUERIES[query_id]
    agent = AGENTS[rec["targetId"]["agentId"]]
    session = SESSIONS[rec["querySessionId"]]
    messages = session["history"]
    checkpoint = len(messages)  # roll back on failure — never leave a dangling tool_use
    messages.append({"role": "user", "content": rec["content"]})
    try:
        answer = await _run_agent(rec, agent, messages)
        rec["response"] = {"answer": answer, "context": rec["context"],
                           "toolCalls": [{"toolName": t["toolName"], "input": t["input"]}
                                         for t in rec["trace"]["toolCalls"]],
                           "usageMetadata": rec["usage"]}
        rec["state"] = "completed"
    except Exception as e:
        del messages[checkpoint:]
        rec["errorCode"] = 1
        rec["errorText"] = f"{type(e).__name__}: {str(e)[:300]}"
        rec["state"] = "failed"
    session["updateTimestamp"] = _now()


# ─── Public API (mirrors the RAM proxy's shapes) ─────────────────────

def list_agents() -> list[dict]:
    return [{"id": a["id"], "name": a["name"], "description": a["description"]}
            for a in AGENTS.values()]


def submit(content: str, agent_id: str | None, session_id: str | None) -> dict:
    if not enabled():
        raise RuntimeError("ANTHROPIC_API_KEY is not set — the agents cannot run.")
    if agent_id not in AGENTS:
        raise ValueError("Pick one of the three agents from the dropdown.")
    sid = session_id if session_id in SESSIONS else None
    if sid is None:
        sid = uuid.uuid4().hex
        SESSIONS[sid] = {"id": sid, "title": content[:60], "agentId": agent_id,
                         "insertTimestamp": _now(), "updateTimestamp": _now(),
                         "history": [], "queries": []}
    qid = uuid.uuid4().hex
    QUERIES[qid] = {
        "id": qid, "querySessionId": sid, "content": content, "origin": "user",
        "target": "agent", "targetId": {"agentId": agent_id},
        "state": "running", "errorCode": 0, "errorText": None, "response": None,
        "context": [], "usage": {"llmPromptTokens": 0, "llmCompletionTokens": 0,
                                 "llmTotalTokens": 0, "llmTotalCost": 0.0},
        "trace": {"toolCalls": [], "llmCalls": [], "retrievalCalls": []},
        "createdAt": _now(),
    }
    SESSIONS[sid]["queries"].append(qid)
    asyncio.get_running_loop().create_task(_process(qid))
    return {"queryId": qid, "querySessionId": sid, "pollInterval": 1.5, "timeout": 300}


def _normalize(rec: dict) -> dict:
    resp = rec.get("response") or {}
    return {"queryId": rec["id"], "querySessionId": rec["querySessionId"],
            "content": rec["content"], "answer": resp.get("answer"),
            "context": resp.get("context") or [], "toolCalls": resp.get("toolCalls") or [],
            "usage": resp.get("usageMetadata") or {}, "target": "agent",
            "targetId": rec["targetId"], "origin": "user",
            "errorCode": rec["errorCode"], "errorText": rec["errorText"]}


def status(query_id: str) -> dict:
    rec = QUERIES.get(query_id)
    if not rec:
        raise KeyError(query_id)
    if rec["state"] == "running":
        return {"done": False}
    return {"done": True, "result": _normalize(rec)}


def trace(query_id: str) -> dict:
    rec = QUERIES.get(query_id)
    if not rec:
        return {"toolCalls": [], "llmCalls": [], "retrievalCalls": []}
    return rec["trace"]


def raw(query_id: str) -> dict:
    rec = QUERIES.get(query_id)
    if not rec:
        raise KeyError(query_id)
    return {k: v for k, v in rec.items() if k != "trace"} | {"trace": rec["trace"]}


def list_sessions() -> list[dict]:
    return [{"id": s["id"], "title": s["title"], "agentId": s["agentId"],
             "insertTimestamp": s["insertTimestamp"], "updateTimestamp": s["updateTimestamp"]}
            for s in sorted(SESSIONS.values(), key=lambda s: s["updateTimestamp"], reverse=True)]


def session_queries(session_id: str) -> list[dict]:
    s = SESSIONS.get(session_id)
    if not s:
        return []
    return [_normalize(QUERIES[qid]) for qid in s["queries"] if qid in QUERIES]


def health() -> dict:
    key = enabled()
    return {"status": "ok" if key else "unconfigured", "mode": "live",
            "ramUrl": "(no RAM — Claude agents + SAS Viya direct)",
            "auth": "anthropic", "authenticated": key,
            "model": MODEL if key else None,
            "knowledgeBase": knowledge.stats(),
            "sasViya": viya_decision.health() if key else {"skipped": True}}

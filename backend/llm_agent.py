"""Real Claude-powered Customer Resolution Agent.

Activated by setting ANTHROPIC_API_KEY. The scripted engine in
engine/resolution.py stays as the offline fallback; with a key present, every
chat turn runs a genuine agentic loop against the Claude API:

  classify_contact (triage) → investigate via tools → grounded answer
  → deterministic verify_claims gate → (repair + escalate on BLOCK)

The tools operate on the same in-memory registries the rest of the demo uses,
and `run_eligibility_flow` goes through engine/decisioning.execute_flow — so
when SAS_MCP_URL is configured the business rules execute on real
SAS Intelligent Decisioning (see sas_id.py / docs/SAS_ID_SETUP.md).

Environment:
  ANTHROPIC_API_KEY     enables this module
  ANTHROPIC_MODEL       default: claude-opus-4-8
  ANTHROPIC_MAX_TOKENS  per API call (default: 4096, includes thinking)
"""

import asyncio
import json
import os
import re
import time

from store import store, next_id
from engine import knowledge
from engine.tracer import Trace

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")
MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096"))
MAX_LOOP = 10          # API round-trips per citizen message (incl. repair)
_PRICES = {            # USD per MTok (input, output) — for the governance view
    "claude-opus-4-8": (5.0, 25.0), "claude-opus-4-7": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0), "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0),
}

_client = None


def llm_chat_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _get_client():
    global _client
    if _client is None:
        from anthropic import AsyncAnthropic
        _client = AsyncAnthropic()
    return _client


# ------------------------------------------------------------------- tools

TOOLS = [
    {"name": "classify_contact",
     "description": "Record the triage decision for the citizen's latest message. "
                    "MUST be your first tool call for every new citizen message. "
                    "QUERY = general question answerable from policy (no case is opened); "
                    "COMPLAINT = a personal service failure (payment stopped, wrong amount) "
                    "that needs investigation; SERVICE_REQUEST = asks us to do something new.",
     "input_schema": {"type": "object", "properties": {
         "type": {"type": "string", "enum": ["QUERY", "COMPLAINT", "SERVICE_REQUEST"]},
         "confidence": {"type": "number", "description": "0-1"},
         "reason": {"type": "string", "description": "one short sentence"}},
         "required": ["type", "confidence", "reason"]}},
    {"name": "get_citizen_profile",
     "description": "Fetch the authenticated citizen's registry profile (family size, "
                    "employment, income-verification validity).",
     "input_schema": {"type": "object", "properties": {
         "emiratesId": {"type": "string"}}, "required": ["emiratesId"]}},
    {"name": "get_benefit_status",
     "description": "Fetch the citizen's benefit enrolments with status, status reason and "
                    "monthly amounts.",
     "input_schema": {"type": "object", "properties": {
         "emiratesId": {"type": "string"}}, "required": ["emiratesId"]}},
    {"name": "get_payment_history",
     "description": "Fetch the citizen's benefit payment history (last 6 months).",
     "input_schema": {"type": "object", "properties": {
         "emiratesId": {"type": "string"}}, "required": ["emiratesId"]}},
    {"name": "retrieve_policy",
     "description": "Semantic search over the MoCE Policy Library. Returns policy chunks "
                    "with citations (docId, article, page). Answer policy questions ONLY "
                    "from these chunks.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"}}, "required": ["query"]}},
    {"name": "run_eligibility_flow",
     "description": "Execute the Inflation Allowance eligibility decision flow on SAS "
                    "Intelligent Decisioning (published business rules). This is the ONLY "
                    "authoritative source for eligibility outcomes — never decide "
                    "eligibility yourself.",
     "input_schema": {"type": "object", "properties": {
         "monthlyIncomeAED": {"type": "number", "description": "verified gross monthly income"},
         "verifiedWithinMonths": {"type": "number", "description": "months since income verification (0 = just verified)"}},
         "required": ["monthlyIncomeAED"]}},
    {"name": "request_document_upload",
     "description": "Ask the citizen to upload a document through the portal (renders an "
                    "upload control). Use when income re-verification needs a fresh salary "
                    "certificate.",
     "input_schema": {"type": "object", "properties": {
         "docType": {"type": "string", "enum": ["salary_certificate"]},
         "reason": {"type": "string"}}, "required": ["docType"]}},
    {"name": "reinstate_benefit",
     "description": "Reinstate a suspended benefit, effective immediately. Within your "
                    "autonomous authority ONLY after run_eligibility_flow returned ELIGIBLE "
                    "in this conversation and the citizen confirmed. Sends the citizen an SMS.",
     "input_schema": {"type": "object", "properties": {
         "emiratesId": {"type": "string"}, "reason": {"type": "string"}},
         "required": ["emiratesId", "reason"]}},
    {"name": "create_backpay_case",
     "description": "Open a two-stage human-approval case (Social Worker → Social Auditor) "
                    "for retroactive payment of withheld instalments. Required by policy for "
                    "ANY back-payment — you cannot release money yourself.",
     "input_schema": {"type": "object", "properties": {
         "emiratesId": {"type": "string"},
         "backpayAED": {"type": "number"},
         "months": {"type": "integer"},
         "rationale": {"type": "string"}},
         "required": ["emiratesId", "backpayAED", "months", "rationale"]}},
    {"name": "get_case_status",
     "description": "Look up an approval case by id (or the session's current case if no id "
                    "is given).",
     "input_schema": {"type": "object", "properties": {
         "caseId": {"type": "string"}}}},
    {"name": "escalate_to_human",
     "description": "Refer the question to a contact-centre specialist. Use whenever the "
                    "citizen asks about an entitlement, bonus or scheme you cannot verify in "
                    "tool results.",
     "input_schema": {"type": "object", "properties": {
         "reason": {"type": "string"}, "question": {"type": "string"}},
         "required": ["reason", "question"]}},
]

_ACTIVITY = {
    "get_citizen_profile": ("resolution", "Verified identity via UAEPass — registry profile retrieved",
                            "التحقق من الهوية عبر الهوية الرقمية — استرجاع الملف"),
    "get_benefit_status": ("resolution", "Retrieved benefit record", "استرجاع سجل المنفعة"),
    "get_payment_history": ("resolution", "Retrieved payment history", "استرجاع سجل الدفعات"),
    "request_document_upload": ("resolution", "Requested salary certificate upload", "طلب رفع شهادة الراتب"),
    "reinstate_benefit": ("resolution", "Executed: reinstate allowance (within authority limit)",
                          "تنفيذ: إعادة صرف العلاوة (ضمن حدود الصلاحية)"),
    "escalate_to_human": ("guard", "Escalated to contact-centre specialist", "تصعيد إلى مختص مركز الاتصال"),
}


# ------------------------------------------------------------ tool execution

def _fact_numbers(value, facts: set):
    """Collect every number from a tool result into the verified-fact set."""
    if isinstance(value, dict):
        for k, v in value.items():
            _fact_numbers(v, facts)
            if isinstance(v, (int, float)) and "monthly" in k.lower() and v > 0:
                for m in range(1, 7):     # derived: n months × monthly amount
                    facts.add(round(v * m, 2))
    elif isinstance(value, list):
        for v in value:
            _fact_numbers(v, facts)
    elif isinstance(value, bool):
        pass
    elif isinstance(value, (int, float)):
        facts.add(round(float(value), 2))
    elif isinstance(value, str):
        for m in re.findall(r"\d[\d,]*(?:\.\d+)?", value):
            try:
                facts.add(round(float(m.replace(",", "")), 2))
            except ValueError:
                pass


async def _exec_tool(name: str, args: dict, session: dict, citizen: dict,
                     turn: dict) -> dict:
    """Run one tool against the demo registries; record activity/citations."""
    if name in _ACTIVITY:
        agent, en, ar = _ACTIVITY[name]
        turn["activity"].append({"agent": agent, "labelEn": en, "labelAr": ar})

    if name == "classify_contact":
        turn["triage"] = {"type": args.get("type", "QUERY"),
                          "confidence": round(float(args.get("confidence", 0.9)), 2),
                          "detailEn": args.get("reason", ""), "detailAr": args.get("reason", "")}
        turn["activity"].insert(0, {"agent": "guard",
                                    "labelEn": f"Triage: {turn['triage']['type']} "
                                               f"({turn['triage']['confidence']:.0%}) — {args.get('reason', '')}",
                                    "labelAr": f"الفرز: {turn['triage']['type']}"})
        return {"recorded": True}

    if name == "get_citizen_profile":
        return {"nameEn": citizen["nameEn"], "nameAr": citizen["nameAr"],
                "emiratesId": citizen["emiratesId"], "nationality": citizen["nationality"],
                "emirate": citizen["emirate"], "familySize": citizen["familySize"],
                "employment": citizen["employment"], "phone": citizen["phone"]}

    if name == "get_benefit_status":
        return {"benefits": citizen["benefits"]}

    if name == "get_payment_history":
        return {"payments": citizen["payments"]}

    if name == "retrieve_policy":
        chunks = knowledge.retrieve(args.get("query", ""))
        turn["trace"].retrieval("MoCE Policy Library", args.get("query", ""), chunks, ms=60)
        turn["citations"].extend(c for c in chunks
                                 if c["article"] not in {x["article"] for x in turn["citations"]})
        if chunks:
            turn["activity"].append({"agent": "knowledge",
                                     "labelEn": f"Retrieved {chunks[0]['docId']} {chunks[0]['article']} (cited)",
                                     "labelAr": f"استرجاع {chunks[0]['docId']} {chunks[0]['article']}"})
        return {"chunks": [{"docId": c["docId"], "article": c["article"], "page": c["page"],
                            "title": c["title"], "text": c["textPreview"],
                            "textAr": c["textPreviewAr"]} for c in chunks]}

    if name == "run_eligibility_flow":
        from engine import decisioning
        flow = await asyncio.to_thread(decisioning.execute_flow, {
            "monthlyIncomeAED": args.get("monthlyIncomeAED", 0),
            "nationality": citizen["nationality"],
            "familySize": citizen["familySize"],
            "verifiedWithinMonths": args.get("verifiedWithinMonths", 0),
        })
        turn["activity"].append({"agent": "knowledge",
                                 "labelEn": f"Decision flow → {flow['outcome']} · {flow.get('executedOn', '')}",
                                 "labelAr": f"مسار القرار ← {flow['outcome']}"})
        if flow["outcome"] == "ELIGIBLE" and session["stage"] not in ("resolved",):
            session["stage"] = "resolution_proposed"
        return {"outcome": flow["outcome"], "confidence": flow["confidence"],
                "version": flow["version"], "thresholdAED": flow["threshold"],
                "executedOn": flow.get("executedOn"),
                "ruleFires": [{"ruleId": f["ruleId"], "passed": f["passed"], "detail": f["detail"]}
                              for f in flow["ruleFires"]]}

    if name == "request_document_upload":
        session["stage"] = "awaiting_doc"
        return {"status": "upload control shown to citizen", "docType": args.get("docType")}

    if name == "reinstate_benefit":
        ben = citizen["benefits"][0]
        ben["status"] = "ACTIVE"
        ben["statusReason"] = "REINSTATED_AFTER_VERIFICATION"
        store.notifications.append({
            "at": "now", "to": citizen["nameEn"], "channel": "SMS",
            "textEn": "MoCE: your Inflation Allowance has been reinstated effective immediately.",
            "textAr": "وزارة تمكين المجتمع: تمت إعادة صرف علاوة غلاء المعيشة اعتباراً من الآن.",
        })
        turn["activity"].append({"agent": "resolution", "labelEn": "SMS notification sent",
                                 "labelAr": "إرسال إشعار نصي"})
        return {"status": "ACTIVE", "effective": "immediately",
                "monthlyAED": ben["monthlyAmountAED"], "smsSent": True}

    if name == "create_backpay_case":
        from engine import cases as case_engine
        months = int(args.get("months", 3))
        monthly = citizen["benefits"][0]["monthlyAmountAED"] or 2350
        rec = {"recommendation": "REINSTATE_WITH_BACKPAY",
               "rationale": args.get("rationale", ""),
               "evidence": [{"docId": c["docId"], "article": c["article"], "page": c["page"],
                             "title": c["title"]} for c in turn["citations"]],
               "confidence": 0.93, "risk": "LOW",
               "decisionFlow": {"flow": store.ruleset["flowName"],
                                "version": store.ruleset["publishedVersion"], "ruleFires": []},
               "financialImpact": {"monthlyAED": monthly,
                                   "backpayAED": float(args.get("backpayAED", months * monthly)),
                                   "backpayMonths": months}}
        case = case_engine.create_case(session["sessionId"], citizen, rec,
                                       "Benefit Reinstatement — Back-pay Release")
        session["caseId"] = case["caseId"]
        session["stage"] = "resolved"
        turn["activity"].append({"agent": "case",
                                 "labelEn": f"Case {case['caseId']} created → two-stage approval",
                                 "labelAr": f"إنشاء الحالة {case['caseId']} ← اعتماد على مرحلتين"})
        return {"caseId": case["caseId"], "status": case["status"], "priority": case["priority"],
                "slaHours": case["slaHours"],
                "stages": [s["role"] for s in case["stages"]]}

    if name == "get_case_status":
        cid = args.get("caseId") or session.get("caseId")
        case = next((c for c in store.cases if c["caseId"] == cid), None)
        if not case:
            return {"error": "no case found for this citizen"}
        return {"caseId": case["caseId"], "status": case["status"], "priority": case["priority"],
                "slaHours": case["slaHours"],
                "stages": [{"stage": s["stage"], "role": s["role"], "decision": s["decision"]}
                           for s in case["stages"]]}

    if name == "escalate_to_human":
        esc = {"escalationId": next_id("ESC"), "sessionId": session["sessionId"],
               "citizen": citizen["nameEn"], "channel": session["channel"],
               "reason": args.get("reason", ""), "question": args.get("question", ""),
               "traceId": turn["trace"].rec["traceId"], "status": "OPEN",
               "sentiment": session["sentiment"]["label"]}
        store.escalations.append(esc)
        turn["escalationId"] = esc["escalationId"]
        return {"escalationId": esc["escalationId"], "status": "OPEN",
                "note": "a specialist will contact the citizen"}

    return {"error": f"unknown tool {name}"}


# --------------------------------------------------------- verify_claims gate

def _verify_claims(answer: str, facts: set) -> tuple[str, list]:
    """Deterministic hallucination gate: every currency amount in the answer
    must be traceable to a tool result from this session."""
    claims, seen = [], set()
    for m in re.finditer(
            r"(?:AED|درهم(?:اً|ًا|ا)?)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:AED|درهم(?:اً|ًا|ا)?|dirhams?)",
            answer):
        raw = m.group(1) or m.group(2)
        try:
            val = round(float(raw.replace(",", "")), 2)
        except ValueError:
            continue
        if val < 300 or val in seen:  # ignore small counts/percentages, dedupe
            continue
        seen.add(val)
        claims.append({"claim": f"AED {raw}", "verified": val in facts,
                       "source": "tool result" if val in facts else None})
    verdict = "BLOCK" if any(not c["verified"] for c in claims) else "PASS"
    return verdict, claims


# ------------------------------------------------------------------ the loop

def _system_prompt(session: dict, citizen: dict, lang: str) -> str:
    language = "Modern Standard Arabic" if lang == "ar" else "English"
    channel = ("the MoCE citizen portal (authenticated via UAEPass)"
               if session["channel"] == "citizen" else "the MoCE contact-centre agent console")
    return f"""You are the Customer Resolution Agent of the UAE Ministry of Community \
Empowerment (MoCE), serving a citizen through {channel}.

Authenticated citizen: {citizen['nameEn']} / {citizen['nameAr']} — Emirates ID \
{citizen['emiratesId']}. Today is 2026-07-13. The flagship programme is the Inflation \
Allowance (علاوة غلاء المعيشة).

OPERATING RULES
1. TRIAGE FIRST — your first tool call for every new citizen message is classify_contact. \
Many inbound complaints are really general questions (QUERY): answer those straight from \
retrieve_policy with citations and do NOT open cases or pull personal records unless needed.
2. COMPLAINT about payments or benefit status → investigate before answering: \
get_benefit_status and get_payment_history, plus retrieve_policy for the governing rules.
3. Eligibility is decided ONLY by run_eligibility_flow (SAS Intelligent Decisioning). \
Never conclude eligibility yourself.
4. If a suspension is caused by expired income verification, use request_document_upload \
to ask for a fresh salary certificate (issued within 90 days). After a document is verified, \
re-run run_eligibility_flow with the verified income before proposing anything.
5. AUTHORITY LIMITS — reinstating a suspended benefit is within your autonomous authority \
once the flow returns ELIGIBLE and the citizen explicitly confirms. Releasing money \
(back-pay) is NEVER within your authority: use create_backpay_case (two-stage human \
approval: Social Worker then Social Auditor, SLA 48h). Propose first, execute only after \
the citizen agrees.
6. GROUNDING (verify_claims policy) — every amount, date, and entitlement you state must \
appear in a tool result from this conversation. If the citizen asks about a bonus, scheme \
or entitlement you cannot verify (for example an Eid bonus), say plainly that you cannot \
verify it, call escalate_to_human, and NEVER guess or invent amounts.

STYLE
Respond in {language} only. Be warm, concise (2–6 short sentences or a short list), use \
Markdown bold for key figures and dates, never mention internal tool or system names — \
describe actions in citizen terms ("I checked your record…"). When citing policy, name the \
document and article (e.g. POL-2024-017 Art. 7.1)."""


async def _run_loop(messages: list, system: str, session: dict, citizen: dict,
                    turn: dict) -> str:
    client = _get_client()
    in_rate, out_rate = _PRICES.get(MODEL, (5.0, 25.0))
    for _ in range(MAX_LOOP):
        t0 = time.time()
        resp = await client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=system,
            messages=messages, tools=TOOLS, thinking={"type": "adaptive"})
        ms = int((time.time() - t0) * 1000)
        pt, ct = resp.usage.input_tokens, resp.usage.output_tokens
        text_preview = next((b.text for b in resp.content if b.type == "text"), "")
        tools_called = [b.name for b in resp.content if b.type == "tool_use"]
        turn["trace"].rec["llmCalls"].append({
            "id": next_id("LC"), "model": MODEL,
            "purpose": "agentic turn" + (f" → {', '.join(tools_called)}" if tools_called else " → final answer"),
            "promptPreview": str(messages[-1])[:300],
            "completionPreview": (text_preview or f"[tool_use: {', '.join(tools_called)}]")[:300],
            "promptTokens": pt, "completionTokens": ct,
            "costUSD": round((pt * in_rate + ct * out_rate) / 1_000_000, 6), "ms": ms})
        turn["trace"].rec["costUSD"] = round(
            turn["trace"].rec["costUSD"] + (pt * in_rate + ct * out_rate) / 1_000_000, 6)

        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "pause_turn":
            continue
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text").strip()

        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            t0 = time.time()
            try:
                out = await _exec_tool(block.name, block.input or {}, session, citizen, turn)
                status = "ok"
            except Exception as e:
                out, status = {"error": f"{type(e).__name__}: {str(e)[:200]}"}, "error"
            _fact_numbers(out, turn["facts"])
            turn["trace"].tool(block.name,
                               "sas-viya-mcp" if block.name == "run_eligibility_flow" else "moce-mcp-tools",
                               block.input or {}, out,
                               ms=int((time.time() - t0) * 1000), status=status)
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": json.dumps(out, ensure_ascii=False, default=str)})
        messages.append({"role": "user", "content": results})
    return "I could not complete this request — please try again or contact the service centre."


async def chat(session_id: str, text: str, lang: str = "en") -> dict:
    from engine import resolution
    session = store.sessions[session_id]
    citizen = store.citizens[session["citizenId"]]
    session["lang"] = lang
    resolution._sentiment(session, text)

    trace = Trace("Customer Resolution Agent (Claude)", session["channel"], text, session_id)
    turn = {"trace": trace, "activity": [], "citations": [], "triage": None,
            "escalationId": None, "facts": session.setdefault("llmFacts", set())}
    messages = session.setdefault("llmHistory", [])
    checkpoint = len(messages)  # roll back on API failure so history never ends
    messages.append({"role": "user", "content": text})  # with an unanswered tool_use
    system = _system_prompt(session, citizen, lang)

    try:
        answer = await _run_loop(messages, system, session, citizen, turn)
    except Exception:
        del messages[checkpoint:]
        raise

    verdict, claims = _verify_claims(answer, turn["facts"])
    blocked = False
    if verdict == "BLOCK":
        blocked = True
        unverified = [c["claim"] for c in claims if not c["verified"]]
        trace.guardrail("verify_claims", claims, "BLOCKED")
        store.hallucination_log.append({"traceId": trace.rec["traceId"], "claims": claims})
        store.metrics["hallucinationBlocks30d"] += 1
        if not turn["escalationId"]:
            esc = {"escalationId": next_id("ESC"), "sessionId": session_id,
                   "citizen": citizen["nameEn"], "channel": session["channel"],
                   "reason": f"verify_claims blocked draft: unverifiable {', '.join(unverified)}",
                   "question": text, "traceId": trace.rec["traceId"], "status": "OPEN",
                   "sentiment": session["sentiment"]["label"]}
            store.escalations.append(esc)
            turn["escalationId"] = esc["escalationId"]
        turn["activity"].append({
            "agent": "guard",
            "labelEn": f"verify_claims: {', '.join(unverified)} NOT traceable → draft BLOCKED, rewriting",
            "labelAr": "التحقق من الوقائع: مبالغ غير موثقة ← حظر المسودة وإعادة الصياغة"})
        messages.append({"role": "user", "content":
            f"[GUARDRAIL verify_claims — verdict BLOCK] The following amounts in your draft "
            f"are NOT traceable to any tool result: {', '.join(unverified)}. Rewrite your "
            f"answer now: state only verified amounts, say plainly which item you cannot "
            f"verify, and tell the citizen a specialist will confirm it (an escalation has "
            f"been opened). Do not repeat unverified figures."})
        answer = await _run_loop(messages, system, session, citizen, turn)
    else:
        trace.guardrail("verify_claims", claims, "PASS")
        turn["activity"].append({
            "agent": "guard",
            "labelEn": f"verify_claims: {len(claims)}/{len(claims)} amounts traced to records — PASS"
                       if claims else "verify_claims: no factual amount claims — PASS",
            "labelAr": "التحقق من الوقائع: جميع المبالغ موثقة"})

    trace.done(answer, status="blocked" if blocked else "completed")
    msg = {"messageId": next_id("MSG"), "answerEn": answer, "answerAr": answer,
           "traceId": trace.rec["traceId"], "blocked": blocked,
           "escalationId": turn["escalationId"],
           "activity": turn["activity"], "citations": turn["citations"],
           "sentiment": session["sentiment"], "stage": session["stage"],
           "suggestions": resolution._suggestions(session["stage"]),
           "caseId": session.get("caseId"), "triage": turn["triage"], "live": True}
    session["messages"].append(msg)
    return msg


def note_event(session_id: str, text_en: str):
    """Keep Claude's conversation history coherent when the document pipeline
    (or a case approval) injects an out-of-band agent message."""
    session = store.sessions.get(session_id)
    if session is None or "llmHistory" not in session:
        return
    session["llmHistory"].append({"role": "assistant", "content": text_en})
    # Numbers announced by the deterministic pipeline are verified facts too.
    _fact_numbers(text_en, session.setdefault("llmFacts", set()))


def health() -> dict:
    if not llm_chat_enabled():
        return {"enabled": False}
    return {"enabled": True, "model": MODEL, "ok": True}

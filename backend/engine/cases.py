"""Simulated Case Management AI Agent (Agent 3).

Production swap: orchestrator agent + SAS Workflow Manager (two-stage BPMN)
+ Intelligent Decisioning for routing/SLA rules. The alignment tracker feeds
the Learning-to-Autonomy gates (>=90% supervised, >=95% full).
"""

from datetime import datetime, timezone

from store import store, next_id
from engine.tracer import Trace


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_case(session_id: str, citizen: dict, recommendation: dict, case_type: str):
    t = Trace("Case Management Agent", "a2a", f"create_case({case_type})", session_id)
    flow_inputs = {"caseType": case_type, "financialImpactAED":
                   recommendation["financialImpact"]["backpayAED"]}
    t.tool("score_data", "sas-viya-mcp",
           {"module": "case_routing_rules", "inputs": flow_inputs},
           {"priority": "High", "slaHours": 48, "queue": "social-worker-benefits"}, ms=80)
    case = {
        "caseId": f"CASE-2026-{8300 + len(store.cases)}",
        "type": case_type,
        "citizenId": citizen["emiratesId"], "citizenName": citizen["nameEn"],
        "citizenNameAr": citizen["nameAr"],
        "priority": "High", "slaHours": 48, "status": "PENDING_STAGE_1",
        "createdAt": _now(),
        "recommendation": recommendation,
        "sessionId": session_id,
        "stages": [
            {"stage": 1, "role": "Social Worker", "actor": None, "decision": None, "at": None},
            {"stage": 2, "role": "Social Auditor", "actor": None, "decision": None, "at": None},
        ],
        "timeline": [
            {"at": _now(), "event": "Case created by Customer Resolution Agent (A2A)"},
            {"at": _now(), "event": f"AI recommendation attached "
             f"({recommendation['recommendation']}, confidence {recommendation['confidence']})"},
            {"at": _now(), "event": "Routed to Social Worker queue — SLA 48h (rule CASE-ROUTE-011)"},
        ],
        "aiHumanAligned": None,
    }
    store.cases.append(case)
    t.tool("create_case_record", "dynamics365-mcp",
           {"entity": "incident", "caseId": case["caseId"]},
           {"crmRef": f"CRM-{case['caseId']}"}, ms=140)
    t.done(f"Case {case['caseId']} created, two-stage approval initiated")
    case["traceId"] = t.rec["traceId"]
    return case


def approve_stage(case_id: str, stage: int, actor: str, decision: str, comment: str = ""):
    case = next((c for c in store.cases if c["caseId"] == case_id), None)
    if not case:
        raise ValueError("Case not found")
    expected = {"PENDING_STAGE_1": 1, "PENDING_STAGE_2": 2}.get(case["status"])
    if expected != stage:
        raise ValueError(f"Case is not awaiting stage {stage}")
    st = case["stages"][stage - 1]
    st.update({"actor": actor, "decision": decision, "at": _now(), "comment": comment})
    case["timeline"].append({"at": _now(),
                             "event": f"Stage {stage} ({st['role']}): {decision} by {actor}"})

    if decision != "APPROVE_RECOMMENDATION":
        case["status"] = "RETURNED"
        case["aiHumanAligned"] = False
        _update_autonomy(False)
        case["timeline"].append({"at": _now(), "event": "Returned — human overrode AI recommendation"})
        return case, None

    if stage == 1:
        case["status"] = "PENDING_STAGE_2"
        return case, None

    # Stage 2 complete -> close and execute financial effect
    case["status"] = "CLOSED"
    case["aiHumanAligned"] = True
    _update_autonomy(True)
    fin = case["recommendation"]["financialImpact"]
    t = Trace("Case Management Agent", "workflow", f"execute_outcome({case_id})", case["sessionId"])
    t.tool("execute_benefit_action", "benefits-mcp",
           {"action": "RELEASE_BACKPAY", "citizenId": case["citizenId"],
            "amountAED": fin["backpayAED"], "authority": "two-stage-approved"},
           {"paymentRef": next_id("PAY"), "scheduled": "next payment run"}, ms=210)
    t.tool("send_notification", "notify-mcp",
           {"channel": "sms", "to": "+971-50-XXX-4821",
            "template": "backpay_approved", "lang": "ar"},
           {"status": "queued"}, ms=60)
    t.done(f"Back-pay AED {fin['backpayAED']:,.0f} released after two-stage approval")
    case["timeline"].append({"at": _now(),
                             "event": f"Case closed — back-pay AED {fin['backpayAED']:,.0f} scheduled; citizen notified"})
    store.notifications.append({
        "at": _now(), "to": case["citizenName"], "channel": "SMS",
        "textEn": f"MoCE: your Inflation Allowance is reinstated. Back-payment of AED "
                  f"{fin['backpayAED']:,.0f} is scheduled in the next payment run.",
        "textAr": f"وزارة تمكين المجتمع: تمت إعادة صرف علاوة غلاء المعيشة. سيتم صرف مبلغ "
                  f"{fin['backpayAED']:,.0f} درهم بأثر رجعي في دورة الدفع القادمة.",
    })

    # Wake the citizen's chat session with the good news.
    session = store.sessions.get(case["sessionId"])
    if session is not None:
        session["events"].append({
            "type": "agent_message",
            "answerEn": f"✅ Good news — your case {case_id} completed both approval stages. "
                        f"Your Inflation Allowance is reinstated at AED {fin['monthlyAED']:,.0f}/month and a "
                        f"back-payment of AED {fin['backpayAED']:,.0f} ({fin['backpayMonths']} months) has been "
                        f"scheduled. You will receive an SMS confirmation.",
            "answerAr": f"✅ خبر سار — أكملت حالتك {case_id} مرحلتي الاعتماد. تمت إعادة صرف علاوة غلاء "
                        f"المعيشة بواقع {fin['monthlyAED']:,.0f} درهم شهرياً، وتمت جدولة دفعة بأثر رجعي بمبلغ "
                        f"{fin['backpayAED']:,.0f} درهم ({fin['backpayMonths']} أشهر). ستصلك رسالة نصية للتأكيد.",
            "meta": {"caseId": case_id, "kind": "case_closed"},
        })
    return case, t.rec["traceId"]


def _update_autonomy(aligned: bool):
    a = store.autonomy
    a["casesEvaluated"] += 1
    if aligned:
        a["aligned"] += 1
    rate = a["aligned"] / a["casesEvaluated"]
    a["history"][-1]["alignment"] = round(rate, 4)
    a["history"][-1]["cases"] += 1
    if rate >= a["gates"]["full"]:
        a["phase"] = "FULL_AUTONOMY_ELIGIBLE"
    elif rate >= a["gates"]["supervised"]:
        a["phase"] = "SUPERVISED_AUTONOMY_ELIGIBLE"
    else:
        a["phase"] = "LEARNING"

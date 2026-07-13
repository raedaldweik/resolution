"""Simulated Knowledge & Decision AI Agent (Agent 2).

Production swap: a SAS RAM agent over the MoCE policy collections (citations
come from RAM retrieval), calling Intelligent Decisioning through MCP for the
deterministic part. The recommendation contract below is the exact structured
output other agents consume via A2A.
"""

from store import store
from engine import decisioning
from engine.tracer import Trace


def retrieve(query: str, k: int = 2):
    """Toy keyword scorer standing in for vector retrieval over RAM collections."""
    words = {w.lower().strip("؟?.,") for w in query.split() if len(w) > 3}
    scored = []
    for p in store.policies:
        hay = (p["title"] + " " + p["text"]).lower()
        score = sum(1 for w in words if w in hay)
        boost = 2 if any(w in hay for w in ("reinstat", "back", "suspen", "علاوة", "تعليق")) else 0
        scored.append((score + boost, p))
    scored.sort(key=lambda x: -x[0])
    chunks = []
    for score, p in scored[:k]:
        chunks.append({"docId": p["docId"], "title": p["title"], "titleAr": p["titleAr"],
                       "article": p["article"], "page": p["page"],
                       "score": round(min(0.98, 0.62 + 0.11 * score), 2),
                       "textPreview": p["text"][:260], "textPreviewAr": p["textAr"][:260]})
    return chunks


def assess_eligibility(session_id: str, citizen: dict, verified_income: float):
    """Full decision-support call: retrieve policy + execute decision flow ->
    structured recommendation {recommendation, rationale, evidence, confidence, risk}."""
    t = Trace("Knowledge & Decision Agent", "a2a",
              f"assess_eligibility({citizen['nameEn']}, income={verified_income})", session_id)

    chunks = retrieve("inflation allowance eligibility reinstatement suspension back-payment")
    t.retrieval("MoCE Policy Library", "inflation allowance eligibility + reinstatement rules",
                chunks, ms=420)

    flow = decisioning.execute_flow({
        "monthlyIncomeAED": verified_income, "nationality": citizen["nationality"],
        "familySize": citizen["familySize"], "verifiedWithinMonths": 0,
    })
    t.tool("score_data", "sas-viya-mcp",
           {"module": flow["masModule"], "version": flow["version"],
            "inputs": {"monthlyIncomeAED": verified_income, "nationality": citizen["nationality"],
                       "familySize": citizen["familySize"], "verifiedWithinMonths": 0}},
           {"outcome": flow["outcome"], "confidence": flow["confidence"],
            "ruleFires": [f["ruleId"] for f in flow["ruleFires"] if f["passed"]]}, ms=95)

    eligible = flow["outcome"] == "ELIGIBLE"
    months_suspended = 3
    monthly = citizen["benefits"][0]["monthlyAmountAED"] or 2350
    backpay = months_suspended * monthly if eligible else 0

    recommendation = {
        "recommendation": "REINSTATE_WITH_BACKPAY" if eligible else "MAINTAIN_SUSPENSION",
        "rationale": (f"Renewed income verification (AED {verified_income:,.0f}/month, human-verified) "
                      f"is below the Schedule B threshold (AED {flow['threshold']:,.0f}). Suspension was "
                      f"caused solely by expired verification; Art. 7.1 mandates reinstatement with "
                      f"retroactive payment of {months_suspended} withheld instalments."
                      ) if eligible else (
                      f"Verified income AED {verified_income:,.0f}/month exceeds the Schedule B "
                      f"threshold (AED {flow['threshold']:,.0f}); eligibility conditions are not met."),
        "evidence": [{"docId": c["docId"], "article": c["article"], "page": c["page"],
                      "title": c["title"]} for c in chunks],
        "confidence": flow["confidence"],
        "risk": "LOW" if eligible else "MEDIUM",
        "decisionFlow": {"flow": flow["flow"], "version": flow["version"],
                         "ruleFires": flow["ruleFires"]},
        "financialImpact": {"monthlyAED": monthly if eligible else 0,
                            "backpayAED": backpay, "backpayMonths": months_suspended if eligible else 0},
    }
    t.llm("recommendation synthesis",
          "Compose decision memo from rule outcome + retrieved policy context…",
          f"{recommendation['recommendation']} (conf {recommendation['confidence']})", 1720, 260, 1100)
    t.done(f"{recommendation['recommendation']} — confidence {recommendation['confidence']}")
    recommendation["traceId"] = t.rec["traceId"]
    recommendation["chunks"] = chunks
    return recommendation

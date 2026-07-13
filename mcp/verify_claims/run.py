"""verify_claims guardrail — MCP server for SAS RAM.

The hallucination gate from the MoCE RFP: every name, date, and amount in a
draft reply must be traceable to system records. The agent calls
extract_claims on its draft, then verify_claims against the facts gathered
from its tool calls; any unverified claim means the reply must be blocked
and escalated.

Environment:
  PORT   listen port (default 8300)
"""

import os
import re

from fastmcp import FastMCP

mcp = FastMCP("moce-verify-claims")

AMOUNT = re.compile(r"(?:AED|درهم|Dhs?\.?)\s?([\d,]+(?:\.\d+)?)|([\d,]{4,})\s?(?:AED|درهم)", re.I)
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b")
PROPER = re.compile(r"\b([A-Z][a-z]+(?: Al [A-Z][a-z]+| [A-Z][a-z]+){1,3})\b")


@mcp.tool()
def extract_claims(draft_reply: str) -> dict:
    """Extract the verifiable claims (amounts, dates, proper names) from a draft reply."""
    amounts = [m.group(1) or m.group(2) for m in AMOUNT.finditer(draft_reply)]
    dates = DATE.findall(draft_reply)
    names = PROPER.findall(draft_reply)
    return {"amounts": amounts, "dates": dates, "names": names,
            "claimCount": len(amounts) + len(dates) + len(names)}


@mcp.tool()
def verify_claims(claims: list[str], facts: list[str]) -> dict:
    """Verify each claim against the facts gathered from tool calls this session.
    A claim passes only if its normalized form appears in at least one fact.
    verdict=BLOCK means the reply MUST NOT be sent — answer only with the
    verified subset and escalate the rest to a human."""

    def norm(s: str) -> str:
        return re.sub(r"[\s,]+", "", str(s)).lower()

    normalized_facts = [norm(f) for f in facts]
    results = []
    for claim in claims:
        ok = any(norm(claim) in f or f in norm(claim) for f in normalized_facts if f)
        results.append({"claim": claim, "verified": ok})
    unverified = [r["claim"] for r in results if not r["verified"]]
    return {
        "results": results,
        "verified": len(results) - len(unverified),
        "unverified": unverified,
        "verdict": "BLOCK" if unverified else "PASS",
        "instruction": ("Do NOT state the unverified claims. Answer with verified facts only, "
                        "state clearly that the rest could not be verified, and escalate to a "
                        "human specialist.") if unverified else "All claims verified — safe to send.",
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0",
            port=int(os.getenv("PORT", "8300")), path="/mcp")

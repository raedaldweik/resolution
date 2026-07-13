"""MoCE demo action tools — MCP server for SAS RAM.

Exposes the demo backend's citizen/benefit/case operations as MCP tools so a
RAM agent can investigate and act on the same data the UI shows. Register in
RAM either as a Container MCP Server (image from GHCR) or paste run.py +
requirements.txt into a Code MCP Server template.

Environment:
  MOCE_BACKEND_URL   base URL of the deployed demo backend
                     (e.g. https://moce-demo.up.railway.app)
  PORT               listen port (default 8200)
"""

import os

import httpx
from fastmcp import FastMCP

BACKEND = os.getenv("MOCE_BACKEND_URL", "http://localhost:8000").rstrip("/")

mcp = FastMCP("moce-demo-tools")


def _get(path: str):
    r = httpx.get(f"{BACKEND}{path}", timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict):
    r = httpx.post(f"{BACKEND}{path}", json=body, timeout=30)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def get_citizen_profile(emirates_id: str) -> dict:
    """Retrieve a citizen's profile, benefits, and employment record by Emirates ID."""
    c = _get(f"/api/citizens/{emirates_id}")
    return {k: c[k] for k in ("emiratesId", "nameEn", "nameAr", "emirate", "familySize",
                              "employment", "benefits") if k in c}


@mcp.tool()
def get_payment_history(emirates_id: str) -> list:
    """List recent benefit payments (date, amount AED, status) for a citizen."""
    return _get(f"/api/citizens/{emirates_id}").get("payments", [])


@mcp.tool()
def get_case_status(case_id: str) -> dict:
    """Check a case's status, approval stages, and timeline."""
    c = _get(f"/api/cases/{case_id}")
    return {"caseId": c["caseId"], "status": c["status"], "stages": c["stages"],
            "timeline": c["timeline"][-5:]}


@mcp.tool()
def run_eligibility_flow(emirates_id: str) -> dict:
    """Execute the Inflation Allowance eligibility decision flow for a citizen.
    Returns outcome, confidence, and the per-rule fire trace.
    (Production: SAS Intelligent Decisioning module via MAS.)"""
    return _post("/api/decisioning/test", {"citizenId": emirates_id})


@mcp.tool()
def list_open_escalations() -> list:
    """List open escalations awaiting a human specialist."""
    return _get("/api/escalations").get("escalations", [])


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0",
            port=int(os.getenv("PORT", "8200")), path="/mcp")

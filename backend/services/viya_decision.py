"""Execute the published SAS Intelligent Decisioning flow — through the
sas-mcp-server MCP (score_data → MAS), no RAM involved.

The published module (authored in SAS ID, published to MAS):
  module  decision_84173c15_4130_492c_811       (override: DECISION_MODULE_ID)
  step    execute                               (override: DECISION_STEP_ID)
  inputs  ALL LOWERCASE — MAS lowercases variable names on publish:
          monthlyincomeaed, nationality, familysize, verifiedwithinmonths,
          suspensionreason, monthssuspended, monthlyamountaed
  outputs outcome, reasoncode, confidence, action, backpaymonths, backpayaed,
          approvalpath (+ MAS bookkeeping: pathid, rulesfiredforrecordcount)

Environment:
  SAS_MCP_URL       sas-mcp-server endpoint (default http://127.0.0.1:8134/mcp
                    — the in-container sidecar started by start.sh)
  SAS_MCP_API_KEY   the server's MCP_API_KEY (X-API-Key header)
"""
from __future__ import annotations

import json
import os
import threading

import httpx

SAS_MCP_URL = os.getenv("SAS_MCP_URL", "http://127.0.0.1:8134/mcp").rstrip("/")
SAS_MCP_API_KEY = os.getenv("SAS_MCP_API_KEY", os.getenv("MCP_API_KEY", ""))
MODULE_ID = os.getenv("DECISION_MODULE_ID", "decision_84173c15_4130_492c_811")
STEP_ID = os.getenv("DECISION_STEP_ID", "execute")
TIMEOUT = float(os.getenv("SAS_MCP_TIMEOUT", "60"))
PROTOCOL_VERSION = "2025-06-18"

# The exact MAS input variable names (lowercase!) mapped from tool arguments.
INPUT_MAP = {
    "monthly_income_aed": "monthlyincomeaed",
    "nationality": "nationality",
    "family_size": "familysize",
    "verified_within_months": "verifiedwithinmonths",
    "suspension_reason": "suspensionreason",
    "months_suspended": "monthssuspended",
    "monthly_amount_aed": "monthlyamountaed",
}

_lock = threading.Lock()
_state: dict = {"session": None, "next_id": 1}


def _headers(mcp_session: str | None = None) -> dict:
    h = {"Content-Type": "application/json",
         "Accept": "application/json, text/event-stream",
         "MCP-Protocol-Version": PROTOCOL_VERSION}
    if SAS_MCP_API_KEY:
        h["X-API-Key"] = SAS_MCP_API_KEY
    if mcp_session:
        h["mcp-session-id"] = mcp_session
    return h


def _parse_body(resp: httpx.Response) -> dict | None:
    if "text/event-stream" in resp.headers.get("content-type", ""):
        msg = None
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                try:
                    candidate = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict) and ("result" in candidate or "error" in candidate):
                    msg = candidate
        return msg
    return resp.json() if resp.content else None


def _post(client: httpx.Client, payload: dict, mcp_session: str | None):
    resp = client.post(SAS_MCP_URL, json=payload, headers=_headers(mcp_session))
    resp.raise_for_status()
    return resp


def _initialize(client: httpx.Client) -> str | None:
    resp = _post(client, {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                          "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                     "clientInfo": {"name": "moce-agents-backend", "version": "1.0"}}}, None)
    body = _parse_body(resp) or {}
    if "error" in body:
        raise RuntimeError(f"MCP initialize failed: {body['error'].get('message')}")
    sid = resp.headers.get("mcp-session-id")
    client.post(SAS_MCP_URL, headers=_headers(sid),
                json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return sid


def _rpc(method: str, params: dict, timeout: float | None = None) -> dict:
    with _lock:
        rpc_id = _state["next_id"]
        _state["next_id"] += 1
        sid = _state["session"]
    payload = {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}
    with httpx.Client(timeout=timeout or TIMEOUT) as client:
        if sid is None:
            sid = _initialize(client)
            with _lock:
                _state["session"] = sid
        try:
            resp = _post(client, payload, sid)
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in (400, 404):
                raise
            sid = _initialize(client)  # stale MCP session — re-handshake once
            with _lock:
                _state["session"] = sid
            resp = _post(client, payload, sid)
        body = _parse_body(resp) or {}
    if "error" in body:
        raise RuntimeError(body["error"].get("message", str(body["error"])))
    return body.get("result", {})


def _tool_payload(result: dict) -> dict:
    if result.get("isError"):
        text = " ".join(c.get("text", "") for c in result.get("content", []))
        raise RuntimeError(text[:400] or "tool returned isError")
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for c in result.get("content", []):
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except (json.JSONDecodeError, TypeError):
                return {"text": c["text"]}
    return {}


def execute(**kwargs) -> dict:
    """Score the decision flow. kwargs use the tool's snake_case names (see
    INPUT_MAP); values are sent to MAS under the published lowercase names.
    Never raises — returns {"ok": False, "error": ...} for the agent to relay."""
    inputs = {}
    for arg, mas_name in INPUT_MAP.items():
        if arg in kwargs and kwargs[arg] is not None:
            inputs[mas_name] = kwargs[arg]
    try:
        result = _rpc("tools/call", {
            "name": "score_data",
            "arguments": {"module_id": MODULE_ID, "step_id": STEP_ID, "input_data": inputs},
        })
        mas = _tool_payload(result)
        outputs = {}
        for o in mas.get("outputs", []) or []:
            if isinstance(o, dict) and "name" in o:
                outputs[o["name"]] = o.get("value")
        if not outputs and isinstance(mas, dict):
            outputs = {k: v for k, v in mas.items() if not isinstance(v, (dict, list))}
        return {"ok": True, "module": MODULE_ID, "step": STEP_ID,
                "sentInputs": inputs, "outputs": outputs,
                "executedOn": f"SAS Intelligent Decisioning — MAS module '{MODULE_ID}' via sas-mcp-server"}
    except Exception as e:
        with _lock:
            _state["session"] = None
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}",
                "module": MODULE_ID, "sentInputs": inputs}


def health() -> dict:
    try:
        result = _rpc("tools/list", {}, timeout=8)
        names = [t.get("name") for t in result.get("tools", [])]
        return {"url": SAS_MCP_URL, "module": MODULE_ID,
                "ok": "score_data" in names, "tools": len(names)}
    except Exception as e:
        return {"url": SAS_MCP_URL, "module": MODULE_ID, "ok": False,
                "error": f"{type(e).__name__}: {str(e)[:200]}"}

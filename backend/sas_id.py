"""Live SAS Intelligent Decisioning execution — through the sas-mcp-server MCP.

When configured, the demo's decision flow no longer simulates: the payload is
sent to the real SAS ID rule set (published to MAS) by calling the
sas-mcp-server's `score_data` tool over MCP streamable HTTP
(POST /microanalyticScore/modules/{module}/steps/{step} on Viya).

The local rule mirror still runs to render the per-rule fire trace in the UI,
but outcome + confidence come from SAS, and every result is stamped with
`executedOn` so the demo is honest about where the decision was made.

Environment:
  SAS_MCP_URL       sas-mcp-server endpoint in direct HTTP mode,
                    e.g. http://<host>:8134/mcp   (uv run app-http-direct)
  SAS_MCP_API_KEY   the server's MCP_API_KEY (sent as X-API-Key); optional
  SAS_ID_MODULE     MAS module id (default: inflation_allowance_eligibility)
  SAS_ID_STEP       MAS step id (default: execute)
  SAS_MCP_TIMEOUT   seconds per call (default: 30)

Setup guide: docs/SAS_ID_SETUP.md (authoring the rule set in SAS ID,
publishing to MAS, starting the MCP server).
"""

import json
import os
import threading

import httpx

SAS_MCP_URL = os.getenv("SAS_MCP_URL", "").strip().rstrip("/")
SAS_MCP_API_KEY = os.getenv("SAS_MCP_API_KEY", "")
SAS_ID_MODULE = os.getenv("SAS_ID_MODULE", "inflation_allowance_eligibility")
SAS_ID_STEP = os.getenv("SAS_ID_STEP", "execute")
TIMEOUT = float(os.getenv("SAS_MCP_TIMEOUT", "30"))
PROTOCOL_VERSION = "2025-06-18"

_lock = threading.Lock()
_state: dict = {"session": None, "next_id": 1}


def enabled() -> bool:
    return bool(SAS_MCP_URL)


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
    """MCP streamable HTTP answers either as JSON or as an SSE stream."""
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
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
    if resp.content:
        return resp.json()
    return None


def _post(client: httpx.Client, payload: dict, mcp_session: str | None):
    resp = client.post(SAS_MCP_URL, json=payload, headers=_headers(mcp_session))
    resp.raise_for_status()
    return resp


def _initialize(client: httpx.Client) -> str | None:
    resp = _post(client, {
        "jsonrpc": "2.0", "id": 0, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION,
                   "capabilities": {},
                   "clientInfo": {"name": "moce-demo-backend", "version": "1.0"}},
    }, None)
    body = _parse_body(resp) or {}
    if "error" in body:
        raise RuntimeError(f"MCP initialize failed: {body['error'].get('message')}")
    sid = resp.headers.get("mcp-session-id")
    client.post(SAS_MCP_URL, headers=_headers(sid),
                json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return sid


def _rpc(method: str, params: dict) -> dict:
    """One JSON-RPC call, re-initializing the MCP session once if it expired."""
    with _lock:
        rpc_id = _state["next_id"]
        _state["next_id"] += 1
        sid = _state["session"]
    payload = {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}
    with httpx.Client(timeout=TIMEOUT) as client:
        if sid is None:
            sid = _initialize(client)
            with _lock:
                _state["session"] = sid
        try:
            resp = _post(client, payload, sid)
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in (400, 404):
                raise
            sid = _initialize(client)  # stale session — start a fresh one
            with _lock:
                _state["session"] = sid
            resp = _post(client, payload, sid)
        body = _parse_body(resp) or {}
    if "error" in body:
        raise RuntimeError(body["error"].get("message", str(body["error"])))
    return body.get("result", {})


def _tool_payload(result: dict) -> dict:
    """Unwrap an MCP tools/call result into the tool's own return value."""
    if result.get("isError"):
        text = " ".join(c.get("text", "") for c in result.get("content", []))
        raise RuntimeError(text[:300] or "tool returned isError")
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for c in result.get("content", []):
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except (json.JSONDecodeError, TypeError):
                return {"text": c["text"]}
    return {}


def _map_outputs(mas: dict) -> tuple[dict, str | None, float | None]:
    """MAS returns {"outputs": [{"name": ..., "value": ...}, ...]}."""
    outputs = {}
    for o in mas.get("outputs", []) or []:
        if isinstance(o, dict) and "name" in o:
            outputs[o["name"]] = o.get("value")
    if not outputs and isinstance(mas, dict):  # some wrappers flatten already
        outputs = {k: v for k, v in mas.items() if not isinstance(v, (dict, list))}
    outcome = confidence = None
    for k, v in outputs.items():
        kl = k.lower()
        if outcome is None and any(s in kl for s in ("outcome", "eligib", "decision")) and isinstance(v, str):
            outcome = v.strip().upper()
        if confidence is None and any(s in kl for s in ("confidence", "probab", "score")):
            try:
                confidence = round(float(v), 4)
            except (TypeError, ValueError):
                pass
    return outputs, outcome, confidence


def execute(input_data: dict) -> dict:
    """Score the payload on the published SAS ID module. Never raises —
    returns {"ok": False, "error": ...} so callers can fall back."""
    if not enabled():
        return {"ok": False, "error": "SAS_MCP_URL not configured"}
    try:
        result = _rpc("tools/call", {
            "name": "score_data",
            "arguments": {"module_id": SAS_ID_MODULE, "step_id": SAS_ID_STEP,
                          "input_data": input_data},
        })
        mas = _tool_payload(result)
        outputs, outcome, confidence = _map_outputs(mas)
        return {"ok": True, "module": SAS_ID_MODULE, "outputs": outputs,
                "outcome": outcome, "confidence": confidence,
                "executedOn": f"SAS Intelligent Decisioning — MAS module "
                              f"'{SAS_ID_MODULE}' via sas-viya-mcp"}
    except Exception as e:
        with _lock:
            _state["session"] = None  # force a clean handshake next time
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def health() -> dict:
    if not enabled():
        return {"enabled": False}
    try:
        result = _rpc("tools/list", {})
        names = [t.get("name") for t in result.get("tools", [])]
        return {"enabled": True, "url": SAS_MCP_URL, "module": SAS_ID_MODULE,
                "ok": "score_data" in names,
                "tools": len(names),
                "error": None if "score_data" in names else "score_data tool not exposed"}
    except Exception as e:
        return {"enabled": True, "url": SAS_MCP_URL, "module": SAS_ID_MODULE,
                "ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

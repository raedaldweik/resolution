"""
SAS Retrieval Agent Manager (RAM) client.

Wraps the RAM REST API (OpenAPI v1) and handles SAS Viya authentication.
The browser never talks to RAM directly — this backend proxies every call,
which keeps the bearer token server-side and avoids CORS issues.

Auth options (checked in order):
    RAM_TOKEN            — static bearer token (simplest; expires per policy)
    SAS_CLIENT_ID/SECRET — OAuth client_credentials grant
                           (add SAS_USERNAME/SAS_PASSWORD for the password grant)
    device code flow     — default for standalone RAM (Keycloak): no configuration
                           needed; the UI's "Sign in" button drives the flow against
                           the pre-configured public client (RAM_CLIENT_ID, default
                           "sas-ram-api") with PKCE, and the backend keeps the
                           session alive with the refresh token.

Other env vars:
    RAM_API_URL     — base URL, e.g. https://host/SASRetrievalAgentManager/api/v1
    SAS_LOGON_URL   — override the OAuth token endpoint (default derived from RAM_API_URL)
    RAM_CLIENT_ID   — public client for the device flow (default "sas-ram-api")
    RAM_REALM       — Keycloak realm for standalone RAM (default "sas-iot")
    RAM_VERIFY_SSL  — "false" to skip TLS verification (self-signed certs)
    RAM_MOCK        — "true" to run against an in-memory mock (UI demo without RAM)
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import time
import uuid
from typing import Any

import httpx

RAM_API_URL = os.getenv("RAM_API_URL", "").rstrip("/")
VERIFY_SSL = os.getenv("RAM_VERIFY_SSL", "true").lower() != "false"
MOCK = os.getenv("RAM_MOCK", "").lower() == "true"

TIMEOUT = httpx.Timeout(10.0, read=180.0)

# Queries are submitted asynchronously (synchronous=false) and polled, so no
# single HTTP request to RAM outlives its gateway's timeout. These bound the
# overall wait for an answer and the poll cadence.
QUERY_TIMEOUT = float(os.getenv("RAM_QUERY_TIMEOUT", "600"))
QUERY_POLL_INTERVAL = float(os.getenv("RAM_QUERY_POLL_INTERVAL", "2"))


class RamError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


# ─── Token management ────────────────────────────────────────────────
_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0, "refresh_token": None}
_device_state: dict[str, str] = {}  # in-flight device authorization (verifier + device_code)
# Serializes token refreshes. While a query runs the frontend polls the result
# plus three trace endpoints every couple of seconds, so ~4 RAM calls are always
# in flight. When the access token expires mid-query they would otherwise all
# refresh at once — and Keycloak rotates the refresh token on every use and
# revokes the whole family if a used token is presented again, so a concurrent
# stampede invalidates everyone's session and the UI drops to the sign-in screen
# (the "logged out on a long question" bug). With this lock one coroutine
# refreshes and the rest reuse the token it stored.
_token_lock = asyncio.Lock()


def _oidc_base() -> str:
    """Keycloak OpenID Connect base for standalone RAM, e.g.
    https://host/SASRetrievalAgentManager/auth/realms/sas-iot/protocol/openid-connect"""
    explicit = os.getenv("SAS_LOGON_URL")
    if explicit and "/protocol/openid-connect" in explicit:
        return explicit.split("/protocol/openid-connect")[0] + "/protocol/openid-connect"
    base = RAM_API_URL.split("/api/")[0]  # strip /api/v1
    realm = os.getenv("RAM_REALM", "sas-iot")
    return f"{base}/auth/realms/{realm}/protocol/openid-connect"


def _logon_url() -> str:
    explicit = os.getenv("SAS_LOGON_URL")
    if explicit:
        return explicit
    # Derive https://host/SASLogon/oauth/token from the RAM URL (full Viya);
    # standalone RAM deployments go through _oidc_base() instead.
    base = RAM_API_URL.split("/SASRetrievalAgentManager")[0]
    return f"{base}/SASLogon/oauth/token"


def _store_tokens(body: dict, *, token_url: str | None = None,
                  client_id: str | None = None, auth_style: str = "body") -> None:
    _token_cache["token"] = body["access_token"]
    # Refresh shortly before actual expiry
    _token_cache["expires_at"] = time.time() + int(body.get("expires_in", 300)) - 30
    if body.get("refresh_token"):
        _token_cache["refresh_token"] = body["refresh_token"]
    if token_url:
        _token_cache["token_url"] = token_url
        _token_cache["client_id"] = client_id
        _token_cache["auth_style"] = auth_style  # "basic" (UAA/SASLogon) or "body" (Keycloak public)


# ─── Sign-in flow detection ──────────────────────────────────────────
# Standalone RAM ships Keycloak (device code flow); full SAS Viya uses
# SASLogon (authorization code flow with the sas.cli public client).
_flow_cache: dict[str, str | None] = {"flow": None}


def _viya_logon_base() -> str:
    explicit = os.getenv("SAS_LOGON_URL")
    if explicit:
        return explicit.split("/oauth/")[0]
    return RAM_API_URL.split("/SASRetrievalAgentManager")[0] + "/SASLogon"


async def detect_signin_flow() -> str:
    """Return "device" (Keycloak) or "code" (Viya SASLogon paste-the-code)."""
    env = os.getenv("RAM_AUTH_FLOW")
    if env in ("device", "code"):
        return env
    if _flow_cache["flow"]:
        return _flow_cache["flow"]
    if not RAM_API_URL:
        return "device"
    realm = os.getenv("RAM_REALM", "sas-iot")
    base = RAM_API_URL.split("/api/")[0]
    try:
        async with httpx.AsyncClient(verify=VERIFY_SSL, timeout=httpx.Timeout(8.0)) as client:
            r = await client.get(f"{base}/auth/realms/{realm}/.well-known/openid-configuration")
        _flow_cache["flow"] = "device" if r.status_code == 200 else "code"
    except Exception:
        return "device"  # don't cache on network errors — retry next time
    return _flow_cache["flow"]


# ─── Viya SASLogon authorization code flow (sas.cli public client) ───
# Visiting /SASLogon/oauth/authorize?client_id=sas.cli&response_type=code
# displays an authorization code after login (SSO included); the user
# pastes it into the UI and we exchange it for tokens here.
def viya_authorize_url() -> str:
    client_id = os.getenv("SAS_AUTH_CLIENT_ID", "sas.cli")
    return f"{_viya_logon_base()}/oauth/authorize?client_id={client_id}&response_type=code"


async def viya_code_exchange(code: str) -> dict:
    client_id = os.getenv("SAS_AUTH_CLIENT_ID", "sas.cli")
    client_secret = os.getenv("SAS_AUTH_CLIENT_SECRET", "")
    token_url = f"{_viya_logon_base()}/oauth/token"
    async with httpx.AsyncClient(verify=VERIFY_SSL, timeout=TIMEOUT) as client:
        r = await client.post(token_url,
                              data={"grant_type": "authorization_code", "code": code.strip()},
                              auth=(client_id, client_secret))
    if r.status_code != 200:
        raise RamError(r.status_code, f"Sign-in failed — SASLogon said: {r.text[:300]}")
    _store_tokens(r.json(), token_url=token_url, client_id=client_id, auth_style="basic")
    return {"ok": True}


# ─── Device code flow (standalone RAM / Keycloak public client) ──────
async def device_start() -> dict:
    """Begin a device authorization (PKCE). Returns the code/URL the user needs."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    client_id = os.getenv("RAM_CLIENT_ID", "sas-ram-api")
    async with httpx.AsyncClient(verify=VERIFY_SSL, timeout=TIMEOUT) as client:
        r = await client.post(f"{_oidc_base()}/auth/device", data={
            "client_id": client_id,
            "scope": "openid",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
    if r.status_code != 200:
        raise RamError(r.status_code, f"Device authorization failed: {r.text[:300]}")
    body = r.json()
    _device_state.update({"verifier": verifier, "device_code": body["device_code"]})
    return {
        "userCode": body.get("user_code"),
        "verificationUri": body.get("verification_uri"),
        "verificationUriComplete": body.get("verification_uri_complete"),
        "expiresIn": body.get("expires_in"),
        "interval": body.get("interval", 5),
    }


async def device_poll() -> dict:
    """Poll Keycloak until the user approves the device authorization."""
    if not _device_state.get("device_code"):
        raise RamError(400, "No device authorization in progress — start a sign-in first.")
    client_id = os.getenv("RAM_CLIENT_ID", "sas-ram-api")
    async with httpx.AsyncClient(verify=VERIFY_SSL, timeout=TIMEOUT) as client:
        r = await client.post(f"{_oidc_base()}/token", data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": _device_state["device_code"],
            "code_verifier": _device_state["verifier"],
            "client_id": client_id,
        })
    try:
        body = r.json()
    except Exception:
        raise RamError(r.status_code, r.text[:300])
    if r.status_code != 200:
        error = body.get("error", "")
        if error in ("authorization_pending", "slow_down"):
            return {"pending": True, "slowDown": error == "slow_down"}
        _device_state.clear()
        raise RamError(r.status_code, body.get("error_description") or error or r.text[:300])
    _store_tokens(body, token_url=f"{_oidc_base()}/token", client_id=client_id, auth_style="body")
    _device_state.clear()
    return {"ok": True}


async def _refresh_token_grant() -> str | None:
    """Renew the access token with the stored refresh token (any sign-in flow).

    The caller holds _token_lock, so this is the only refresh in flight — the
    stored refresh token is therefore used exactly once, which is what
    Keycloak's rotation/reuse-detection requires."""
    refresh = _token_cache.get("refresh_token")
    token_url = _token_cache.get("token_url")
    if not refresh or not token_url:
        return None
    client_id = _token_cache.get("client_id") or os.getenv("RAM_CLIENT_ID", "sas-ram-api")
    data = {"grant_type": "refresh_token", "refresh_token": refresh}
    auth = None
    if _token_cache.get("auth_style") == "basic":
        auth = (client_id, os.getenv("SAS_AUTH_CLIENT_SECRET", ""))
    else:
        data["client_id"] = client_id
    try:
        async with httpx.AsyncClient(verify=VERIFY_SSL, timeout=TIMEOUT) as client:
            r = await client.post(token_url, data=data, auth=auth)
    except httpx.HTTPError:
        # Network blip — keep the refresh token so the next call can retry
        # instead of forcing the user to sign in again.
        return None
    if r.status_code == 200:
        _store_tokens(r.json())
        return _token_cache["token"]
    if r.status_code in (400, 401):
        # invalid_grant: the refresh token is genuinely expired or revoked —
        # only now drop it so the UI prompts for a fresh sign-in.
        _token_cache["refresh_token"] = None
    # 5xx / other transient errors: leave the refresh token in place to retry.
    return None


async def _fetch_oauth_token() -> str:
    client_id = os.getenv("SAS_CLIENT_ID")
    client_secret = os.getenv("SAS_CLIENT_SECRET", "")
    username = os.getenv("SAS_USERNAME")
    password = os.getenv("SAS_PASSWORD")
    if not client_id:
        raise RamError(500, "No RAM_TOKEN and no SAS_CLIENT_ID configured — cannot authenticate to SAS Viya.")

    if username and password:
        data = {"grant_type": "password", "username": username, "password": password}
    else:
        data = {"grant_type": "client_credentials"}

    # SASLogon (UAA) wants client auth via HTTP Basic (empty secret is fine for
    # public clients like sas.cli); Keycloak public clients want client_id in
    # the form body. Try Basic first, fall back to the body style.
    async with httpx.AsyncClient(verify=VERIFY_SSL, timeout=TIMEOUT) as client:
        r = await client.post(_logon_url(), data=data, auth=(client_id, client_secret))
        if r.status_code in (400, 401) and not client_secret:
            r = await client.post(_logon_url(), data={**data, "client_id": client_id})
    if r.status_code != 200:
        raise RamError(r.status_code, f"Token request failed: {r.text[:300]}")
    body = r.json()
    _token_cache["token"] = body["access_token"]
    # Refresh a minute before actual expiry
    _token_cache["expires_at"] = time.time() + int(body.get("expires_in", 3600)) - 60
    return _token_cache["token"]


async def _get_token(invalid_token: str | None = None) -> str:
    """Return a usable bearer token, refreshing if needed.

    Pass the token that just drew a 401 as `invalid_token`: a coroutine whose
    request was rejected then either reuses a token another coroutine already
    refreshed, or — if it's the first to notice — does the single refresh
    itself. The refresh path is serialized by _token_lock so concurrent callers
    never stampede the (single-use, rotating) refresh token."""
    static = os.getenv("RAM_TOKEN")
    if static:
        return static
    # Fast path: a valid, not-just-rejected cached token. No lock, no refresh —
    # so normal operation pays nothing for the serialization below.
    cached = _token_cache["token"]
    if cached and cached != invalid_token and time.time() < _token_cache["expires_at"]:
        return cached
    async with _token_lock:
        # Re-check under the lock: another coroutine may have refreshed while we
        # waited, in which case we just reuse its freshly stored token.
        cached = _token_cache["token"]
        if cached and cached != invalid_token and time.time() < _token_cache["expires_at"]:
            return cached
        refreshed = await _refresh_token_grant()
        if refreshed:
            return refreshed
        if os.getenv("SAS_CLIENT_ID"):
            return await _fetch_oauth_token()
        raise RamError(401, "Not signed in — click “Sign in” in the header to authenticate with RAM.")


# ─── HTTP helper ─────────────────────────────────────────────────────
async def _request(method: str, path: str, *, params: dict | None = None, json: dict | None = None,
                   with_response: bool = False) -> Any:
    if MOCK:
        data = await _mock_request(method, path, params=params, json=json)
        return (data, None) if with_response else data
    if not RAM_API_URL:
        raise RamError(500, "RAM_API_URL is not configured. Set it in backend/.env (see .env.example).")

    token = await _get_token()
    url = f"{RAM_API_URL}{path}"
    # Retry transient connection drops (e.g. RAM or its gateway closing a
    # connection — "Server disconnected without sending a response", a
    # RemoteProtocolError — which happens under intermittent/concurrent load).
    # Without this a single blip surfaces to the user as a failed turn; a fresh
    # connection on retry almost always succeeds. Backs off briefly between
    # attempts. The 401 access-token retry is nested inside each attempt.
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(verify=VERIFY_SSL, timeout=TIMEOUT) as client:
                r = await client.request(method, url, params=params, json=json,
                                         headers={"Authorization": f"Bearer {token}"})
                # One retry on 401 in case the access token just expired. Hand the
                # rejected token to _get_token so the refresh stays single-flight:
                # if a concurrent call already refreshed we reuse its token, and we
                # never refresh a token that's already been rotated (which Keycloak
                # would treat as reuse and revoke the whole session).
                if r.status_code == 401 and not os.getenv("RAM_TOKEN"):
                    token = await _get_token(invalid_token=token)
                    r = await client.request(method, url, params=params, json=json,
                                             headers={"Authorization": f"Bearer {token}"})
            break  # got an HTTP response (any status) — stop retrying
        except httpx.TransportError as e:
            last_exc = e
            if attempt == 2:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
    if r.status_code >= 400:
        try:
            message = r.json().get("message", r.text[:300])
        except Exception:
            message = r.text[:300]
        raise RamError(r.status_code, message)
    data = r.json() if r.content else None
    return (data, r) if with_response else data


# ─── Public API ──────────────────────────────────────────────────────
async def list_agents() -> list[dict]:
    body = await _request("GET", "/agents", params={"limit": 100})
    return body.get("items") or []


async def list_collections() -> list[dict]:
    body = await _request("GET", "/collections", params={"limit": 100})
    return body.get("items") or []


async def list_sessions() -> list[dict]:
    # In a shared-identity deployment (one RAM token/login for several users —
    # e.g. a bootcamp) every user queries RAM as the same identity, so RAM's
    # session history is shared: each person would see everyone else's
    # conversations in "Recent conversations". Set RAM_HIDE_HISTORY=true to
    # suppress the shared list — each browser then keeps only its own live
    # session. (True per-user history requires per-user RAM logins.)
    if os.getenv("RAM_HIDE_HISTORY", "").lower() == "true":
        return []
    body = await _request("GET", "/querySessions", params={"limit": 100, "sortBy": "updateTimestamp:descending"})
    sessions = body.get("items") or []
    # Annotate each session with the agent/collections its queries targeted so
    # the UI can scope "Recent conversations" to the selected target. Sessions
    # don't carry this themselves, so derive it from the query records.
    targets: dict[str, dict] = {}
    try:
        # GET /query caps limit at 100 — page through (bounded) to cover history
        for start in range(0, 1000, 100):
            qbody = await _request("GET", "/query", params={"limit": 100, "start": start})
            items = qbody.get("items") or []
            for q in items:
                sid = q.get("querySessionId")
                if not sid or sid in targets:
                    continue
                targets[sid] = {"target": q.get("target"), **_target_ids(q)}
            if len(items) < 100:
                break
    except RamError:
        pass  # best-effort: an unannotated history is better than no history
    return [{**s, **targets.get(s.get("id"), {})} for s in sessions]


def _target_ids(q: dict) -> dict:
    """targetId comes back as e.g. {"agentId": …} or {"configurationIds": […]},
    with snake_case variants in some responses."""
    tid = q.get("targetId") or {}
    return {
        "agentId": tid.get("agentId") or tid.get("agent_id"),
        "collectionIds": (tid.get("configurationIds") or tid.get("configuration_ids")
                          or tid.get("collectionIds") or tid.get("collection_ids") or []),
    }


async def list_session_queries(session_id: str) -> list[dict]:
    body = await _request("GET", "/query", params={"filter": f"eq(querySessionId,'{session_id}')", "limit": 100})
    items = body.get("items") or []
    # Order chronologically — RAM doesn't guarantee an order on this endpoint,
    # and an unordered list reconstructs the conversation with turns scrambled.
    # ISO-8601 timestamps sort lexically; undated items sink to the top stably.
    items.sort(key=lambda q: (q.get("creationTimeStamp") or q.get("creationTimestamp")
                              or q.get("insertTimestamp") or q.get("modifiedTimeStamp") or ""))
    # A conversation turn is a top-level *user* query. Querying an agent also
    # records the agent's own internal sub-queries (origin "agent", each with a
    # parentQueryId) under the same session id — rendering those as chat bubbles
    # is what made reloaded conversations look garbled. Keep only the user turns.
    turns = [q for q in items
             if (q.get("origin") or "user") == "user" and not q.get("parentQueryId")]
    normalized = [_normalize_query(q) for q in turns]
    # Re-attach each agent turn's tool calls (with their outputs) so an inline
    # map renders on reload exactly like a live answer. RAM's persisted
    # response.toolCalls omits the tool *outputs* where the tomtom-render-map
    # spec lives, so without this the map would be missing from history.
    await _attach_tool_outputs([n for n in normalized
                                if n.get("queryId") and n.get("target") == "agent"])
    return normalized


async def _attach_tool_outputs(turns: list[dict], *, concurrency: int = 8) -> None:
    """Fetch /toolCalls for each turn and stash them under `trace` (bounded
    concurrency so a long history doesn't stampede RAM). Best-effort: a turn
    whose trace can't be fetched simply renders without its map."""
    if not turns:
        return
    sem = asyncio.Semaphore(concurrency)

    async def one(turn: dict) -> None:
        async with sem:
            try:
                body = await _request("GET", "/toolCalls",
                                      params={"filter": f"eq(parentQueryId,'{turn['queryId']}')", "limit": 100})
            except Exception:
                return
            items = body.get("items") or []
            if items:
                turn["trace"] = {"toolCalls": items}

    await asyncio.gather(*(one(t) for t in turns), return_exceptions=True)


async def submit_query(content: str, *, agent_id: str | None = None,
                       collection_ids: list[str] | None = None,
                       session_id: str | None = None) -> dict:
    payload: dict[str, Any] = {"content": content}
    if agent_id:
        payload["agentId"] = agent_id
    elif collection_ids:
        payload["collectionIds"] = collection_ids
    else:
        raise RamError(400, "Either an agent or at least one collection must be selected.")
    if session_id:
        payload["querySessionId"] = session_id

    # Submit asynchronously: a synchronous POST /query holds one HTTP request
    # open for the whole agent run, which gateways in front of RAM kill with
    # "504 upstream request timeout" on slow queries. The frontend polls
    # /api/query/{id} for the result and /api/query/{id}/trace for live
    # tool/LLM/retrieval activity while it runs.
    body, resp = await _request("POST", "/query", params={"synchronous": "false", "persistent": "true"},
                                json=payload, with_response=True)
    out = {
        "queryId": _extract_query_id(body, resp),
        "querySessionId": (body or {}).get("querySessionId") or session_id,
        "pollInterval": QUERY_POLL_INTERVAL,
        "timeout": QUERY_TIMEOUT,
    }
    if _query_finished(body):  # the mock (and a sync-answering RAM) returns the result inline
        out["result"] = _normalize_query(body)
    elif not out["queryId"]:
        raise RamError(502, "RAM accepted the query but returned no query id to poll. "
                            f"Submit response: {str(body)[:200]!r}")
    return out


async def query_status(query_id: str) -> dict:
    q = await _fetch_query(query_id)
    if not _query_finished(q):
        return {"done": False}
    return {"done": True, "result": _normalize_query(q)}


async def query_trace(query_id: str) -> dict:
    """The tool, LLM, and retrieval calls RAM recorded for a query — each is a
    separate resource filterable by parentQueryId, so this also works while
    the query is still running (calls appear as RAM persists them)."""
    flt = f"eq(parentQueryId,'{query_id}')"
    results = await asyncio.gather(
        _request("GET", "/toolCalls", params={"filter": flt, "limit": 100}),
        _request("GET", "/llmCalls", params={"filter": flt, "limit": 100}),
        _request("GET", "/retrievalCalls", params={"filter": flt, "limit": 100}),
        return_exceptions=True,
    )

    def _items(r: Any) -> list:
        return [] if isinstance(r, BaseException) or not r else (r.get("items") or [])

    return {"toolCalls": _items(results[0]), "llmCalls": _items(results[1]),
            "retrievalCalls": _items(results[2])}


def _extract_query_id(body: dict | None, resp: httpx.Response | None) -> str | None:
    """An async submit may return the query object, a bare id, or just a
    Location header pointing at the created query — accept any of them."""
    if isinstance(body, dict):
        for key in ("id", "queryId"):
            if body.get(key):
                return str(body[key])
        items = body.get("items")
        if isinstance(items, list) and items and isinstance(items[0], dict) and items[0].get("id"):
            return str(items[0]["id"])
    if isinstance(body, str) and body.strip():
        return body.strip()
    if resp is not None:
        location = resp.headers.get("location") or resp.headers.get("content-location") or ""
        if location:
            return location.rstrip("/").rsplit("/", 1)[-1].split("?")[0] or None
    return None


def _query_finished(q: dict | None) -> bool:
    """Done = a nonzero errorCode/errorText, a terminal state field, or a
    response that actually carries content.

    Some RAM builds attach an EMPTY response object ({} or {"answer": null})
    to the query record while the agent is still running — treating any
    non-null response as finished made those deployments render '(empty
    answer)' with zero tokens instantly. So an empty response only counts as
    finished when the record's state says the run is over."""
    if not q:
        return False
    if q.get("errorCode") or q.get("errorText"):
        return True
    state = str(q.get("state") or q.get("status") or "").lower()
    if state in ("completed", "complete", "succeeded", "success", "done",
                 "failed", "error", "canceled", "cancelled", "timedout"):
        return True
    if state in ("pending", "running", "executing", "inprogress", "in_progress",
                 "created", "queued", "submitted", "started"):
        return False
    resp = q.get("response")
    if isinstance(resp, dict):
        return (resp.get("answer") is not None or bool(resp.get("toolCalls"))
                or bool(resp.get("context")))
    return resp is not None


async def _fetch_query(query_id: str) -> dict | None:
    """Fetch a single query record. There is no GET /query/{id} item endpoint
    in the v1 API — use the collection endpoint's id filter (and match the id
    client-side too, in case a deployment ignores the filter)."""
    body = await _request("GET", "/query", params={"filter": f"eq(id,'{query_id}')", "limit": 100})
    items = body.get("items") or []
    return next((i for i in items if str(i.get("id")) == str(query_id)),
                items[0] if len(items) == 1 else None)


async def fetch_query_raw(query_id: str) -> dict:
    """The untouched RAM query record — /api/query/{id}/raw exposes this for
    diagnosing deployment-specific shapes (empty answers, odd state fields)."""
    q = await _fetch_query(query_id)
    if q is None:
        raise RamError(404, f"RAM returned no query record for id {query_id!r}.")
    return q


def _normalize_query(q: dict) -> dict:
    """Flatten RAM's queryResponse into the shape the frontend renders."""
    response = q.get("response") or {}
    return {
        "queryId": q.get("id"),
        "querySessionId": q.get("querySessionId"),
        "content": q.get("content"),
        "answer": response.get("answer"),
        "context": response.get("context") or [],
        "toolCalls": response.get("toolCalls") or [],
        "usage": response.get("usageMetadata") or {},
        "target": q.get("target"),
        "targetId": q.get("targetId"),
        "origin": q.get("origin"),
        "parentQueryId": q.get("parentQueryId"),
        "errorCode": q.get("errorCode", 0),
        "errorText": q.get("errorText"),
    }


def status() -> dict:
    if MOCK:
        return {"status": "ok", "mode": "mock", "ramUrl": "(in-memory mock)", "authenticated": True}
    if os.getenv("RAM_TOKEN"):
        auth, authenticated = "static-token", True
    elif os.getenv("SAS_CLIENT_ID"):
        auth, authenticated = "oauth", True
    else:
        # Standalone RAM: device sign-in through the UI
        auth = "device"
        authenticated = bool(
            _token_cache.get("refresh_token")
            or (_token_cache["token"] and time.time() < _token_cache["expires_at"])
        )
    if not RAM_API_URL:
        state = "unconfigured"
    elif auth == "device" and not authenticated:
        state = "signin_required"
    else:
        state = "ok"
    return {
        "status": state,
        "mode": "live",
        "ramUrl": RAM_API_URL or "(not set)",
        "auth": auth,
        "authenticated": authenticated,
    }


async def status_async() -> dict:
    """status() plus the interactive sign-in flow ("device" or "code")."""
    s = status()
    if s.get("auth") == "device":
        s["signinFlow"] = await detect_signin_flow()
        if s["signinFlow"] == "code":
            s["authorizeUrl"] = viya_authorize_url() if RAM_API_URL else None
    return s


# ─── In-memory mock (RAM_MOCK=true) ──────────────────────────────────
# Lets the UI run end-to-end without a reachable RAM environment. The three
# mock agents mirror the real ones built on RAM (docs/agents/*.md) so the
# dropdown looks identical before and after connecting.
_MOCK_AGENTS = [
    {"id": "a1000000-0000-0000-0000-000000000001", "name": "MoCE Document Processing",
     "description": "OCR (Arabic + English), field extraction and summarization of citizen documents."},
    {"id": "a1000000-0000-0000-0000-000000000002", "name": "MoCE Knowledge & Policy",
     "description": "Answers policy questions from the MoCE Policy Library with citations."},
    {"id": "a1000000-0000-0000-0000-000000000003", "name": "MoCE Customer Resolution",
     "description": "Investigates benefit issues end-to-end: records, policy, decisioning, resolution."},
]
_MOCK_COLLECTIONS = [
    {"id": "c1000000-0000-0000-0000-000000000001", "name": "MoCE Policy Library",
     "description": "Inflation Allowance programme policies and SOPs (Arabic + English)."},
]
_mock_sessions: dict[str, dict] = {}
_mock_traces: dict[str, dict] = {}  # queryId → {"/toolCalls": [...], "/llmCalls": [...], "/retrievalCalls": [...]}


async def _mock_request(method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> Any:
    params = params or {}
    if path == "/agents":
        return {"items": _MOCK_AGENTS, "count": len(_MOCK_AGENTS)}
    if path == "/collections":
        return {"items": _MOCK_COLLECTIONS, "count": len(_MOCK_COLLECTIONS)}
    if path == "/querySessions":
        items = sorted(_mock_sessions.values(), key=lambda s: s["updateTimestamp"], reverse=True)
        return {"items": [{k: s[k] for k in ("id", "title", "insertTimestamp", "updateTimestamp")} for s in items],
                "count": len(items)}
    if path == "/query" and method == "GET":
        filt = params.get("filter", "")
        if "'" in filt:
            sid = filt.split("'")[1]
            session = _mock_sessions.get(sid, {"queries": []})
            return {"items": session["queries"], "count": len(session["queries"])}
        queries = [q for s in _mock_sessions.values() for q in s["queries"]]
        return {"items": queries, "count": len(queries)}
    if path == "/query" and method == "POST":
        now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        sid = (json or {}).get("querySessionId") or str(uuid.uuid4())
        session = _mock_sessions.setdefault(sid, {
            "id": sid, "title": json["content"][:60], "insertTimestamp": now, "updateTimestamp": now, "queries": [],
        })
        session["updateTimestamp"] = now
        agent_id = (json or {}).get("agentId")
        agent = next((a for a in _MOCK_AGENTS if a["id"] == agent_id), None)
        target_name = agent["name"] if agent else "the selected collections"

        # A MoCE-flavored placeholder so the UI can be exercised end-to-end.
        # Every answer is clearly labelled mock — the real answers come from
        # the agents built on RAM (docs/agents/*.md).
        answer = (f"**[Mock answer from {target_name}]**\n\nYou asked: _{json['content']}_\n\n"
                  "This is a placeholder — connect the UI to your SAS Retrieval Agent "
                  "Manager (set `RAM_API_URL`, unset `RAM_MOCK`) and this dropdown will "
                  "list the real agents: **MoCE Document Processing**, **MoCE Knowledge "
                  "& Policy**, and **MoCE Customer Resolution**.")
        tool_calls = [{"toolName": "retrieve_documents",
                       "input": {"query": json["content"]},
                       "output": {"documents": 1}}]

        query = {
            "id": str(uuid.uuid4()), "content": json["content"], "errorCode": 0, "errorText": None,
            "origin": "user", "querySessionId": sid,
            "target": "agent" if agent_id else "collection",
            "targetId": {"agentId": agent_id} if agent_id else {"configurationIds": json.get("collectionIds", [])},
            "response": {
                "answer": answer,
                "context": [{
                    "pageContent": "The inflation allowance is payable to Emirati heads of household "
                                   "whose verified gross monthly income does not exceed the threshold "
                                   "defined in Schedule B (AED 25,000 at publication). Income "
                                   "verification must be renewed every 12 months; benefits are "
                                   "suspended, not terminated, while verification is pending.",
                    "metadata": {"filename": "POL-2024-017_inflation_allowance_operations_manual.pdf", "page": 12},
                }],
                "toolCalls": tool_calls,
                "usageMetadata": {"llmPromptTokens": 220, "llmCompletionTokens": 96,
                                  "llmTotalTokens": 316, "llmTotalCost": 0.0014},
            },
        }
        session["queries"].append(query)
        _mock_traces[query["id"]] = {
            "/toolCalls": [{
                "id": str(uuid.uuid4()), "parentQueryId": query["id"], "toolName": "retrieve_documents",
                "input": {"query": json["content"]},
                "output": {"content": ["Found 1 matching document."], "isError": False}, "cost": 0,
            }],
            "/llmCalls": [{
                "id": str(uuid.uuid4()), "parentQueryId": query["id"], "llmId": "mock-llm",
                "input": {"content": json["content"], "modelName": "sovereign-llm", "modelProvider": "on-prem", "temperature": 0.7},
                "output": {"response": query["response"]["answer"], "toolCalls": []},
                "promptTokens": 220, "completionTokens": 96, "promptCost": 0.0008, "completionCost": 0.0006,
            }],
            "/retrievalCalls": [{
                "id": str(uuid.uuid4()), "parentQueryId": query["id"],
                "input": {"query": json["content"], "k": 4}, "output": {"documents": 1},
            }],
        }
        return query
    if path in ("/toolCalls", "/llmCalls", "/retrievalCalls") and method == "GET":
        filt = params.get("filter", "")
        qid = filt.split("'")[1] if "'" in filt else ""
        return {"items": _mock_traces.get(qid, {}).get(path, [])}
    raise RamError(404, f"Mock has no handler for {method} {path}")

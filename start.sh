#!/bin/sh
# One-container start: the sas-mcp-server sidecar (direct HTTP mode, talks to
# SAS Viya) + the UI/agents backend. Railway runs this as the service CMD.
set -e

# ── Normalize env names: the canonical names are UPPERCASE, but accept the
#    mixed-case spellings too (Viya_Endpoint, Client_ID, …) so a typo in the
#    Railway variables panel doesn't cost a debugging round-trip.
pick() { # pick CANON alt1 alt2 …
    canon="$1"; shift
    eval "current=\${$canon:-}"
    if [ -z "$current" ]; then
        for alt in "$@"; do
            eval "val=\${$alt:-}"
            if [ -n "$val" ]; then export "$canon"="$val"; break; fi
        done
    fi
}
pick VIYA_ENDPOINT        Viya_Endpoint viya_endpoint VIYA_URL
pick VIYA_REFRESH_TOKEN   Viya_Refresh_token Viya_Refresh_Token viya_refresh_token
pick CLIENT_ID            Client_ID client_id
pick SSL_VERIFY           SSL_Verify Ssl_Verify ssl_verify
pick COMPUTE_CONTEXT_NAME Compute_Context_name Compute_Context_Name compute_context_name
pick SCOPE_ENFORCE        Scope_Enforce scope_enforce

# ── The sidecar and the backend share an internal API key by default.
export MCP_API_KEY="${MCP_API_KEY:-internal-$(head -c16 /dev/urandom | od -An -tx1 | tr -d ' \n')}"
export SAS_MCP_API_KEY="${SAS_MCP_API_KEY:-$MCP_API_KEY}"
export SAS_MCP_URL="${SAS_MCP_URL:-http://127.0.0.1:8134/mcp}"

# ── Start the sas-mcp-server sidecar when Viya is configured.
if [ -n "$VIYA_ENDPOINT" ]; then
    echo "→ starting sas-mcp-server sidecar (direct HTTP, $VIYA_ENDPOINT)"
    app-http-direct &
else
    echo "⚠ VIYA_ENDPOINT not set — decision-flow tool will report unavailable"
fi

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"

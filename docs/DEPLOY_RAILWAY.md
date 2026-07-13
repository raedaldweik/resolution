# Deploying to Railway — simulation and SAS versions

One repo, one Docker image, two Railway services. The `APP_MODE` environment
variable decides which version a service runs; everything else is identical.

## Prerequisites

- A Railway account connected to GitHub (railway.com → login with GitHub)
- This repository pushed to GitHub (branch `claude/moce-agent-ecosystem-xfonrv` or merged to `main`)

## Service 1 — Simulation version (`moce-demo`)

1. Railway → **New Project → Deploy from GitHub repo** → select `raedaldweik/resolution`.
2. Railway detects `railway.json` and builds the root `Dockerfile` (frontend build + FastAPI runtime, health check on `/api/health`). No variables needed — `APP_MODE` defaults to `simulation`.
3. **Settings → Networking → Generate Domain** → e.g. `https://moce-demo.up.railway.app`.
4. Done. Fully self-contained: scripted engine, no SAS, no LLM keys — the stage-safe version.

> If deploying from the working branch, set **Settings → Source → Branch** to
> `claude/moce-agent-ecosystem-xfonrv`.

## Service 2 — SAS version (`moce-demo-sas`)

Same repo, second service in the same project (**+ New → GitHub Repo** again). Set variables:

| Variable | Value | Notes |
|---|---|---|
| `APP_MODE` | `sas` | switches chat to the live RAM agent |
| `RAM_API_URL` | `https://<ram-host>/SASRetrievalAgentManager/api/v1` | must be reachable from Railway (public or tunneled) |
| `RAM_AGENT_NAME` | `MoCE Customer Resolution` | the RAM (orchestrator) agent to converse with |
| `RAM_TOKEN` | *(option A)* static bearer token | quick demos; expires |
| `SAS_CLIENT_ID` / `SAS_CLIENT_SECRET` | *(option B)* OAuth client | backend fetches/refreshes tokens itself |
| `SAS_USERNAME` / `SAS_PASSWORD` | *(option C, with B's client)* password grant | named-user identity |
| `SAS_LOGON_URL` | override token endpoint | defaults to `<viya>/SASLogon/oauth/token` |
| `RAM_VERIFY_SSL` | `false` | only for self-signed certificates |

What "SAS version" means today: **chat runs through the real RAM agent**
(answers, citations from retrieval calls, full tool/LLM/retrieval trace in
Governance via the RAM query id). Documents, Cases, Decision Studio, and the
governance seed metrics stay simulated until those SAS pieces are wired —
`/api/meta.capabilities` reports which is which, and the header badge switches
to **LIVE · SAS RAM** automatically.

Check `https://<sas-service>/api/health` — it reports whether the backend can
reach RAM and resolve the agent, with the error message if not.

## MCP servers (needed by the RAM agent — see docs/RAM_INTEGRATION.md)

The RAM agent needs its action tools reachable. Two options:

- **GHCR images in RAM (recommended):** the GitHub Actions workflow
  (`.github/workflows/publish-mcp.yml`) publishes
  `ghcr.io/raedaldweik/moce-mcp-tools` and `ghcr.io/raedaldweik/moce-verify-claims`
  on every push that touches `mcp/**`. RAM pulls them directly as
  **Container MCP Server** templates — nothing to deploy on Railway.
- **Railway-hosted (if RAM can't pull GHCR):** create two more services from
  this repo, setting **Settings → Build → Dockerfile path** to
  `mcp/moce_tools/Dockerfile` and `mcp/verify_claims/Dockerfile` respectively.
  Set `MOCE_BACKEND_URL` on `moce-mcp-tools` to the demo service's URL.
  Generate domains and register each in RAM as a **Remote MCP Server**
  (transport *Streamable HTTP*, URL `https://<domain>/mcp`).

## Updating

Push to the tracked branch — Railway redeploys automatically. `↺ Reset` in the
app restores seed data at any time (state is in-memory by design: every demo
starts clean after a restart/redeploy).

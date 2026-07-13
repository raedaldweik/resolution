# Business rules on SAS Intelligent Decisioning — via the sas-mcp-server MCP

This makes the eligibility decision **real**: the rules live in SAS Intelligent
Decisioning (ID), are published to the Micro Analytic Score service (MAS), and
the demo executes them through the **sas-mcp-server**'s `score_data` MCP tool.

```
UI → backend → engine/decisioning.execute_flow
                  └─ sas_id.py ──MCP streamable HTTP──▶ sas-mcp-server
                                                          └─ POST /microanalyticScore/
                                                             modules/{module}/steps/{step}
                                                             (SAS Viya · MAS)
```

Everywhere a decision is executed — the chat agent's `run_eligibility_flow`
tool, the Decision Studio test runner, the eligibility re-assessment after
document verification — the same path is used, and the result is stamped
`executedOn: SAS Intelligent Decisioning — MAS module '<name>' via sas-viya-mcp`
so you can prove on stage that the outcome came from Viya. If the MCP server is
unreachable, the demo falls back to the in-process mirror and says so in
`executedOn` (check `/api/health → sasDecisioning`).

## Step 1 — Author the rule set in SAS Intelligent Decisioning

SAS Viya → **Intelligent Decisioning** → New **Rule Set**
`Inflation Allowance Eligibility` with **exactly these input variables** (the
demo sends them by name):

| Variable | Type | Example |
|---|---|---|
| `monthlyIncomeAED` | Decimal | 23500 |
| `nationality` | Character(3) | `UAE` |
| `familySize` | Decimal | 5 |
| `verifiedWithinMonths` | Decimal | 0 |

Output variables: `outcome` Character(16), `confidence` Decimal.
(Other names work too — the demo maps any output containing
*outcome/eligib/decision* and *confidence/probab/score*.)

Rules (mirroring the demo's Decision Studio view):

1. `INC-001` — if `nationality NE 'UAE'` → `outcome = 'INELIGIBLE'`
2. `INC-002` — if `familySize < 1` → `outcome = 'INELIGIBLE'`
3. `INC-004` — if `monthlyIncomeAED > 25000` → `outcome = 'INELIGIBLE'`  *(the editable threshold)*
4. `INC-007` — if `verifiedWithinMonths > 12` → `outcome = 'INELIGIBLE'`
5. `OUT-001` — if `outcome = ''` (nothing fired) → `outcome = 'ELIGIBLE'`; `confidence = 0.93`

Then create a **Decision** `Inflation Allowance Eligibility Flow` containing the
rule set (a bare rule set can also be published directly).

## Step 2 — Publish to MAS

In the decision (or rule set): **Publish → Destination: SAS Micro Analytic
Score service (maslocal)** → name the module **`inflation_allowance_eligibility`**.

Validate it in ID's publishing-validation panel, or from any REST client:

```
POST {viya}/microAnalyticScore/modules/inflation_allowance_eligibility/steps/execute
{"inputs": [{"name": "monthlyIncomeAED", "value": 23500},
            {"name": "nationality", "value": "UAE"},
            {"name": "familySize", "value": 5},
            {"name": "verifiedWithinMonths", "value": 0}]}
```

> Module and step ids are case-sensitive and lowercased by MAS. If you named
> things differently, list modules via the MCP tool `list_models_and_decisions`
> or `GET /microAnalyticScore/modules`, and check the step id (decisions
> publish with step `execute`; some model types use `score`).

## Step 3 — Run the sas-mcp-server (direct HTTP mode)

From your `raedaldweik/sas-mcp-server` clone (already configured with
`VIYA_ENDPOINT`, `VIYA_REFRESH_TOKEN`, `CLIENT_ID=sas-mcp`, `SSL_VERIFY`):

```bash
export MCP_API_KEY="pick-a-strong-key"     # protects the endpoint
uv run app-http-direct                     # serves http://<host>:8134/mcp
```

Anywhere that can reach Viya works (a VM, your laptop with a tunnel, a
container). Scope it down for the demo if you like:
`SCOPE_ENFORCE=true`, `ALLOWED_DECISIONS=inflation_allowance_eligibility`.

## Step 4 — Point the demo at it

On the backend (Railway service variables, or local shell):

| Variable | Value |
|---|---|
| `SAS_MCP_URL` | `http://<host>:8134/mcp` |
| `SAS_MCP_API_KEY` | the `MCP_API_KEY` you set on the server |
| `SAS_ID_MODULE` | `inflation_allowance_eligibility` (default) |
| `SAS_ID_STEP` | `execute` (default; use `score` for model modules) |

Verify: `GET /api/health` → `sasDecisioning: {enabled: true, ok: true}`.
Then open **Decision Studio → Run decision flow** — the result now shows a gold
**⚡ SAS Intelligent Decisioning — MAS module … via sas-viya-mcp** badge, and the
header badge appends **+ SAS Intelligent Decisioning** when the Claude agent is
also enabled.

## What stays where

| Piece | Live on SAS | Still simulated |
|---|---|---|
| Decision outcome + confidence | ✅ MAS via MCP | — |
| Per-rule fire trace in the UI | — | ✅ local mirror (ID's own rule-fire analysis lives in ID) |
| No-code edit + publish in Decision Studio | — | ✅ (edit the real threshold in ID's UI; Tier-7 decisioning tools can automate this later) |
| DS2 preview | — | ✅ illustrative |

Keep the demo's `INC-004` threshold visually in sync with the real rule set —
or edit the real one in ID and let MAS disagree with the mirror on stage: the
`executedOn` badge makes it obvious which engine decided.

## Troubleshooting

- `sasDecisioning.ok:false, error: 401/403` — refresh token expired: re-run
  `sas-viya auth login` / regenerate the refresh token on the MCP server.
- `error: score_data tool not exposed` — the server is running in a tier
  configuration without MAS tools; unset `MCP_TIERS` or include the scoring tier.
- `404 module not found` — module name mismatch: MAS lowercases names
  (`inflation_allowance_eligibility`), check `GET /microAnalyticScore/modules`.
- Railway → on-prem Viya: the MCP server must be reachable from Railway
  (public DNS or a tunnel like Cloudflare/ngrok). TLS with a self-signed cert:
  put the MCP server behind the tunnel's TLS, not raw self-signed HTTPS.

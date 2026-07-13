# MoCE Agent Ecosystem — Interactive Demo

A stage-ready demo of the four-agent ecosystem from the MoCE RFP (Enterprise Agentic AI
Platform & AI Agents), **tailored to the SAS architecture it will run on** — SAS Retrieval
Agent Manager (RAM) + SAS Viya (Intelligent Decisioning, Workflow, Model governance).

It runs at three levels of "real", switched purely by environment variables:

| Level | Enable with | Chat engine | Business rules |
|---|---|---|---|
| **Simulation** | nothing (default) | deterministic script — zero-risk, offline | in-process mirror |
| **Claude agent** | `ANTHROPIC_API_KEY` | **real agentic loop on the Claude API** (`claude-opus-4-8`): live triage, tool calls, grounded answers, `verify_claims` gate | in-process mirror |
| **SAS live** | `APP_MODE=sas` + RAM vars / `SAS_MCP_URL` | **SAS RAM agent** | **SAS Intelligent Decisioning (MAS)** via the `sas-mcp-server` MCP |

`SAS_MCP_URL` is independent of the chat mode — set it in any level and every eligibility
decision executes on the real published SAS ID module (the result is stamped `executedOn`
so you can prove it on stage). Setup: **[docs/SAS_ID_SETUP.md](docs/SAS_ID_SETUP.md)**.

## The golden path (≈ 15 minutes on stage)

One story travels through all four agents — **Fatima's Inflation Allowance**:

1. **Citizen Portal** — sign in with UAEPass (mock), ask *"Why did my inflation allowance
   payment stop?"* (English or Arabic, full RTL). The Customer Resolution agent investigates:
   identity → benefit record (SUSPENDED, verification expired) → cited policy answer.
2. **Query triage** — ask *"What documents do I need to apply?"* first: the agent triages the
   contact (many "complaints" are really questions) as a **QUERY** and answers it instantly from
   the knowledge base with citations — **no case opened**. Complaint markers route to investigation
   instead; the triage decision is visible on every answer and in the Governance "queries deflected" KPI.
3. **Upload the scanned salary certificate** (suggestion chip). The Document Processing agent
   runs OCR → classification (96%) → schema-driven extraction. One field (income, 74%) falls
   below its threshold → routed to human review. **HITL demonstrated, not claimed.**
3. **Document Review** — reviewer sees the annotated certificate, corrects the field,
   approves. The Resolution agent resumes automatically.
4. **Back in the Portal** — the Knowledge & Decision agent has re-assessed eligibility via the
   decision flow (ELIGIBLE, 93%) and proposes: reinstate + AED 7,050 back-pay. Confirm →
   reinstatement executes within authority, SMS sent, case opened for the back-pay.
5. **Case Management** — two-stage approval (Social Worker → Social Auditor). Stage-2 approval
   releases the back-pay and notifies Fatima in her chat. The Learning-to-Autonomy tracker
   updates (alignment vs the 90% / 95% gates).
6. **The hallucination beat** — ask *"Will I also get the Eid bonus with my back-pay?"*
   The drafted reply contains an unverifiable claim → `verify_claims` **blocks the response**,
   answers honestly with only verified amounts, and escalates to the Contact Center.
7. **Decision Studio** — run the flow for Ahmed (income 27,000) → INELIGIBLE. Change the
   income threshold 25,000 → 30,000, publish v4 (**no code, no vendor, 90 seconds**), re-run →
   ELIGIBLE. Version history + generated DS2 score code shown.
8. **Governance** — every answer's full reasoning trace (tool calls, LLM calls, retrievals,
   guardrails, token cost), confidence distributions, hallucination rate vs the ≤ 0.5% target.

## Run it

```bash
# backend (serves the built frontend too)
cd backend
pip install -r requirements.txt
uvicorn main:app --port 8000

# frontend — dev mode (optional; otherwise build once)
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to :8000)
# or: npm run build  → then http://localhost:8000 serves everything
```

Docker: `docker build -t moce-demo . && docker run -p 8000:8000 moce-demo`

**Demo tips:** the sidebar footer lists the golden-path order. `↺ Reset demo` restores the
seed state. The scripted engine is deterministic — same clicks, same show, no Wi-Fi risk.
For the live version: `export ANTHROPIC_API_KEY=sk-ant-…` before starting the backend and
the chat becomes a genuine Claude agentic loop (the header badge flips to **LIVE · Claude
agent**); add `SAS_MCP_URL` / `SAS_MCP_API_KEY` and the decision flow runs on real
SAS Intelligent Decisioning.

## What becomes what — the SAS swap map

| Demo module (simulation) | Production component |
|---|---|
| `backend/engine/resolution.py` — orchestrator, intents, authority-limited actions | **SAS RAM orchestrator agent** (A2A to agents 1 & 2) + allow-listed MCP action tools |
| `backend/engine/documents.py` — OCR/classify/extract + review queue | **SAS RAM ingestion** (PaddleOCR ar+en) + VTA classifier + schema-constrained extraction agent |
| `backend/engine/knowledge.py` — retrieval + recommendation contract | **SAS RAM agent** over MoCE policy collections (real citations) |
| `backend/engine/decisioning.py` — versioned rule sets, publish, rule-fire trace, DS2 preview | **SAS Intelligent Decisioning** → MAS via `sas-mcp-server` `score_data` — **already wired**: set `SAS_MCP_URL` (docs/SAS_ID_SETUP.md) |
| `backend/engine/cases.py` — two-stage approval + alignment tracking | **SAS Workflow Manager** (BPMN) + CAS alignment mart + VA dashboard |
| `backend/engine/tracer.py` — toolCalls / llmCalls / retrievalCalls / guardrails | **SAS RAM query telemetry** (`/toolCalls`, `/llmCalls`, `/retrievalCalls` by `parentQueryId`) — same shapes, drop-in |
| Scripted bilingual answers | **UAE sovereign LLM** on on-prem GPUs (RAM is BYO-model) |
| `store.py` seed data (citizens, benefits, payments) | Ministry registries / Dynamics 365 via DB-Connector & OpenAPI MCP servers |
| Document type registry (`doc_schemas`) | Survives as-is — the ministry-owned, no-code schema registry |
| `verify_claims` guardrail | A real MCP tool checking draft claims against session tool results |

The REST surface (`/api/*`) is designed to survive the swap: the frontend does not change.

## Deploying — the versions on Railway

| Service | Variables | What runs |
|---|---|---|
| `moce-demo` | none | fully self-contained scripted demo — no SAS, no keys |
| `moce-demo-claude` | `ANTHROPIC_API_KEY` (+ optional `SAS_MCP_*`) | real Claude agentic chat; rules on SAS ID if the MCP vars are set |
| `moce-demo-sas` | `APP_MODE=sas` + RAM vars | chat through a live **SAS RAM agent** (answers, citations, traces) |

Full steps: **[docs/DEPLOY_RAILWAY.md](docs/DEPLOY_RAILWAY.md)**.
RAM wiring + MCP package publishing (GHCR): **[docs/RAM_INTEGRATION.md](docs/RAM_INTEGRATION.md)** —
the `mcp/` folder ships two MCP servers (`moce-mcp-tools`, `moce-verify-claims`) that GitHub Actions
publishes as container images for RAM to pull.

## Layout

```
backend/          FastAPI app + simulated SAS layer (engine/) + seed data (store.py)
                  live_ram.py — SAS-live adapter (APP_MODE=sas → RAM agent)
                  llm_agent.py — real Claude agentic loop (ANTHROPIC_API_KEY)
                  sas_id.py — SAS Intelligent Decisioning via sas-mcp-server MCP (SAS_MCP_URL)
frontend/         React + Vite + Tailwind — six views:
                  Citizen Portal · Contact Center · Document Review ·
                  Case Management · Decision Studio · Governance
mcp/              MCP servers for RAM (published to GHCR by GitHub Actions):
                  moce_tools (action tools) · verify_claims (hallucination gate)
docs/             DEPLOY_RAILWAY.md · RAM_INTEGRATION.md · SAS_ID_SETUP.md
```

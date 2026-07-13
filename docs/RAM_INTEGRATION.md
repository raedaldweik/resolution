# Wiring the demo to SAS RAM — full integration playbook

This is the step-by-step path from the simulation to a live SAS build: publish
the MCP servers as packages, register them in RAM, build the collections and
agents, and point the UI at the orchestrator. Steps reference the views in the
*SAS Retrieval Agent Manager: User's Guide* (2026.06).

```
UI (Railway, APP_MODE=sas)
   └─ RAM orchestrator agent  "MoCE Customer Resolution"
        ├─ A2A → agent "MoCE Knowledge & Decision"   (collections + decisioning tools)
        ├─ A2A → agent "MoCE Document Processing"    (doc pipeline; phase 2)
        └─ MCP tools:
             ├─ moce-demo-tools      (ghcr.io/raedaldweik/moce-mcp-tools)
             ├─ moce-verify-claims   (ghcr.io/raedaldweik/moce-verify-claims)
             └─ sas-viya-mcp         (raedaldweik/sas-mcp-server, direct HTTP mode)
```

## Step 0 — Publish the MCP packages (GitHub)

The repo ships two MCP servers under `mcp/` plus a GitHub Actions workflow
(`.github/workflows/publish-mcp.yml`) that builds and pushes both images to
GitHub Container Registry on every push touching `mcp/**`:

- `ghcr.io/raedaldweik/moce-mcp-tools` — citizen/benefit/case action tools
  (get_citizen_profile, get_payment_history, get_case_status,
  run_eligibility_flow, list_open_escalations), calling the deployed demo
  backend (`MOCE_BACKEND_URL`).
- `ghcr.io/raedaldweik/moce-verify-claims` — the hallucination gate
  (extract_claims, verify_claims → PASS/BLOCK verdict + instruction).

One-time setup:
1. Push the branch → the workflow runs (check the repo's **Actions** tab).
2. GitHub → your profile → **Packages** → each package → **Package settings →
   Change visibility → Public** (or give RAM registry credentials instead).
3. Note the image URLs — RAM pulls them in Step 2.

The third server is your **sas-mcp-server fork** (Viya code execution, CAS
data, MAS scoring, and the Tier-7 Intelligent Decisioning tools once the
`upstream-main` merge lands). Run it in **direct HTTP mode** (`uv run
app-http-direct`, `VIYA_REFRESH_TOKEN` + `MCP_API_KEY` in env) anywhere that
reaches Viya, or containerize it the same way.

## Step 1 — Knowledge base (RAM: Sources → Collections)

1. **Sources view** — upload the MoCE policy corpus (the demo's three policy
   documents exist as text in `backend/store.py::_seed_policies`; for the real
   thing use the actual Inflation Allowance policy PDFs, Arabic + English).
   Tag by program (`inflation-allowance`) and add custom metadata columns
   (article, effective date).
2. **Collections view** — create collection **"MoCE Policy Library"**; add the
   sources. In the configuration's **Text Extraction tab**: *Enable OCR* →
   PaddleOCR, language `ara` (add `eng` config for English docs); enable
   *Export tables* (Markdown).
3. Run **vectorization**, then a **user evaluation test** (Chapter 7) with
   bilingual Q&A pairs — e.g. "What documents are required to apply?" /
   "ما المستندات المطلوبة؟" — and select the winning configuration as
   **champion**. Agents can only use champion collections.

## Step 2 — Register the MCP tool servers (RAM: Code Templates → MCP Tools)

For each of the three servers:

1. **Code Templates view** → **Container MCP Server** (for the two GHCR
   images) — image `ghcr.io/raedaldweik/moce-mcp-tools:latest`, transport
   *Streamable HTTP*, port `8200`, base path `/mcp`; add environment variable
   `MOCE_BACKEND_URL` = your Railway demo URL. Same for
   `moce-verify-claims:latest` (port `8300`, no env vars). **Publish** the
   templates (Chapter 8).
   - Alternative if RAM can't pull GHCR: deploy the two servers on Railway
     (see DEPLOY_RAILWAY.md) and register them as **Remote MCP Server**
     catalog entries instead (URL `https://<domain>/mcp`, auth None/API key).
2. For **sas-viya-mcp**: **MCP Tools view** → new tool server → **Catalog →
   Remote MCP Server** → transport *Streamable HTTP*, URL
   `http://<host>:8134/mcp`, authentication *API Key* = your `MCP_API_KEY`.
3. **MCP Tools view** → create a tool server from each template → **Start** it.
   Verify the tools list populates.

## Step 3 — Knowledge & Decision agent (RAM: Agents)

1. **Agents view → Create an Agent** → name **"MoCE Knowledge & Decision"**.
2. Add an **agent experiment** (tools-based):
   - System prompt: answer only from retrieved policy with citations; return
     the structured contract `{recommendation, rationale, evidence, confidence,
     risk}` when asked for an eligibility assessment; call the decisioning
     tool for the deterministic outcome; never make final decisions.
   - **LLMs tab**: the sovereign/на-prem LLM registered in RAM.
   - **Tools tab**: allow only `sas-viya-mcp` scoring/decisioning tools.
   - **Collections tab**: "MoCE Policy Library" (enable agentic retrieval).
3. **Evaluate** the experiment (user evaluation test), pick **champion**, **Start**.
4. **A2A Agent Card tab** — description: *"Assesses Inflation Allowance
   eligibility and answers policy questions with citations."* Add skills
   (`policy-qa`, `eligibility-assessment`) and query examples ("Is a citizen
   with income AED 23,500 eligible?", "What does Art 7.1 say about back-pay?").
   The orchestrator routes by this card — write it well.

## Step 4 — Customer Resolution orchestrator (RAM: Agents)

1. **Agents view → Create an Agent Orchestrator** → **"MoCE Customer
   Resolution"** (this exact name goes in the UI's `RAM_AGENT_NAME`).
2. Experiment (start with **Basic no-code**; move to a **Code template
   experiment** for custom logic later):
   - System prompt encoding the demo's flow — triage first (QUERY → answer
     from the Knowledge agent with citations, no case; COMPLAINT →
     investigate via tools), act only within authority, and **always** run
     `extract_claims` + `verify_claims` on the draft before answering; on
     BLOCK verdict, answer with the verified subset and escalate.
   - **Agents tab**: assign "MoCE Knowledge & Decision" (A2A; only agents
     with a configured card appear).
   - Attach the `moce-demo-tools` and `moce-verify-claims` tool servers.
3. Evaluate → champion → **Start**.
4. Test in RAM's **Chat view** first: "Why did citizen 784-1985-9384756-1's
   inflation allowance stop?" should trigger profile + payment tools, policy
   retrieval, and a cited answer.

## Step 5 — Point the UI at RAM

On the Railway **SAS service** (see DEPLOY_RAILWAY.md): `APP_MODE=sas`,
`RAM_API_URL`, `RAM_AGENT_NAME="MoCE Customer Resolution"`, plus credentials.
The header badge flips to **LIVE · SAS RAM**; chat answers, citations, and the
Governance trace inspector now come from RAM (`/query`, `/toolCalls`,
`/llmCalls`, `/retrievalCalls` — the same shapes the simulation mirrors).

## Step 6 — Phase 2 wiring (the remaining simulated capabilities)

| Demo capability | SAS target | Path |
|---|---|---|
| Document Processing + HITL queue | RAM ingestion + VTA classifier + extraction agent | New RAM agent + `process_document` MCP tool; review queue stays in the demo backend |
| Decision Studio | SAS Intelligent Decisioning | Author the rule set/decision flow in ID, publish to MAS; swap `backend/engine/decisioning.py` calls for `sas-viya-mcp` `score_data` / Tier-7 tools |
| Two-stage case approval | SAS Workflow Manager | BPMN definition; approvals via workflow REST through an MCP tool |
| Governance metrics | RAM telemetry + CAS + Visual Analytics | Land llm/tool/retrieval calls in CAS; VA dashboard |

## Gotchas

- RAM agents must be **champion + started** before they answer; the UI's
  `/api/health` tells you if the agent can't be resolved.
- The orchestrator only sees agents **with a configured A2A card**.
- RAM's REST API has **no streaming** — answers arrive whole (the UI's
  activity feed handles the wait).
- GHCR images referenced by RAM must be **public** or RAM's container
  registry credentials must be configured in the template.
- Keep `MOCE_BACKEND_URL` pointing at the **simulation service** so RAM tools
  and the UI read/write the same demo data.

# MoCE Agent Ecosystem

Three agents on **SAS Retrieval Agent Manager** + one chat UI. Nothing else.

| Agent | What it is | Build sheet |
|---|---|---|
| **MoCE Document Processing** | Real OCR (tesseract ara+eng) via an MCP server: read a scanned document, extract fields, classify, summarize | [docs/agents/1-document-processing.md](docs/agents/1-document-processing.md) |
| **MoCE Knowledge & Policy** | RAG over the MoCE Policy Library (real u.ae / moce.gov.ae documents + 2 operational PDFs), cited answers | [docs/agents/2-knowledge-policy.md](docs/agents/2-knowledge-policy.md) |
| **MoCE Customer Resolution** | Orchestrator: record lookup + delegates to the two agents above + executes business rules on SAS Intelligent Decisioning through your Viya MCP | [docs/agents/3-customer-resolution.md](docs/agents/3-customer-resolution.md) |

The UI is the same app as `finance_ram_ui`, re-skinned to the MoCE gold
theme: a thin FastAPI proxy over the RAM REST API + a React chat. Point it at
your RAM, sign in, and whatever agents are started there appear in the
dropdown — you chat with the *real* agents and see their real tool / LLM /
retrieval traces per answer. No scripted answers anywhere.

## The storyline (one thread through all three agents)

**"Fatima's inflation allowance stopped."**

1. Ask **Customer Resolution** why → looks up her record, gets the rule from
   **Knowledge & Policy** (POL-2024-017 Art 6.2/4.2): suspended because income
   verification expired — *suspended, not cancelled* — and asks for a fresh
   salary certificate.
2. Hand it the scanned certificate (`knowledge_base/samples/`) → it delegates
   to **Document Processing**, which OCRs it for real: AED 23,500, 95%
   confidence.
3. It executes the published decision flow on **SAS Intelligent Decisioning**
   (`docs/DECISIONING_RULES.md`) → ELIGIBLE, reinstate, back-pay AED 7,050,
   two-stage approval — and explains exactly that, citing Art 7.1.
4. Ask about an "Eid bonus" → nothing verifiable in any record → it says so
   and refers to the contact centre instead of inventing an amount.
5. Change the income threshold in Intelligent Decisioning, republish, re-ask
   → the same agent decides differently. Business rules, no vendor, no code.

## Repo layout

```
backend/           FastAPI proxy over RAM (auth flows, async queries, traces, OCR /api/extract)
frontend/          React chat UI (agent dropdown, live activity, citations, query details)
mcp/document_processing/   OCR MCP server → ghcr.io/raedaldweik/moce-document-processing
mcp/verify_claims/         hallucination-gate MCP → ghcr.io/raedaldweik/moce-verify-claims
knowledge_base/    what goes in the RAG (real sources + 2 authored PDFs) + sample scan
docs/agents/       the three RAM build sheets
docs/DECISIONING_RULES.md  rule sets + decision flow for SAS Intelligent Decisioning
```

## Run the UI

```bash
cd backend && pip install -r requirements.txt
cp .env.example .env        # set RAM_API_URL (or RAM_MOCK=true to try the UI without RAM)
uvicorn main:app --port 8000
cd ../frontend && npm install && npm run dev    # http://localhost:5173
```

Docker (serves the built frontend on one port):
`docker build -t moce-ui . && docker run -p 8000:8000 -e RAM_API_URL=... moce-ui`

Railway: **New Project → Deploy from GitHub repo** — `railway.json` builds
the Dockerfile with `/api/health` as the health check; set `RAM_API_URL`
(+ auth vars from `backend/.env.example`) on the service. Pushing to the
tracked branch redeploys; the GitHub Action publishes the two MCP images to
GHCR on any `mcp/**` change (make the packages public after the first run so
RAM can pull them).

## Connecting to RAM — identical to finance_ram_ui

The backend is the **same RAM client as finance_ram_ui** (same code, same
variables). If your finance UI connects, this one connects with the *exact
same configuration*: **copy `backend/.env` from your working finance_ram_ui
project into `backend/.env` here** (or copy the service variables if it runs
on Railway) and restart. That's the whole setup.

The variables, from `backend/.env.example`:

| Variable | Required | Notes |
|---|---|---|
| `RAM_API_URL` | ✅ | e.g. `https://<host>/SASRetrievalAgentManager/api/v1` — without it the header shows *Not configured* |
| `RAM_VERIFY_SSL` | if self-signed | set `false` for self-signed certificates |
| *(nothing else)* | — | header shows **Sign in** → interactive login (Keycloak device code on standalone RAM, SASLogon paste-the-code on full Viya) |
| `RAM_TOKEN` | optional | static bearer token instead of interactive sign-in |
| `SAS_CLIENT_ID` / `SAS_CLIENT_SECRET` (+ `SAS_USERNAME`/`SAS_PASSWORD`) | optional | headless OAuth instead of interactive sign-in |

What the header pill means: **Not configured** → `RAM_API_URL` unset ·
**Sign in required** → URL set, click Sign in · **Connected** → talking to
RAM (the dropdown now lists your real agents) · **Mock mode** → `RAM_MOCK=true`
· **Backend offline** → check `GET /api/health`, it returns the exact error.

Attachments in chat are extracted server-side (PDF/DOCX/text; images are
OCR'd with the same tesseract engine as the Document Processing MCP) and
inlined into the query, since RAM's query API is text-only.

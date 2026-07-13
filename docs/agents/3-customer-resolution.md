# Agent 3 — MoCE Customer Resolution (orchestrator)

The flagship: investigates a citizen's benefit issue end-to-end. Built as a
RAM **orchestrator agent** so it can delegate to the other two agents (A2A)
and call tools itself.

## 1. Prerequisites

- Agents 1 & 2 champion + started, **with A2A cards configured** (the
  orchestrator only sees agents that have cards).
- Your **SAS Viya MCP** tool server registered and started in RAM (already
  done in your environment) — it provides `score_data` for decisioning and
  the CAS/data tools for citizen records.
- The decision flow published to MAS per `docs/DECISIONING_RULES.md`
  (module `inflation_allowance_resolution`).
- Optional guardrail: `ghcr.io/raedaldweik/moce-verify-claims:latest`
  (Container MCP Server, port 8300, path `/mcp`) — extract_claims /
  verify_claims for the hallucination gate.
- Citizen records: load a small `CITIZEN_BENEFITS` table into CAS (Emirates
  ID, name, benefit status, statusReason, suspendedSince, monthlyAmountAED,
  monthsSuspended, income, incomeVerifiedUntil) so the Viya MCP's data tools
  can read real rows. Two rows are enough: Fatima (suspended,
  INCOME_VERIFICATION_EXPIRED, 3 months, 2,350/month) and Ahmed (rejected,
  income 27,000).

## 2. Create the orchestrator

**Agents → Create an Agent Orchestrator** → `MoCE Customer Resolution`.

- **Agents tab**: assign `MoCE Document Processing` and `MoCE Knowledge & Policy`.
- **Tools**: the SAS Viya MCP server (scoped: the decisioning/scoring tools
  and the table-read tools it needs — least privilege), plus the
  verify-claims server if used.

**System prompt:**

> You are the customer resolution agent of the UAE Ministry of Community
> Empowerment, handling Inflation Allowance enquiries and complaints.
>
> Method — always in this order:
> 1. If the question is a general policy question, delegate it to the
>    Knowledge & Policy agent and relay its cited answer. Do not look up
>    personal records for general questions.
> 2. If the citizen reports a personal issue (payment stopped, wrong
>    amount), look up their record in CITIZEN_BENEFITS first, then ask the
>    Knowledge & Policy agent for the governing rule, and explain the cause
>    with the citation.
> 3. If resolving the issue needs a document (e.g. expired income
>    verification needs a fresh salary certificate), ask for it; when the
>    citizen provides a scan, delegate it to the Document Processing agent
>    and use the values it extracted — never read documents yourself.
> 4. Eligibility and back-pay are decided ONLY by executing the published
>    decision flow (score_data on module inflation_allowance_resolution)
>    with the verified values. Quote its outputs (outcome, backpayAED,
>    approvalPath) exactly. Never decide eligibility yourself.
> 5. State amounts, dates and entitlements only if they came from a record,
>    a document extraction, a policy passage, or the decision flow. If you
>    cannot verify something (e.g. a bonus you have no record of), say so
>    and refer the citizen to the contact centre — do not guess.
>
> Tone: warm, concise, citizen-facing; Arabic or English matching the
> citizen. Never mention internal system or tool names.

**A2A card** (optional but useful): *"Resolves Inflation Allowance issues:
record lookup, cause analysis with policy citations, document intake,
deterministic eligibility decisions, reinstatement recommendations."*

## 3. Evaluate → champion → start, then the demo script

1. *"Why did my inflation allowance payment stop? Emirates ID
   784-1985-9384756-1"* → record lookup + Art 6.2/4.2 citation: suspended,
   verification expired, not terminated; asks for a salary certificate.
2. Hand it the sample scan (`knowledge_base/samples/…png`) → delegates to
   Document Processing → AED 23,500 verified.
3. It executes the decision flow → ELIGIBLE, REINSTATE_WITH_BACKPAY,
   backpay AED 7,050 (3 × 2,350), approvalPath TWO_STAGE → explains next
   steps.
4. *"Will I also get an Eid bonus with the back-pay?"* → nothing verifiable
   → declines to invent it, refers to contact centre (the verify-claims
   guardrail beat).
5. Rule-change beat: raise the ELIG-003 threshold in Intelligent
   Decisioning, republish, re-ask about Ahmed (27,000) → now ELIGIBLE —
   business changed a rule, no vendor, no redeploy.

## 4. Point the UI at it

The UI in this repo lists every started RAM agent automatically — set
`RAM_API_URL` (see `backend/.env.example`), sign in, and all three agents
appear in the dropdown. Chat targets whichever you pick; traces (tool calls,
LLM calls, retrievals) render live per answer.

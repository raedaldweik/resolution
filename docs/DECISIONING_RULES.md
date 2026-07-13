# Business rules for SAS Intelligent Decisioning

The deterministic core of the **MoCE Customer Resolution** agent. Author this
in SAS Intelligent Decisioning, publish it to MAS, and the agent executes it
through your SAS Viya MCP's `score_data` tool (already connected to RAM).

Everything below is copy-paste ready for the chat session that has your Viya
MCP connected. The rules implement POL-2024-017 (see
`knowledge_base/POL-2024-017_…pdf`): Art 4.2 eligibility, Art 7.1
reinstatement + back-pay, Art 8.4 two-stage approval.

---

## Rule set 1 — `Inflation Allowance Eligibility`

**Input variables**

| Name | Type | Example | Meaning |
|---|---|---|---|
| `monthlyIncomeAED` | decimal | 23500 | verified gross monthly household income |
| `nationality` | character(3) | `UAE` | head of household nationality |
| `familySize` | decimal | 5 | household members incl. head |
| `verifiedWithinMonths` | decimal | 0 | months since income verification (0 = just verified) |

**Output variables**: `outcome` character(16), `reasonCode` character(32), `confidence` decimal

**Rules (fire in order; first failure wins)**

| Rule | Condition | Then |
|---|---|---|
| ELIG-001 Nationality gate | `nationality NE 'UAE'` | `outcome='INELIGIBLE'`, `reasonCode='NOT_UAE_NATIONAL'` |
| ELIG-002 Head of household | `familySize < 1` | `outcome='INELIGIBLE'`, `reasonCode='NO_HOUSEHOLD'` |
| ELIG-003 Income threshold (Art 4.2 / Sch. B) | `monthlyIncomeAED > 25000` | `outcome='INELIGIBLE'`, `reasonCode='INCOME_ABOVE_THRESHOLD'` |
| ELIG-004 Verification recency (Art 4.2) | `verifiedWithinMonths > 12` | `outcome='INELIGIBLE'`, `reasonCode='VERIFICATION_EXPIRED'` |
| ELIG-005 Default | `outcome = ''` (nothing fired) | `outcome='ELIGIBLE'`, `reasonCode='ALL_CONDITIONS_MET'`, `confidence=0.93` |

`25000` (ELIG-003) is the business-editable threshold — the "change a rule
without a vendor" demo beat: edit it in the ID interface, republish, and the
agent's very next decision uses the new version.

## Rule set 2 — `Reinstatement & Back-pay` (Art 7.1 + 8.4)

**Input variables**

| Name | Type | Example | Meaning |
|---|---|---|---|
| `outcome` | character(16) | `ELIGIBLE` | from rule set 1 |
| `suspensionReason` | character(32) | `INCOME_VERIFICATION_EXPIRED` | why payment stopped |
| `monthsSuspended` | decimal | 3 | instalments withheld |
| `monthlyAmountAED` | decimal | 2350 | Schedule B entitlement |

**Output variables**: `action` character(24), `backpayMonths` decimal, `backpayAED` decimal, `approvalPath` character(16)

**Rules**

| Rule | Condition | Then |
|---|---|---|
| REIN-001 Reinstate (Art 7.1) | `outcome='ELIGIBLE'` and `suspensionReason='INCOME_VERIFICATION_EXPIRED'` | `action='REINSTATE_WITH_BACKPAY'` |
| REIN-002 Back-pay cap (Art 7.1: max 6 months) | after REIN-001 | `backpayMonths = MIN(monthsSuspended, 6)`; `backpayAED = backpayMonths * monthlyAmountAED` |
| REIN-003 Approval routing (Art 8.4) | `backpayAED > 5000` | `approvalPath='TWO_STAGE'` (Social Worker → Social Auditor) |
| REIN-004 Small amounts | `backpayAED <= 5000` | `approvalPath='AUTO'` |
| REIN-005 Not eligible | `outcome NE 'ELIGIBLE'` | `action='MAINTAIN_SUSPENSION'`, `backpayAED=0`, `approvalPath='NONE'` |

## Decision flow — `Inflation Allowance Resolution`

Chain the two rule sets: **Eligibility → Reinstatement & Back-pay**.
Publish the flow to **MAS** as module **`inflation_allowance_resolution`**
(destination *SAS Micro Analytic Score service*). MAS lowercases module
names; the execute step id is `execute`.

## Validate the published module

```
POST {viya}/microAnalyticScore/modules/inflation_allowance_resolution/steps/execute
{"inputs": [
  {"name": "monthlyIncomeAED",      "value": 23500},
  {"name": "nationality",           "value": "UAE"},
  {"name": "familySize",            "value": 5},
  {"name": "verifiedWithinMonths",  "value": 0},
  {"name": "suspensionReason",      "value": "INCOME_VERIFICATION_EXPIRED"},
  {"name": "monthsSuspended",       "value": 3},
  {"name": "monthlyAmountAED",      "value": 2350}
]}
```

Expected: `outcome=ELIGIBLE`, `action=REINSTATE_WITH_BACKPAY`,
`backpayMonths=3`, `backpayAED=7050`, `approvalPath=TWO_STAGE`.

Second test — Ahmed (income 27,000): expect `outcome=INELIGIBLE`,
`reasonCode=INCOME_ABOVE_THRESHOLD`, `action=MAINTAIN_SUSPENSION`.

## The two demo moments this enables

1. **Deterministic decisions**: the Customer Resolution agent never "decides"
   eligibility with the LLM — its trace shows a `score_data` call to
   `inflation_allowance_resolution` and quotes the rule output.
2. **No-code rule change**: raise ELIG-003 to 30,000 in the ID interface,
   republish, re-ask the agent about Ahmed → ELIGIBLE, same conversation,
   no redeployment of anything.

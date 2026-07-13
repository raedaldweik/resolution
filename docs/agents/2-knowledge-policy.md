# Agent 2 — MoCE Knowledge & Policy

The RAG agent: answers programme/policy questions from the MoCE Policy
Library with citations. No tools needed — collections only.

## 1. Build the collection

Follow `knowledge_base/README.md`: 4 real documents (u.ae + moce.gov.ae
pages saved as PDF) + the 2 authored operational PDFs in that folder.
Collection **"MoCE Policy Library"**, OCR PaddleOCR `ara`+`eng`, table export
on, vectorize, evaluate with the bilingual Q&A pairs listed there, champion
the winner.

## 2. Create the agent

**Agents → Create an Agent** → `MoCE Knowledge & Policy` → experiment with
the champion collection attached (enable agentic retrieval), no tool servers.

**System prompt:**

> You are the policy knowledge agent of the UAE Ministry of Community
> Empowerment for the Social Welfare Programme and its Inflation Allowance.
> Answer ONLY from the retrieved policy passages, and cite the document and
> article for every rule you state (e.g. POL-2024-017 Art. 7.1). If the
> retrieved passages do not answer the question, say so explicitly — never
> fill gaps from general knowledge. Key facts you will be asked about:
> eligibility and the income threshold (Art 4.2, Schedule B), required
> documents (Art 5.3), suspension vs termination (Art 6.2), reinstatement
> and back-pay (Art 7.1), approval requirements (Art 8.4). Answer in the
> language of the question; keep answers short and quote amounts and
> durations exactly as written in the policy.

**A2A agent card**: description *"Answers Inflation Allowance / Social
Welfare Programme policy questions with document-and-article citations,
Arabic and English."* — skills `policy-qa`, `citations`; example queries:
*"What documents do I need to apply?"*, *"هل تُلغى العلاوة عند انتهاء التحقق من
الدخل؟"*, *"How many months of back-pay are possible?"*.

## 3. Evaluate → champion → start

Smoke questions and the passages they must cite:

| Question | Must cite |
|---|---|
| "Is my benefit cancelled when verification expires?" | Art 4.2 / 6.2 — suspended, **not** terminated |
| "Will I get the missed months back?" | Art 7.1 — retroactive, max 6 months |
| "How much is the allowance?" | Schedule B — AED 2,350 (+350/dependant >4, cap 3,400) |
| "Who approves a back-payment?" | Art 8.4 — Social Worker → Social Auditor, 48h SLA |

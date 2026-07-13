# MoCE Policy Library — what goes in the RAG

This is the corpus for the **MoCE Knowledge & Policy** agent's collection in
SAS RAM. Six documents: four real, publicly published ones you download, plus
the two operational PDFs in this folder that carry the demo's working rules.

## 1. Real documents (download these)

| # | Document | Where | Why it's in the corpus |
|---|---|---|---|
| 1 | **Social welfare programme for low-income citizens** (EN + AR page) | [u.ae — social welfare for low-income nationals](https://u.ae/en/information-and-services/social-affairs/social-welfare/social-welfare-programmes/social-welfare-for-low-income-nationals) | The official programme description: AED 25,000/month income threshold, the allowance types (inflation allowance for fuel/food/electricity & water, housing, unemployed 45+, university), UAE PASS application |
| 2 | **Social welfare programmes** (overview page) | [u.ae — social welfare programmes](https://u.ae/en/information-and-services/social-affairs/social-welfare/social-welfare-programmes) | Programme landscape + which ministry owns what |
| 3 | **Applying for Inflation Allowance** (service card) | [moce.gov.ae — applying-for-inflation-allowance](https://www.moce.gov.ae/en/w/applying-for-inflation-allowance) | The ministry's own service page: channels, steps, requirements — the agent should answer "how do I apply" from THIS |
| 4 | **Social Welfare Application** (service card) | [moce.gov.ae — social-welfare](https://www.moce.gov.ae/en/w/social-welfare) | The umbrella application service |

Save each page as PDF from your browser (both u.ae and moce.gov.ae block
data-centre scrapers, so do it from a normal connection — right-click → Print
→ Save as PDF, once in English and once in Arabic where available).

## 2. Operational documents (in this folder, ready to upload)

Real programmes never publish their internal thresholds — these two authored
PDFs stand in for the ministry's internal manuals and give the agents the
*specific* rules the storyline runs on. Bilingual (every article EN + AR),
with a proper text layer (no OCR needed, though PaddleOCR handles them fine):

- **`POL-2024-017_inflation_allowance_operations_manual.pdf`**
  - Art 2.4 — human review of automated decisions
  - Art 4.2 — eligibility: Emirati head of household, income ≤ AED 25,000, re-verify every 12 months, *suspension not termination*
  - Art 5.3 — required documents (Emirates ID, salary certificate ≤ 90 days, IBAN letter, family book), 10 working days
  - Art 6.2 — suspension causes incl. INCOME_VERIFICATION_EXPIRED
  - Art 7.1 — reinstatement + back-pay up to 6 months
  - Art 8.4 — two-stage approval (Social Worker → Social Auditor) for effects > AED 5,000, SLA 48h
  - Schedule B — AED 2,350/month base, AED 350 dependant supplement, AED 3,400 cap
- **`SOP-DOC-009_document_verification_procedures.pdf`**
  - Salary-certificate validity (90 days) and required contents
  - OCR confidence thresholds (income 90%, Emirates ID 95%, IBAN 95%…) → below threshold = human review
  - Verification recency (12 months) + renewal reminders
  - Reviewer turnaround (4 working hours) + audit trail

The demo storyline ("Fatima's allowance stopped") resolves entirely from
these two: cause (Art 6.2) → remedy (SOP §2) → decision (Art 4.2 / Sch. B) →
reinstatement + back-pay (Art 7.1) → approval path (Art 8.4).

## 3. Sample input (not for the collection)

`samples/salary_certificate_scanned.png` — a scanned salary certificate for
the Document Processing agent to OCR live (Fatima Al Mansoori, AED 23,500
gross, Emirates ID + IBAN + dates on it). Don't index it into the collection;
it's the demo *input*, not knowledge.

## RAM collection settings

Collection **"MoCE Policy Library"** → add all six documents.
Text extraction: **enable OCR (PaddleOCR)**, languages **ara + eng**; enable
table export (Markdown) so Schedule B survives chunking. Run vectorization,
then a user evaluation with bilingual Q&A pairs, e.g.:

- "What documents do I need to apply for the inflation allowance?" / "ما المستندات المطلوبة للتقديم؟" → Art 5.3
- "My payment stopped — is my benefit cancelled?" → Art 4.2 + 6.2 (suspended, not terminated)
- "Will I get the missed months back?" → Art 7.1 (yes, up to 6 months, after re-verification)
- "How much is the allowance?" / "كم قيمة العلاوة؟" → Schedule B

Mark the winning configuration **champion** — only champion collections are
usable by agents.

# Agent 1 — MoCE Document Processing

OCR + extraction + summarization of citizen documents. **Not** the RAG agent —
its knowledge is the document you hand it, read through a real OCR MCP.

## 1. Run the MCP server

Image: `ghcr.io/raedaldweik/moce-document-processing:latest` (built by the
repo's GitHub Action from `mcp/document_processing/` — tesseract with Arabic +
English inside). Tools, all real:

- `ocr_document(image_base64 | image_url, languages)` → text + mean confidence + low-confidence words
- `extract_fields(text)` → Emirates ID, IBAN (OCR-confusion-corrected), AED amounts, dates, phones, emails
- `classify_document(text)` → salary_certificate / emirates_id_card / iban_letter / family_book / utility_bill

## 2. Register in RAM

**Code Templates → Container MCP Server**: image above, transport
*Streamable HTTP*, port `8400`, path `/mcp`. Publish the template, then
**MCP Tools → create tool server from template → Start**, and confirm the
three tools list. (If RAM can't pull GHCR, deploy the image anywhere and
register it as a **Remote MCP Server** with URL `https://<host>/mcp`.)

**Optional environment variables** (set on the template in RAM):

| Variable | Default | What it does |
|---|---|---|
| `OCR_LANGUAGES` | `ara+eng` | default tesseract languages for `ocr_document` |
| `CUSTOM_FIELDS` | *(unset — defaults only)* | JSON object adding your own fields to `extract_fields`: `{"fieldName": "regex"}` |

`CUSTOM_FIELDS` example — add a passport number, a job title, and an issue
date on top of the built-in six (Emirates ID, IBAN, amounts, dates, phones,
emails):

```json
{"passportNumber": "\\b[A-Z]\\d{8}\\b",
 "jobTitle": "as ([A-Za-z ]+?) since",
 "issueDate": "Date of issue: (\\d{4}-\\d{2}-\\d{2})"}
```

Rules: custom fields are **added** to the defaults (reusing a default's name
overrides it); a regex **with a capturing group returns group 1**, otherwise
the whole match; an invalid regex is skipped (logged) and invalid JSON falls
back to defaults — the server never crashes on a bad value. The tool's result
lists `customFieldsActive` so you can see in the agent trace which extras are
configured. Restart the tool server in RAM after changing the variable.

## 3. Create the agent

**Agents → Create an Agent** → `MoCE Document Processing` → tools-based
experiment, no collections, only this tool server attached.

**System prompt:**

> You are the document processing agent of the UAE Ministry of Community
> Empowerment. When given a document image (base64 or URL), always work in
> this order: `ocr_document` → `classify_document` → `extract_fields`. Then
> summarize: document type, who it belongs to, the key values (amounts,
> dates, IDs), and the OCR mean confidence. Quote extracted values EXACTLY as
> returned by the tools — never correct, complete, or guess a value. If
> `meanConfidence` is below 90 or a financial field appears in
> `lowConfidenceWords`, state that the document needs human verification per
> SOP-DOC-009 instead of treating the value as final. Answer in the language
> of the request (Arabic or English).

**A2A agent card** (so the Customer Resolution orchestrator can call it):
description *"Reads scanned citizen documents (Arabic/English): OCR, document
type, key fields (Emirates ID, IBAN, salary amounts), with confidence
scores."* — skills `ocr`, `document-classification`, `field-extraction`;
example queries: *"Read this salary certificate and give me the gross monthly
income"*, *"ما نوع هذا المستند؟"*.

## 4. Evaluate → champion → start

Test in RAM chat with `knowledge_base/samples/salary_certificate_scanned.png`
(host it anywhere reachable and pass the URL, or paste base64): expect gross
income **AED 23,500**, Emirates ID **784-1985-9384756-1**, type
`salary_certificate`, and ~95% confidence.

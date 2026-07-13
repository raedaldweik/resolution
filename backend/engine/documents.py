"""Simulated Document Processing AI Agent (Agent 1).

Production swap: RAM ingestion with OCR (PaddleOCR ara+eng), a Visual Text
Analytics classification model, and a schema-driven extraction agent. The
document-type schema registry (store.doc_schemas) survives the swap as-is —
that is the ministry-owned, no-code part.
"""

from store import store, next_id
from engine.tracer import Trace

# The two bundled sample documents. "blurry" is scripted to produce one
# low-confidence field so the HITL review beat always lands.
SAMPLE_DOCS = {
    "salary_cert_clean": {
        "fileName": "salary_certificate_fatima.pdf", "quality": "clean",
        "fields": {
            "employee_name": {"value": "Fatima Al Mansoori", "confidence": 0.97},
            "employer_name": {"value": "Al Noor Trading LLC", "confidence": 0.96},
            "monthly_income": {"value": "23,500", "confidence": 0.95},
            "issue_date": {"value": "2026-07-02", "confidence": 0.94},
            "stamp": {"value": "Detected (Chamber of Commerce)", "confidence": 0.92},
        },
    },
    "salary_cert_blurry": {
        "fileName": "salary_certificate_fatima_scan.jpg", "quality": "blurry scan",
        "fields": {
            "employee_name": {"value": "Fatima Al Mansoori", "confidence": 0.94},
            "employer_name": {"value": "Al Noor Trading LLC", "confidence": 0.91},
            "monthly_income": {"value": "23,500", "confidence": 0.74},  # below 0.90 threshold
            "issue_date": {"value": "2026-07-02", "confidence": 0.88},
            "stamp": {"value": "Detected (Chamber of Commerce)", "confidence": 0.83},
        },
    },
}


def process_document(session_id: str, doc_key: str, citizen_id: str, lang: str = "en"):
    doc = SAMPLE_DOCS[doc_key]
    schema = store.doc_schemas["salary_certificate"]
    t = Trace("Document Processing Agent", "a2a", f"process_document({doc['fileName']})", session_id)
    t.tool("run_ocr", "doc-processing-mcp",
           {"file": doc["fileName"], "ocr": "PaddleOCR", "languages": ["ara", "eng"]},
           {"pages": 1, "textBlocks": 18, "tablesDetected": 1}, ms=1240)
    t.llm("classification",
          "Classify document against 20 registered MoCE document types…",
          "type=salary_certificate p=0.96 (schema v3)", 610, 42, 380)
    t.llm("schema-constrained extraction",
          f"Extract fields per schema salary_certificate v{schema['version']} as JSON…",
          "{employee_name:…, monthly_income:…}", 1380, 210, 940)

    fields, review_fields = [], []
    for f in schema["fields"]:
        ext = doc["fields"][f["key"]]
        needs_review = ext["confidence"] < f["threshold"]
        row = {"key": f["key"], "labelEn": f["labelEn"], "labelAr": f["labelAr"],
               "value": ext["value"], "confidence": ext["confidence"],
               "threshold": f["threshold"], "needsReview": needs_review}
        fields.append(row)
        if needs_review:
            review_fields.append(f["key"])

    result = {
        "documentId": next_id("DOC"), "fileName": doc["fileName"], "quality": doc["quality"],
        "docType": "salary_certificate", "docTypeName": schema["nameEn"],
        "docTypeNameAr": schema["nameAr"], "classificationConfidence": 0.96,
        "schemaVersion": schema["version"], "fields": fields,
        "validations": schema["validations"], "reviewRequired": bool(review_fields),
        "citizenId": citizen_id, "sessionId": session_id, "status": "",
    }

    if review_fields:
        result["status"] = "PENDING_REVIEW"
        store.review_queue.append({**result, "queuedAt": next_id("Q"),
                                   "reviewFields": review_fields, "reviewer": None})
        t.tool("route_to_review", "doc-processing-mcp",
               {"documentId": result["documentId"], "fields": review_fields,
                "reason": "field confidence below schema threshold"},
               {"queue": "doc-review", "position": len(store.review_queue)}, ms=45)
        t.done(f"Extraction complete; {len(review_fields)} field(s) below threshold -> HITL review", "review")
    else:
        result["status"] = "EXTRACTED"
        t.done("Extraction complete; all fields above threshold")
    result["traceId"] = t.rec["traceId"]
    return result


def complete_review(document_id: str, corrections: dict, reviewer: str):
    item = next((d for d in store.review_queue if d["documentId"] == document_id), None)
    if not item:
        raise ValueError("Document not in review queue")
    for f in item["fields"]:
        if f["key"] in corrections:
            f["value"] = corrections[f["key"]]
            f["confidence"] = 1.0
            f["needsReview"] = False
            f["humanVerified"] = True
    item["status"] = "APPROVED"
    item["reviewer"] = reviewer
    store.review_queue = [d for d in store.review_queue if d["documentId"] != document_id]

    t = Trace("Document Processing Agent", "review-ui", f"human_review({document_id})", item["sessionId"])
    t.tool("apply_review", "doc-processing-mcp",
           {"documentId": document_id, "corrections": corrections, "reviewer": reviewer},
           {"status": "APPROVED"}, ms=30)
    t.done("Human review approved; corrections become training data")
    return item

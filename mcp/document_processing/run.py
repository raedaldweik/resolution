"""Document Processing MCP server — real OCR for SAS RAM.

Backs the "MoCE Document Processing" agent: give it a scanned citizen
document (salary certificate, Emirates ID, IBAN letter …) and it returns the
extracted text with confidence scores, the key fields, and a document-type
classification. The AGENT's LLM does the summarizing — these tools return the
raw, verifiable material it summarizes from.

Engine: tesseract (Arabic + English). Nothing is simulated: the text and the
per-word confidences come straight from the OCR engine.

Tools:
  ocr_document       image (base64 or URL) → full text + confidence
  extract_fields     text → Emirates ID / IBAN / amounts / dates / phones …
  classify_document  text → document type + keyword-match confidence

Environment:
  PORT            listen port (default 8400)
  OCR_LANGUAGES   default tesseract languages (default "ara+eng")
  CUSTOM_FIELDS   optional JSON object of extra fields for extract_fields,
                  name → regex, e.g.
                  {"passportNumber": "\\b[A-Z]\\d{8}\\b",
                   "jobTitle": "as ([A-Za-z ]+) since"}
                  Custom fields are ADDED to the defaults (same name
                  overrides). A regex with a capturing group returns
                  group 1, otherwise the whole match. Unset = defaults only.
"""

import base64
import io
import json
import os
import re
import statistics

import httpx
from fastmcp import FastMCP
from PIL import Image
import pytesseract

mcp = FastMCP("moce-document-processing")

DEFAULT_LANGS = os.getenv("OCR_LANGUAGES", "ara+eng")
MAX_IMAGE_BYTES = 15 * 1024 * 1024


def _load_image(image_base64: str, image_url: str) -> Image.Image:
    if image_base64:
        raw = base64.b64decode(image_base64, validate=False)
    elif image_url:
        resp = httpx.get(image_url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        raw = resp.content
    else:
        raise ValueError("Provide image_base64 or image_url.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Image larger than 15 MB.")
    return Image.open(io.BytesIO(raw)).convert("RGB")


@mcp.tool()
def ocr_document(image_base64: str = "", image_url: str = "",
                 languages: str = "") -> dict:
    """Run OCR on a scanned document image (PNG/JPG/TIFF; base64 string or a
    fetchable URL). Returns the extracted text, the mean word confidence
    (0-100), and any words below 60 confidence — flag those to the user as
    needing human verification rather than guessing. Use languages="ara",
    "eng" or "ara+eng" (default)."""
    img = _load_image(image_base64, image_url)
    langs = languages or DEFAULT_LANGS
    data = pytesseract.image_to_data(img, lang=langs, output_type=pytesseract.Output.DICT)
    words, confs, low_conf = [], [], []
    for txt, conf in zip(data["text"], data["conf"]):
        txt = (txt or "").strip()
        if not txt:
            continue
        c = float(conf)
        if c < 0:  # tesseract marks non-word boxes with -1
            continue
        words.append(txt)
        confs.append(c)
        if c < 60:
            low_conf.append({"word": txt, "confidence": round(c)})
    text = pytesseract.image_to_string(img, lang=langs)
    return {
        "text": text.strip(),
        "languages": langs,
        "wordCount": len(words),
        "meanConfidence": round(statistics.fmean(confs), 1) if confs else 0.0,
        "lowConfidenceWords": low_conf[:40],
        "imageSize": {"width": img.width, "height": img.height},
    }


# Deterministic field patterns for UAE citizen documents. The IBAN pattern
# tolerates the classic OCR confusions (O↔0, I/l↔1) — scanners produce
# "AEO7…" for "AE07…" constantly — and the match is normalized back to digits.
FIELD_PATTERNS = {
    "emiratesId": re.compile(r"\b784[- ]?\d{4}[- ]?\d{7}[- ]?\d\b"),
    "iban": re.compile(r"\bAE[0-9OoIl]{2}(?:[ ]?[0-9OoIl]){19}\b"),
    "amountsAED": re.compile(r"(?:AED|درهم|Dhs?\.?)\s?([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s?(?:AED|درهم)", re.I),
    "dates": re.compile(r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b"),
    "phones": re.compile(r"(?:\+971|00971|0)[ -]?5\d[ -]?\d{3}[ -]?\d{4}\b"),
    "emails": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
}

_IBAN_FIX = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"})


def _load_custom_fields() -> dict:
    """Operator-defined extra fields from the CUSTOM_FIELDS env var (set it on
    the RAM Container MCP Server template). Bad JSON or a bad regex must never
    take the server down — log and fall back to the defaults."""
    raw = os.getenv("CUSTOM_FIELDS", "").strip()
    if not raw:
        return {}
    try:
        spec = json.loads(raw)
        assert isinstance(spec, dict)
    except (json.JSONDecodeError, AssertionError):
        print("[moce-document-processing] CUSTOM_FIELDS ignored — must be a JSON "
              'object of {"fieldName": "regex"}')
        return {}
    out = {}
    for name, pattern in spec.items():
        try:
            out[str(name)] = re.compile(str(pattern), re.IGNORECASE | re.MULTILINE)
        except re.error as e:
            print(f"[moce-document-processing] CUSTOM_FIELDS[{name!r}] skipped — invalid regex: {e}")
    if out:
        print(f"[moce-document-processing] custom extraction fields active: {sorted(out)}")
    return out


CUSTOM_FIELDS = _load_custom_fields()


@mcp.tool()
def extract_fields(text: str) -> dict:
    """Extract the key structured fields from OCR'd document text:
    Emirates ID number, IBAN, AED amounts, dates, UAE phone numbers, emails —
    plus any operator-defined fields configured on this server (the
    customFieldsActive list in the result). Purely pattern-based — every value
    returned exists in the text (IBANs are additionally normalized for common
    OCR digit confusions like O→0)."""
    out = {}
    for field, pattern in {**FIELD_PATTERNS, **CUSTOM_FIELDS}.items():
        if field in CUSTOM_FIELDS:
            values = [(m.group(1) if pattern.groups and m.group(1) is not None else m.group(0))
                      for m in pattern.finditer(text)]
        elif field == "amountsAED":
            values = [m.group(1) or m.group(2) for m in pattern.finditer(text)]
        else:
            values = [m.group(0) for m in pattern.finditer(text)]
        if field == "iban" and field not in CUSTOM_FIELDS:
            values = ["AE" + v[2:].translate(_IBAN_FIX) for v in values]
        seen, unique = set(), []
        for v in values:
            key = re.sub(r"[\s,-]", "", v)
            if key not in seen:
                seen.add(key)
                unique.append(v.strip())
        out[field] = unique
    out["fieldsFound"] = sum(1 for v in out.values() if isinstance(v, list) and v)
    out["customFieldsActive"] = sorted(CUSTOM_FIELDS)
    return out


DOC_TYPES = {
    "salary_certificate": ["salary", "certificate", "employer", "monthly", "employee",
                           "شهادة", "راتب", "الراتب", "جهة العمل"],
    "emirates_id_card": ["emirates id", "identity card", "united arab emirates", "id number",
                         "الهوية", "بطاقة هوية"],
    "iban_letter": ["iban", "bank", "account", "swift", "آيبان", "مصرف", "حساب"],
    "family_book": ["family book", "khulasat", "al-qaid", "خلاصة القيد", "قيد الأسرة"],
    "utility_bill": ["electricity", "water", "dewa", "sewa", "invoice", "فاتورة", "كهرباء", "مياه"],
}


@mcp.tool()
def classify_document(text: str) -> dict:
    """Classify OCR'd text into a document type (salary_certificate,
    emirates_id_card, iban_letter, family_book, utility_bill, or other) by
    bilingual keyword matching. confidence is the share of matched keywords —
    below 0.3, treat the type as uncertain and ask the user."""
    tl = text.lower()
    scores = {}
    for doc_type, keywords in DOC_TYPES.items():
        hits = sum(1 for k in keywords if k in tl)
        scores[doc_type] = round(hits / len(keywords), 2)
    best = max(scores, key=scores.get)
    confidence = scores[best]
    return {
        "docType": best if confidence >= 0.2 else "other",
        "confidence": confidence,
        "scores": scores,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0",
            port=int(os.getenv("PORT", "8400")), path="/mcp")

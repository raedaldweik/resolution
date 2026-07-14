"""Document tools — the same real OCR/extraction logic as the
mcp/document_processing server, callable in-process by the Claude agents."""
from __future__ import annotations

import io
import re
import statistics

import httpx

DEFAULT_LANGS = "ara+eng"

FIELD_PATTERNS = {
    "emiratesId": re.compile(r"\b784[- ]?\d{4}[- ]?\d{7}[- ]?\d\b"),
    "iban": re.compile(r"\bAE[0-9OoIl]{2}(?:[ ]?[0-9OoIl]){19}\b"),
    "amountsAED": re.compile(r"(?:AED|درهم|Dhs?\.?)\s?([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s?(?:AED|درهم)", re.I),
    "dates": re.compile(r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b"),
    "phones": re.compile(r"(?:\+971|00971|0)[ -]?5\d[ -]?\d{3}[ -]?\d{4}\b"),
    "emails": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
}
_IBAN_FIX = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"})

DOC_TYPES = {
    "salary_certificate": ["salary", "certificate", "employer", "monthly", "employee",
                           "شهادة", "راتب", "الراتب", "جهة العمل"],
    "emirates_id_card": ["emirates id", "identity card", "united arab emirates", "id number",
                         "الهوية", "بطاقة هوية"],
    "iban_letter": ["iban", "bank", "account", "swift", "آيبان", "مصرف", "حساب"],
    "family_book": ["family book", "khulasat", "al-qaid", "خلاصة القيد", "قيد الأسرة"],
    "utility_bill": ["electricity", "water", "dewa", "sewa", "invoice", "فاتورة", "كهرباء", "مياه"],
}


def ocr_image(data: bytes, languages: str = "") -> dict:
    import pytesseract
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    langs = languages or DEFAULT_LANGS
    grid = pytesseract.image_to_data(img, lang=langs, output_type=pytesseract.Output.DICT)
    words, confs, low = [], [], []
    for txt, conf in zip(grid["text"], grid["conf"]):
        txt = (txt or "").strip()
        c = float(conf)
        if not txt or c < 0:
            continue
        words.append(txt)
        confs.append(c)
        if c < 60:
            low.append({"word": txt, "confidence": round(c)})
    text = pytesseract.image_to_string(img, lang=langs)
    return {"text": text.strip(), "languages": langs, "wordCount": len(words),
            "meanConfidence": round(statistics.fmean(confs), 1) if confs else 0.0,
            "lowConfidenceWords": low[:40],
            "imageSize": {"width": img.width, "height": img.height}}


def fetch_image(url: str) -> bytes:
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def extract_fields(text: str) -> dict:
    out = {}
    for field, pattern in FIELD_PATTERNS.items():
        if field == "amountsAED":
            values = [m.group(1) or m.group(2) for m in pattern.finditer(text)]
        else:
            values = [m.group(0) for m in pattern.finditer(text)]
        if field == "iban":
            values = ["AE" + v[2:].translate(_IBAN_FIX) for v in values]
        seen, unique = set(), []
        for v in values:
            key = re.sub(r"[\s,-]", "", v)
            if key not in seen:
                seen.add(key)
                unique.append(v.strip())
        out[field] = unique
    out["fieldsFound"] = sum(1 for v in out.values() if isinstance(v, list) and v)
    return out


def classify_document(text: str) -> dict:
    tl = text.lower()
    scores = {t: round(sum(1 for k in kws if k in tl) / len(kws), 2)
              for t, kws in DOC_TYPES.items()}
    best = max(scores, key=scores.get)
    return {"docType": best if scores[best] >= 0.2 else "other",
            "confidence": scores[best], "scores": scores}

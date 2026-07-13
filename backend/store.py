"""In-memory state for the MoCE agent-ecosystem demo.

Everything here is a stand-in for a system of record that the production
build reads through MCP tools:
  citizens/benefits/payments -> ministry registries via DB-Connector MCP / Dynamics 365
  policies                   -> SAS RAM collections (vectorized, with citations)
  rulesets/flows             -> SAS Intelligent Decisioning (published to MAS)
  traces                     -> SAS RAM query telemetry (toolCalls/llmCalls/retrievalCalls)
"""

import itertools
import time
import uuid

_seq = itertools.count(1)


def next_id(prefix: str) -> str:
    return f"{prefix}-{next(_seq):04d}"


def now_ms() -> int:
    return int(time.time() * 1000)


def new_uuid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------
# Seed data
# --------------------------------------------------------------------------

def _seed_citizens():
    return {
        "784-1985-9384756-1": {
            "emiratesId": "784-1985-9384756-1",
            "nameEn": "Fatima Al Mansoori",
            "nameAr": "فاطمة المنصوري",
            "dob": "1985-03-14",
            "nationality": "UAE",
            "emirate": "Sharjah",
            "familySize": 5,
            "employment": {"status": "Employed", "employerEn": "Al Noor Trading LLC",
                           "employerAr": "شركة النور للتجارة ذ.م.م", "monthlyIncomeAED": None,
                           "incomeVerifiedUntil": "2026-03-31"},
            "phone": "+971-50-XXX-4821",
            "benefits": [
                {"benefitId": "BEN-2210", "program": "Inflation Allowance",
                 "programAr": "علاوة غلاء المعيشة",
                 "monthlyAmountAED": 2350, "status": "SUSPENDED",
                 "statusReason": "INCOME_VERIFICATION_EXPIRED",
                 "suspendedSince": "2026-04-01", "enrolledSince": "2024-01-01"},
            ],
            "payments": [
                {"date": "2026-01-25", "amountAED": 2350, "status": "PAID"},
                {"date": "2026-02-25", "amountAED": 2350, "status": "PAID"},
                {"date": "2026-03-25", "amountAED": 2350, "status": "PAID"},
                {"date": "2026-04-25", "amountAED": 0, "status": "SKIPPED"},
                {"date": "2026-05-25", "amountAED": 0, "status": "SKIPPED"},
                {"date": "2026-06-25", "amountAED": 0, "status": "SKIPPED"},
            ],
            "caseHistory": [],
        },
        "784-1990-1122334-2": {
            "emiratesId": "784-1990-1122334-2",
            "nameEn": "Ahmed Al Suwaidi",
            "nameAr": "أحمد السويدي",
            "dob": "1990-08-02",
            "nationality": "UAE",
            "emirate": "Ajman",
            "familySize": 6,
            "employment": {"status": "Employed", "employerEn": "Gulf Logistics FZE",
                           "employerAr": "الخليج للخدمات اللوجستية", "monthlyIncomeAED": 27000,
                           "incomeVerifiedUntil": "2027-01-31"},
            "phone": "+971-55-XXX-7710",
            "benefits": [
                {"benefitId": "BEN-3401", "program": "Inflation Allowance",
                 "programAr": "علاوة غلاء المعيشة",
                 "monthlyAmountAED": 0, "status": "REJECTED",
                 "statusReason": "INCOME_ABOVE_THRESHOLD",
                 "appliedOn": "2026-05-12"},
            ],
            "payments": [],
            "caseHistory": [],
        },
    }


def _seed_policies():
    # Simulates a SAS RAM collection: "MoCE Policy Library" (champion config,
    # PaddleOCR ara+eng, chunked, embedded). Chunks carry citations.
    return [
        {"docId": "POL-2024-017", "title": "Inflation Allowance Programme — Eligibility Criteria",
         "titleAr": "برنامج علاوة غلاء المعيشة — معايير الاستحقاق",
         "article": "Art. 4.2", "page": 12, "lang": "en/ar",
         "text": "The inflation allowance is payable to Emirati heads of household whose "
                 "verified gross monthly income does not exceed the threshold defined in "
                 "Schedule B (AED 25,000 at publication). Income verification must be "
                 "renewed every 12 months; benefits are suspended, not terminated, while "
                 "verification is pending.",
         "textAr": "تُصرف علاوة غلاء المعيشة لأرباب الأسر من مواطني الدولة الذين لا يتجاوز دخلهم الشهري "
                   "الإجمالي الموثق الحد المنصوص عليه في الجدول (ب) (25,000 درهم عند النشر). يجب تجديد "
                   "التحقق من الدخل كل 12 شهراً؛ وتُعلّق المزايا ولا تُلغى أثناء انتظار التحقق."},
        {"docId": "POL-2024-017", "title": "Inflation Allowance Programme — Reinstatement & Back-payment",
         "titleAr": "برنامج علاوة غلاء المعيشة — إعادة الصرف والدفعات بأثر رجعي",
         "article": "Art. 7.1", "page": 23, "lang": "en/ar",
         "text": "Where suspension was caused solely by expired income verification and the "
                 "renewed verification confirms continued eligibility, the allowance shall be "
                 "reinstated and withheld instalments paid retroactively for a period not "
                 "exceeding six months.",
         "textAr": "إذا كان التعليق ناتجاً فقط عن انتهاء صلاحية التحقق من الدخل وأكد التحقق المجدد استمرار "
                   "الاستحقاق، تُعاد العلاوة وتُصرف الأقساط الموقوفة بأثر رجعي لمدة لا تتجاوز ستة أشهر."},
        {"docId": "POL-2024-017", "title": "Inflation Allowance Programme — Application Requirements",
         "titleAr": "برنامج علاوة غلاء المعيشة — متطلبات التقديم",
         "article": "Art. 5.3", "page": 16, "lang": "en/ar",
         "text": "Applications require: (a) valid Emirates ID; (b) a salary certificate issued "
                 "within 90 days for each employed household member; (c) an IBAN letter from a "
                 "UAE bank; and (d) the family book (khulasat al-qaid). Applications are "
                 "submitted through the MoCE portal or service centres; processing takes up to "
                 "10 working days.",
         "textAr": "يتطلب التقديم: (أ) هوية إماراتية سارية؛ (ب) شهادة راتب صادرة خلال 90 يوماً لكل فرد عامل في "
                   "الأسرة؛ (ج) رسالة IBAN من مصرف في الدولة؛ (د) خلاصة القيد. تُقدَّم الطلبات عبر بوابة الوزارة "
                   "أو مراكز الخدمة، وتستغرق المعالجة حتى 10 أيام عمل."},
        {"docId": "POL-2024-017", "title": "Inflation Allowance Programme — Allowance Amounts (Schedule B)",
         "titleAr": "برنامج علاوة غلاء المعيشة — قيمة العلاوة (الجدول ب)",
         "article": "Sch. B", "page": 31, "lang": "en/ar",
         "text": "The base allowance is AED 2,350 per month per eligible household. A dependant "
                 "supplement of AED 350 per month applies for each dependant beyond the fourth, "
                 "capped at AED 3,400 total. Amounts are reviewed annually against the consumer "
                 "price index.",
         "textAr": "قيمة العلاوة الأساسية 2,350 درهماً شهرياً لكل أسرة مستحقة، مع علاوة إعالة قدرها 350 درهماً "
                   "شهرياً عن كل معال بعد الرابع وبحد أقصى 3,400 درهم. وتُراجع المبالغ سنوياً وفق مؤشر أسعار "
                   "المستهلك."},
        {"docId": "POL-2025-003", "title": "Digital Services Charter — Human Review Guarantees",
         "titleAr": "ميثاق الخدمات الرقمية — ضمانات المراجعة البشرية",
         "article": "Art. 2.4", "page": 5, "lang": "en/ar",
         "text": "Automated decisions affecting a benefit amount or entitlement must be "
                 "reviewed and approved by an authorised social worker and social auditor "
                 "before taking financial effect.",
         "textAr": "يجب مراجعة القرارات الآلية التي تؤثر على مبلغ أو استحقاق أي منفعة واعتمادها من قبل "
                   "أخصائي اجتماعي ومدقق اجتماعي مخولين قبل نفاذ أثرها المالي."},
    ]


def _seed_doc_schemas():
    # Simulates the admin-owned Document Type Schema Registry (Agent 1).
    return {
        "salary_certificate": {
            "typeId": "salary_certificate", "nameEn": "Salary Certificate",
            "nameAr": "شهادة راتب", "version": 3,
            "fields": [
                {"key": "employee_name", "labelEn": "Employee name", "labelAr": "اسم الموظف",
                 "required": True, "threshold": 0.85},
                {"key": "employer_name", "labelEn": "Employer", "labelAr": "جهة العمل",
                 "required": True, "threshold": 0.85},
                {"key": "monthly_income", "labelEn": "Gross monthly income (AED)",
                 "labelAr": "الدخل الشهري الإجمالي (درهم)", "required": True, "threshold": 0.90},
                {"key": "issue_date", "labelEn": "Issue date", "labelAr": "تاريخ الإصدار",
                 "required": True, "threshold": 0.85},
                {"key": "stamp", "labelEn": "Official stamp", "labelAr": "الختم الرسمي",
                 "required": True, "threshold": 0.80},
            ],
            "validations": ["issue_date within 90 days", "monthly_income > 0",
                            "employee_name matches applicant (fuzzy ≥ 0.8)"],
        }
    }


def _seed_rulesets():
    # Simulates SAS Intelligent Decisioning content. Version 3 is live.
    rules_v3 = [
        {"ruleId": "INC-001", "name": "Nationality gate",
         "expression": "citizen.nationality == 'UAE'", "action": "continue", "editable": False},
        {"ruleId": "INC-002", "name": "Head of household",
         "expression": "citizen.familySize >= 1", "action": "continue", "editable": False},
        {"ruleId": "INC-004", "name": "Income threshold",
         "expression": "income.monthlyAED <= {threshold}", "action": "continue",
         "editable": True, "params": {"threshold": 25000}},
        {"ruleId": "INC-007", "name": "Verification recency",
         "expression": "income.verifiedWithinMonths <= 12", "action": "continue", "editable": False},
        {"ruleId": "OUT-001", "name": "Outcome mapping",
         "expression": "all gates passed -> ELIGIBLE else INELIGIBLE", "action": "assign_outcome",
         "editable": False},
    ]
    return {
        "ruleSetId": "RS-INFLATION-ELIG",
        "name": "Inflation Allowance — Eligibility Rule Set",
        "flowId": "FLOW-INFL-001",
        "flowName": "Inflation Allowance Eligibility",
        "masModule": "inflation_allowance_eligibility",
        "publishedVersion": 3,
        "draftVersion": None,
        "versions": {
            3: {"version": 3, "publishedAt": "2026-05-02T09:14:00Z", "publishedBy": "s.alketbi@moce.gov.ae",
                "note": "Threshold aligned with Cabinet Resolution 12/2026", "rules": rules_v3},
        },
        "history": [
            {"version": 1, "publishedAt": "2024-01-05T08:00:00Z", "note": "Initial publication"},
            {"version": 2, "publishedAt": "2025-02-11T11:30:00Z", "note": "Added verification recency gate"},
            {"version": 3, "publishedAt": "2026-05-02T09:14:00Z", "note": "Threshold aligned with Cabinet Resolution 12/2026"},
        ],
    }


def _seed_autonomy():
    # Learning-to-Autonomy tracker (Agent 3). Seeded history of AI-vs-human alignment.
    return {
        "phase": "LEARNING",
        "gates": {"supervised": 0.90, "full": 0.95},
        "casesEvaluated": 1240,
        "aligned": 1084,
        "history": [
            {"month": "2026-01", "alignment": 0.79, "cases": 142},
            {"month": "2026-02", "alignment": 0.82, "cases": 176},
            {"month": "2026-03", "alignment": 0.84, "cases": 201},
            {"month": "2026-04", "alignment": 0.86, "cases": 228},
            {"month": "2026-05", "alignment": 0.87, "cases": 243},
            {"month": "2026-06", "alignment": 0.874, "cases": 250},
        ],
    }


def _seed_metrics():
    return {
        "queries30d": 4812,
        "hallucinationBlocks30d": 14,
        "hallucinationRate": 0.0029,
        "avgConfidence": 0.883,
        "confidenceHistogram": [  # bucket lower bound -> count (30d recommendations)
            {"bucket": "0.5–0.6", "count": 38}, {"bucket": "0.6–0.7", "count": 104},
            {"bucket": "0.7–0.8", "count": 356}, {"bucket": "0.8–0.9", "count": 1421},
            {"bucket": "0.9–1.0", "count": 2893},
        ],
        "tokenCostByAgentUSD": {"documents": 41.20, "knowledge": 118.75,
                                "case": 63.40, "resolution": 92.10},
        "containmentRate": 0.81,
        # triage of inbound contacts: most "complaints" are really questions —
        # the agent answers those from the knowledge base without opening a case
        "triage30d": {"queries": 2988, "complaints": 1204, "serviceRequests": 620},
        "queryDeflectionRate": 0.62,
    }


class Store:
    def __init__(self):
        self.reset()

    def reset(self):
        self.citizens = _seed_citizens()
        self.policies = _seed_policies()
        self.doc_schemas = _seed_doc_schemas()
        self.ruleset = _seed_rulesets()
        self.autonomy = _seed_autonomy()
        self.metrics = _seed_metrics()
        self.sessions = {}        # sessionId -> session dict
        self.traces = []          # newest last
        self.review_queue = []    # document review items
        self.cases = []           # case records
        self.escalations = []     # blocked responses / human handoffs
        self.notifications = []   # outbound SMS mock
        self.hallucination_log = []
        self._seed_demo_case_history()

    def _seed_demo_case_history(self):
        self.cases.append({
            "caseId": "CASE-2026-08113", "type": "Benefit Reinstatement Appeal",
            "citizenId": "784-1990-1122334-2", "citizenName": "Ahmed Al Suwaidi",
            "priority": "Medium", "slaHours": 72, "status": "CLOSED",
            "createdAt": "2026-06-20T10:02:00Z",
            "recommendation": {
                "outcome": "REJECT", "confidence": 0.91,
                "rationale": "Verified income AED 27,000 exceeds Schedule B threshold (AED 25,000).",
                "evidence": [{"docId": "POL-2024-017", "article": "Art. 4.2", "page": 12}],
                "risk": "LOW",
                "decisionFlow": {"flow": "Inflation Allowance Eligibility", "version": 3},
            },
            "stages": [
                {"stage": 1, "role": "Social Worker", "actor": "n.alhammadi@moce.gov.ae",
                 "decision": "APPROVE_RECOMMENDATION", "at": "2026-06-21T08:40:00Z"},
                {"stage": 2, "role": "Social Auditor", "actor": "k.almazrouei@moce.gov.ae",
                 "decision": "APPROVE_RECOMMENDATION", "at": "2026-06-21T13:05:00Z"},
            ],
            "timeline": [
                {"at": "2026-06-20T10:02:00Z", "event": "Case created from portal appeal"},
                {"at": "2026-06-20T10:02:41Z", "event": "AI recommendation generated (REJECT, 0.91)"},
                {"at": "2026-06-21T13:05:00Z", "event": "Two-stage approval complete — case closed"},
            ],
            "aiHumanAligned": True,
        })


store = Store()

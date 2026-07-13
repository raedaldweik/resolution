"""Simulated Customer Resolution AI Agent (Agent 4) — the orchestrator.

Production swap: a RAM orchestrator agent whose A2A sub-agents are the
Document Processing and Knowledge & Decision agents, with action MCP tools
allow-listed per authority limits. The conversation engine below is a
deterministic script (ideal for a stage demo); the LLM slot is marked in
every trace so the swap is visible.

Every answer carries {en, ar}; the client renders per language. Quick-reply
suggestions drive the presenter through the golden path.
"""

from store import store, next_id
from engine import knowledge
from engine.tracer import Trace


NEG_WORDS = ("unacceptable", "angry", "ridiculous", "third time", "fed up", "complaint",
             "غاضب", "غير مقبول", "للمرة الثالثة", "سئمت")
HALLUCINATION_TRIGGERS = ("bonus", "eid", "العيد", "مكافأة")
CONFIRM_WORDS = ("yes", "confirm", "proceed", "please do", "go ahead", "نعم", "موافق", "تفضل", "أكمل")
STOP_WORDS_INTENT = ("stop", "didn't receive", "did not receive", "no payment", "missing",
                     "توقف", "لم أستلم", "لم استلم", "انقطع", "اختفت")


def create_session(channel: str, citizen_id: str, lang: str = "en"):
    sid = next_id("SES")
    store.sessions[sid] = {
        "sessionId": sid, "channel": channel, "citizenId": citizen_id, "lang": lang,
        "stage": "start", "messages": [], "events": [], "sentiment": {"score": 0.2, "label": "neutral"},
        "verifiedIncome": None, "caseId": None,
    }
    return store.sessions[sid]


def _suggestions(stage, lang_pair=True):
    s = {
        "start": [
            {"en": "Why did my inflation allowance payment stop?", "ar": "لماذا توقفت علاوة غلاء المعيشة الخاصة بي؟"},
            {"en": "Am I eligible for the inflation allowance?", "ar": "هل أنا مؤهلة لعلاوة غلاء المعيشة؟"},
        ],
        "awaiting_doc": [
            {"en": "📎 Upload salary certificate (scanned copy)", "ar": "📎 رفع شهادة الراتب (نسخة ممسوحة)", "action": "upload:salary_cert_blurry"},
            {"en": "📎 Upload salary certificate (digital PDF)", "ar": "📎 رفع شهادة الراتب (PDF أصلي)", "action": "upload:salary_cert_clean"},
        ],
        "doc_in_review": [
            {"en": "What happens during human review?", "ar": "ماذا يحدث أثناء المراجعة البشرية؟"},
        ],
        "resolution_proposed": [
            {"en": "Yes, please proceed.", "ar": "نعم، تفضلوا بالمتابعة."},
            {"en": "Will I also get the Eid bonus with my back-pay?", "ar": "هل سأحصل أيضاً على مكافأة العيد مع الدفعات المتأخرة؟"},
        ],
        "resolved": [
            {"en": "What is the status of my case?", "ar": "ما حالة معاملتي؟"},
            {"en": "Will I also get the Eid bonus with my back-pay?", "ar": "هل سأحصل أيضاً على مكافأة العيد مع الدفعات المتأخرة؟"},
        ],
    }
    return s.get(stage, s["start"])


def _sentiment(session, text):
    tl = text.lower()
    if any(w in tl for w in NEG_WORDS):
        session["sentiment"] = {"score": 0.82, "label": "frustrated"}
    else:
        # decay toward neutral
        session["sentiment"] = {"score": max(0.1, session["sentiment"]["score"] - 0.1),
                                "label": "neutral"}
    return session["sentiment"]


def handle_message(session_id: str, text: str, lang: str = "en"):
    session = store.sessions[session_id]
    citizen = store.citizens[session["citizenId"]]
    session["lang"] = lang
    sentiment = _sentiment(session, text)
    tl = text.lower()

    if any(w in tl for w in HALLUCINATION_TRIGGERS):
        return _blocked_response(session, citizen, text)

    if session["stage"] == "resolution_proposed" and any(w in tl for w in CONFIRM_WORDS):
        return _execute_resolution(session, citizen, text)

    if any(w in tl for w in STOP_WORDS_INTENT) or session["stage"] == "start" and ("علاوة" in text or "allowance" in tl):
        return _investigate(session, citizen, text)

    if "status" in tl or "حالة" in text:
        return _case_status(session, citizen, text)

    if "review" in tl or "المراجعة" in text:
        return _explain_review(session, citizen, text)

    return _policy_answer(session, citizen, text)


# ---------------------------------------------------------------- investigate

def _investigate(session, citizen, text):
    t = Trace("Customer Resolution Agent", session["channel"], text, session["sessionId"])
    ben = citizen["benefits"][0]
    t.tool("get_citizen_profile", "registry-mcp",
           {"emiratesId": citizen["emiratesId"], "auth": "UAEPass" if session["channel"] == "citizen" else "agent-console"},
           {"name": citizen["nameEn"], "familySize": citizen["familySize"]}, ms=110)
    t.tool("get_benefit_status", "benefits-mcp",
           {"citizenId": citizen["emiratesId"], "program": "Inflation Allowance"},
           {"status": ben["status"], "reason": ben["statusReason"],
            "suspendedSince": ben.get("suspendedSince"), "monthlyAED": ben["monthlyAmountAED"]}, ms=140)
    chunks = knowledge.retrieve("inflation allowance suspension income verification renewal")
    t.retrieval("MoCE Policy Library", "suspension due to expired income verification", chunks, ms=390)
    t.llm("grounded response",
          "Compose reply strictly from tool results + retrieved policy. No unsourced facts.",
          "Suspension cause identified; request renewed salary certificate", 1490, 230, 980)

    answer_en = (f"I checked your record, {citizen['nameEn'].split()[0]}. Your Inflation Allowance "
                 f"(AED {ben['monthlyAmountAED']:,}/month) was **suspended on {ben['suspendedSince']}** because "
                 f"your **income verification expired on {citizen['employment']['incomeVerifiedUntil']}** — not because "
                 f"you became ineligible. Per policy POL-2024-017 Art. 4.2, benefits are suspended (not terminated) "
                 f"while verification is pending, and Art. 7.1 allows **reinstatement with back-payment** once "
                 f"eligibility is re-confirmed.\n\nTo re-verify your income, please upload a recent "
                 f"**salary certificate** (issued within 90 days). I will process it immediately.")
    answer_ar = (f"راجعتُ سجلك يا {citizen['nameAr'].split()[0]}. علاوة غلاء المعيشة "
                 f"({ben['monthlyAmountAED']:,} درهم شهرياً) **عُلّقت بتاريخ {ben['suspendedSince']}** بسبب "
                 f"**انتهاء صلاحية التحقق من الدخل في {citizen['employment']['incomeVerifiedUntil']}** — وليس لعدم "
                 f"الأهلية. وفق السياسة POL-2024-017 المادة 4.2، تُعلّق المزايا ولا تُلغى أثناء انتظار التحقق، "
                 f"وتتيح المادة 7.1 **إعادة الصرف مع الدفعات بأثر رجعي** بعد إعادة تأكيد الاستحقاق.\n\n"
                 f"لإعادة التحقق من دخلك، يرجى رفع **شهادة راتب** حديثة (صادرة خلال 90 يوماً)، وسأعالجها فوراً.")
    t.done("Suspension cause identified; requested renewed salary certificate")
    session["stage"] = "awaiting_doc"
    return _msg(session, answer_en, answer_ar, t.rec["traceId"],
                activity=[
                    {"agent": "resolution", "labelEn": "Verified identity via UAEPass", "labelAr": "التحقق من الهوية عبر الهوية الرقمية"},
                    {"agent": "resolution", "labelEn": "Retrieved benefit record — SUSPENDED (verification expired)", "labelAr": "استرجاع سجل المنفعة — معلّقة (انتهاء التحقق)"},
                    {"agent": "knowledge", "labelEn": "Retrieved policy POL-2024-017 Art. 4.2 & 7.1 (cited)", "labelAr": "استرجاع السياسة POL-2024-017 المادتين 4.2 و7.1"},
                    {"agent": "guard", "labelEn": "verify_claims: 4/4 facts traced to records", "labelAr": "التحقق من الوقائع: 4/4 موثقة"},
                ],
                citations=chunks)


# ------------------------------------------------------------- doc follow-ups

def on_document_processed(session_id: str, doc_result: dict):
    """Called by the upload endpoint after Agent 1 finishes."""
    session = store.sessions[session_id]
    if doc_result["reviewRequired"]:
        session["stage"] = "doc_in_review"
        fields = ", ".join(f["labelEn"] for f in doc_result["fields"] if f["needsReview"])
        en = (f"Thank you — I received **{doc_result['fileName']}** and processed it as a "
              f"**{doc_result['docTypeName']}** (schema v{doc_result['schemaVersion']}, classification 96%). "
              f"Most fields extracted cleanly, but **{fields}** came back below the confidence threshold "
              f"on this scan, so it has been routed to a **human reviewer** as required by our quality "
              f"policy. This usually takes a few minutes — I'll continue automatically once verified.")

        ar = (f"شكراً — استلمتُ **{doc_result['fileName']}** وعالجتُه كـ**شهادة راتب** "
              f"(الإصدار {doc_result['schemaVersion']}، تصنيف 96%). استُخرجت معظم الحقول بنجاح، لكن حقل "
              f"**الدخل الشهري** جاء بثقة أقل من الحد المطلوب في هذه النسخة الممسوحة، لذا حُوّل إلى "
              f"**مراجع بشري** وفق سياسة الجودة لدينا. يستغرق ذلك عادةً دقائق قليلة — وسأتابع تلقائياً فور التحقق.")
    else:
        en, ar = _run_eligibility(session)
    return {"answerEn": en, "answerAr": ar, "suggestions": _suggestions(session["stage"])}


def on_review_completed(session_id: str, doc_item: dict):
    """Called when the human reviewer approves — resumes the golden path."""
    session = store.sessions[session_id]
    en, ar = _run_eligibility(session)
    session["events"].append({"type": "agent_message", "answerEn": en, "answerAr": ar,
                              "meta": {"kind": "eligibility_result"}})


def _run_eligibility(session):
    citizen = store.citizens[session["citizenId"]]
    income = 23500
    session["verifiedIncome"] = income
    rec = knowledge.assess_eligibility(session["sessionId"], citizen, income)
    session["pendingRecommendation"] = rec
    session["stage"] = "resolution_proposed"
    fin = rec["financialImpact"]
    en = (f"✅ Your income verification is complete (human-verified: **AED {income:,}/month**). "
          f"I asked the Knowledge & Decision agent to re-assess your eligibility:\n\n"
          f"**Outcome: ELIGIBLE** (decision flow *{rec['decisionFlow']['flow']}* v{rec['decisionFlow']['version']}, "
          f"confidence {rec['confidence']:.0%})\n"
          f"**Recommendation:** reinstate your allowance at AED {fin['monthlyAED']:,}/month and release "
          f"**AED {fin['backpayAED']:,} back-pay** for the {fin['backpayMonths']} suspended months "
          f"(POL-2024-017 Art. 7.1).\n\nI can reinstate the allowance now within my authority. The back-payment "
          f"requires two-stage human approval (Social Worker + Social Auditor). Shall I proceed?")
    ar = (f"✅ اكتمل التحقق من دخلك (تحقق بشري: **{income:,} درهم شهرياً**). "
          f"طلبتُ من وكيل المعرفة والقرار إعادة تقييم أهليتك:\n\n"
          f"**النتيجة: مؤهلة** (مسار القرار *أهلية علاوة غلاء المعيشة* الإصدار {rec['decisionFlow']['version']}، "
          f"بثقة {rec['confidence']:.0%})\n"
          f"**التوصية:** إعادة صرف العلاوة بواقع {fin['monthlyAED']:,} درهم شهرياً وصرف **{fin['backpayAED']:,} درهم "
          f"بأثر رجعي** عن الأشهر الثلاثة المعلقة (المادة 7.1).\n\nيمكنني إعادة صرف العلاوة الآن ضمن صلاحياتي، أما "
          f"الدفعة بأثر رجعي فتتطلب اعتماداً بشرياً على مرحلتين (أخصائي اجتماعي + مدقق اجتماعي). هل أتابع؟")
    return en, ar


# ---------------------------------------------------------------- execution

def _execute_resolution(session, citizen, text):
    from engine import cases as case_engine
    rec = session["pendingRecommendation"]
    t = Trace("Customer Resolution Agent", session["channel"], text, session["sessionId"])
    t.tool("update_benefit_status", "benefits-mcp",
           {"citizenId": citizen["emiratesId"], "program": "Inflation Allowance",
            "action": "REINSTATE", "authority": "within-limit (status change)"},
           {"status": "ACTIVE", "effective": "immediately"}, ms=180)
    citizen["benefits"][0]["status"] = "ACTIVE"
    citizen["benefits"][0]["statusReason"] = "REINSTATED_AFTER_VERIFICATION"
    t.tool("send_notification", "notify-mcp",
           {"channel": "sms", "to": citizen["phone"], "template": "reinstated", "lang": session["lang"]},
           {"status": "sent"}, ms=70)
    store.notifications.append({
        "at": "now", "to": citizen["nameEn"], "channel": "SMS",
        "textEn": "MoCE: your Inflation Allowance has been reinstated effective immediately.",
        "textAr": "وزارة تمكين المجتمع: تمت إعادة صرف علاوة غلاء المعيشة اعتباراً من الآن.",
    })
    case = case_engine.create_case(session["sessionId"], citizen, rec,
                                   "Benefit Reinstatement — Back-pay Release")
    session["caseId"] = case["caseId"]
    session["stage"] = "resolved"
    t.llm("action confirmation", "Summarize executed actions + case handoff…",
          f"Reinstated; case {case['caseId']} created", 900, 160, 640)
    t.done(f"Reinstated allowance; case {case['caseId']} opened for back-pay approval")

    en = (f"Done ✅ Here is what I executed:\n\n"
          f"1. **Allowance reinstated** — AED {rec['financialImpact']['monthlyAED']:,}/month, effective "
          f"immediately (within my autonomous authority).\n"
          f"2. **SMS confirmation** sent to {citizen['phone']}.\n"
          f"3. **Back-payment of AED {rec['financialImpact']['backpayAED']:,}** requires human approval by "
          f"policy — I opened case **{case['caseId']}** (priority High, SLA 48h). It is now with the "
          f"Social Worker team, then the Social Auditor. I will notify you here and by SMS the moment "
          f"both stages complete.")
    ar = (f"تم ✅ إليك ما نفذته:\n\n"
          f"1. **إعادة صرف العلاوة** — {rec['financialImpact']['monthlyAED']:,} درهم شهرياً اعتباراً من الآن "
          f"(ضمن صلاحياتي المستقلة).\n"
          f"2. **رسالة تأكيد نصية** أُرسلت إلى {citizen['phone']}.\n"
          f"3. **الدفعة بأثر رجعي بمبلغ {rec['financialImpact']['backpayAED']:,} درهم** تتطلب اعتماداً بشرياً وفق "
          f"السياسة — فتحتُ الحالة **{case['caseId']}** (أولوية عالية، اتفاقية مستوى خدمة 48 ساعة). وهي الآن لدى "
          f"فريق الأخصائيين الاجتماعيين ثم المدقق الاجتماعي. سأبلغك هنا وعبر الرسائل النصية فور اكتمال المرحلتين.")
    return _msg(session, en, ar, t.rec["traceId"],
                activity=[
                    {"agent": "resolution", "labelEn": "Executed: reinstate allowance (within authority limit)", "labelAr": "تنفيذ: إعادة صرف العلاوة (ضمن حدود الصلاحية)"},
                    {"agent": "resolution", "labelEn": "SMS notification sent", "labelAr": "إرسال إشعار نصي"},
                    {"agent": "case", "labelEn": f"Case {case['caseId']} created → two-stage approval", "labelAr": f"إنشاء الحالة {case['caseId']} ← اعتماد على مرحلتين"},
                    {"agent": "guard", "labelEn": "verify_claims: amounts traced to decision output", "labelAr": "التحقق: المبالغ موثقة من مخرجات القرار"},
                ])


# ------------------------------------------------------ hallucination blocker

def _blocked_response(session, citizen, text):
    t = Trace("Customer Resolution Agent", session["channel"], text, session["sessionId"])
    t.llm("draft response (pre-guardrail)",
          "User asks about back-pay including Eid bonus…",
          "DRAFT: 'Yes, your back-pay will include the AED 500 Eid bonus…'", 1210, 190, 870)
    claims = [
        {"claim": "Back-pay amount AED 7,050", "verified": True, "source": "decision flow output"},
        {"claim": "Eid bonus of AED 500", "verified": False, "source": None},
        {"claim": "Bonus is added to back-payments", "verified": False, "source": None},
    ]
    t.tool("verify_claims", "guardrail-mcp",
           {"draftClaims": [c["claim"] for c in claims]},
           {"verified": 1, "unverified": 2, "verdict": "BLOCK"}, ms=160)
    t.guardrail("verify_claims", claims, "BLOCKED")
    t.done("Response BLOCKED — 2 unverifiable claims; escalated to human", status="blocked")

    esc = {
        "escalationId": next_id("ESC"), "sessionId": session["sessionId"],
        "citizen": citizen["nameEn"], "channel": session["channel"],
        "reason": "verify_claims blocked draft: unverifiable 'Eid bonus' amount",
        "question": text, "traceId": t.rec["traceId"], "status": "OPEN",
        "sentiment": session["sentiment"]["label"],
    }
    store.escalations.append(esc)
    store.hallucination_log.append({"traceId": t.rec["traceId"], "claims": claims})
    store.metrics["hallucinationBlocks30d"] += 1

    en = ("I can confirm the amounts that exist in your records: your back-pay of **AED 7,050** "
          "(3 × AED 2,350) is documented in your case. However, I **cannot verify any information about an "
          "Eid bonus** in your benefit records or in current policy — so rather than guess, I've referred "
          "this question to a specialist at our contact centre who will confirm the correct answer. "
          "You'll be contacted shortly. Is there anything else I can verify for you?")
    ar = ("أستطيع تأكيد المبالغ الموثقة في سجلاتك: الدفعة بأثر رجعي **7,050 درهم** (3 × 2,350 درهم) مثبتة في "
          "حالتك. لكن **لا يمكنني التحقق من أي معلومات حول مكافأة العيد** في سجلات المزايا أو في السياسات "
          "الحالية — لذا بدلاً من التخمين، أحلتُ سؤالك إلى مختص في مركز الاتصال لتأكيد الإجابة الصحيحة، "
          "وسيتم التواصل معك قريباً. هل هناك ما يمكنني التحقق منه أيضاً؟")
    return _msg(session, en, ar, t.rec["traceId"], blocked=True, escalation_id=esc["escalationId"],
                activity=[
                    {"agent": "resolution", "labelEn": "Drafted response", "labelAr": "صياغة الرد"},
                    {"agent": "guard", "labelEn": "verify_claims: 'Eid bonus AED 500' NOT traceable → BLOCKED", "labelAr": "التحقق: «مكافأة العيد 500 درهم» غير موثقة ← حظر الرد"},
                    {"agent": "resolution", "labelEn": "Escalated to contact-centre specialist", "labelAr": "تصعيد إلى مختص مركز الاتصال"},
                ])


# ------------------------------------------------------------------- misc

def _case_status(session, citizen, text):
    t = Trace("Customer Resolution Agent", session["channel"], text, session["sessionId"])
    case = next((c for c in store.cases if c["caseId"] == session.get("caseId")), None)
    if case:
        t.tool("get_case", "dynamics365-mcp", {"caseId": case["caseId"]},
               {"status": case["status"], "stage1": case["stages"][0]["decision"],
                "stage2": case["stages"][1]["decision"]}, ms=120)
        stage_map = {"PENDING_STAGE_1": ("awaiting Social Worker review (stage 1 of 2)", "بانتظار مراجعة الأخصائي الاجتماعي (المرحلة 1 من 2)"),
                     "PENDING_STAGE_2": ("approved by the Social Worker — awaiting Social Auditor (stage 2 of 2)", "اعتمدها الأخصائي الاجتماعي — بانتظار المدقق الاجتماعي (المرحلة 2 من 2)"),
                     "CLOSED": ("completed — both stages approved", "مكتملة — تم الاعتماد في المرحلتين")}
        s_en, s_ar = stage_map.get(case["status"], (case["status"], case["status"]))
        en = f"Case **{case['caseId']}** is currently **{s_en}**. SLA: 48h from creation."
        ar = f"الحالة **{case['caseId']}** حالياً **{s_ar}**. اتفاقية مستوى الخدمة: 48 ساعة من الإنشاء."
    else:
        en, ar = "You have no open cases at the moment.", "لا توجد لديك حالات مفتوحة حالياً."
    t.done("Case status reported")
    return _msg(session, en, ar, t.rec["traceId"])


def _explain_review(session, citizen, text):
    t = Trace("Customer Resolution Agent", session["channel"], text, session["sessionId"])
    chunks = knowledge.retrieve("human review automated decisions charter")
    t.retrieval("MoCE Policy Library", "human review guarantees", chunks, ms=310)
    t.done("Explained HITL policy")
    en = ("When any extracted value falls below our confidence threshold, a trained MoCE reviewer sees the "
          "original document side-by-side with the extracted data, corrects it if needed, and approves it. "
          "Under the Digital Services Charter Art. 2.4, no automated decision affecting your benefits takes "
          "financial effect without human approval.")
    ar = ("عندما تقل ثقة أي قيمة مستخرجة عن الحد المطلوب، يطّلع مراجع مدرب في الوزارة على المستند الأصلي "
          "جنباً إلى جنب مع البيانات المستخرجة، ويصححها عند الحاجة ثم يعتمدها. وبموجب المادة 2.4 من ميثاق "
          "الخدمات الرقمية، لا يسري أي قرار آلي يمس مزاياك مالياً دون اعتماد بشري.")
    return _msg(session, en, ar, t.rec["traceId"], citations=chunks)


def _policy_answer(session, citizen, text):
    t = Trace("Customer Resolution Agent", session["channel"], text, session["sessionId"])
    chunks = knowledge.retrieve(text)
    t.retrieval("MoCE Policy Library", text, chunks, ms=350)
    t.llm("grounded response", "Answer strictly from retrieved policy with citations…",
          "Eligibility summary with citations", 1100, 190, 760)
    t.done("Policy answer with citations")
    en = ("Based on the Inflation Allowance Programme policy (POL-2024-017 Art. 4.2): the allowance is "
          "payable to Emirati heads of household whose verified gross monthly income does not exceed "
          "AED 25,000, with income re-verification every 12 months. If you'd like, I can check your "
          "specific record — just ask about your payments or eligibility.")
    ar = ("استناداً إلى سياسة برنامج علاوة غلاء المعيشة (POL-2024-017 المادة 4.2): تُصرف العلاوة لأرباب الأسر "
          "من مواطني الدولة الذين لا يتجاوز دخلهم الشهري الإجمالي الموثق 25,000 درهم، مع إعادة التحقق من الدخل "
          "كل 12 شهراً. إن أحببت، يمكنني فحص سجلك مباشرة — فقط اسألني عن دفعاتك أو أهليتك.")
    return _msg(session, en, ar, t.rec["traceId"], citations=chunks)


def _msg(session, en, ar, trace_id, activity=None, citations=None, blocked=False, escalation_id=None):
    msg = {
        "messageId": next_id("MSG"), "answerEn": en, "answerAr": ar,
        "traceId": trace_id, "blocked": blocked, "escalationId": escalation_id,
        "activity": activity or [], "citations": citations or [],
        "sentiment": session["sentiment"], "stage": session["stage"],
        "suggestions": _suggestions(session["stage"]),
        "caseId": session.get("caseId"),
    }
    session["messages"].append(msg)
    return msg

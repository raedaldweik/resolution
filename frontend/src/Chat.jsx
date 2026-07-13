import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { AGENTS, AgentChip, Badge, Conf, Markdownish } from './ui'

const T = {
  en: {
    placeholder: 'Type your message…',
    send: 'Send',
    thinking: 'Agent working…',
    citations: 'Sources',
    blocked: 'Response verified & partially withheld — escalated to a human specialist',
    doc: 'Document processed',
    reviewWait: 'Waiting for human review — approve it in the Documents view',
    you: 'You',
  },
  ar: {
    placeholder: 'اكتب رسالتك…',
    send: 'إرسال',
    thinking: 'الوكيل يعمل…',
    citations: 'المصادر',
    blocked: 'تم التحقق من الرد وحُجب جزئياً — صُعّد إلى مختص بشري',
    doc: 'تمت معالجة المستند',
    reviewWait: 'بانتظار المراجعة البشرية — اعتمدها من شاشة المستندات',
    you: 'أنت',
  },
}

function ActivityFeed({ items, shown, lang }) {
  return (
    <div className="mt-2 space-y-1.5">
      {items.slice(0, shown).map((a, i) => {
        const ag = AGENTS[a.agent] || AGENTS.resolution
        return (
          <div key={i} className="fade-up flex items-start gap-2 text-[12px] text-muted">
            <span className="mt-1 w-1.5 h-1.5 rounded-full shrink-0" style={{ background: ag.color }} />
            <span><span className="font-semibold" style={{ color: ag.color }}>{ag.short}</span>{' · '}
              {lang === 'ar' ? a.labelAr || a.labelEn : a.labelEn}</span>
          </div>
        )
      })}
    </div>
  )
}

function DocCard({ doc, lang }) {
  return (
    <div className="border border-line rounded-xl bg-panel p-3.5 my-1">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="font-semibold text-[13px]">📄 {doc.fileName}</div>
        <div className="flex gap-1.5">
          <Badge tone="doc">{doc.docTypeName} · {Math.round(doc.classificationConfidence * 100)}%</Badge>
          <Badge tone={doc.reviewRequired ? 'warn' : 'ok'}>{doc.reviewRequired ? 'HITL review' : 'Auto-approved'}</Badge>
        </div>
      </div>
      <div className="mt-2.5 grid grid-cols-1 gap-1.5">
        {doc.fields.map((f) => (
          <div key={f.key} className="flex items-center justify-between gap-3 text-[12.5px]">
            <span className="text-muted">{lang === 'ar' ? f.labelAr : f.labelEn}</span>
            <span className="flex items-center gap-2.5">
              <span className={`font-semibold tabnums ${f.needsReview ? 'text-warn' : ''}`}>{f.value}</span>
              <Conf value={f.confidence} threshold={f.threshold} />
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Chat({ channel = 'citizen', citizenId = '784-1985-9384756-1', lang = 'en', onSentiment }) {
  const t = T[lang]
  const [session, setSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [suggestions, setSuggestions] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [staging, setStaging] = useState(null) // {msg, shown}
  const bottomRef = useRef(null)
  const sessionRef = useRef(null)

  useEffect(() => {
    api.createSession(channel, citizenId).then((s) => {
      setSession(s)
      sessionRef.current = s.sessionId
      setSuggestions(s.suggestions || [])
    })
  }, [channel, citizenId])

  // poll for agent-initiated events (post-review, case closure)
  useEffect(() => {
    const iv = setInterval(async () => {
      if (!sessionRef.current) return
      try {
        const r = await api.events(sessionRef.current)
        if (r.events.length) {
          setMessages((m) => [
            ...m,
            ...r.events.map((e) => ({ role: 'agent', text: lang === 'ar' ? e.answerAr : e.answerEn, meta: e.meta })),
          ])
          setSuggestions(r.suggestions || [])
        }
      } catch { /* backend restarting */ }
    }, 2000)
    return () => clearInterval(iv)
  }, [lang])

  // staged reveal of the activity feed, then the answer
  useEffect(() => {
    if (!staging) return
    const total = staging.msg.activity.length
    if (staging.shown < total) {
      const to = setTimeout(() => setStaging((s) => s && { ...s, shown: s.shown + 1 }), 520)
      return () => clearTimeout(to)
    }
    const to = setTimeout(() => {
      const m = staging.msg
      setMessages((prev) => [...prev, {
        role: 'agent', text: lang === 'ar' ? m.answerAr : m.answerEn,
        citations: m.citations, blocked: m.blocked, traceId: m.traceId, activity: m.activity,
      }])
      setSuggestions(m.suggestions || [])
      if (onSentiment) onSentiment(m.sentiment)
      setStaging(null)
      setBusy(false)
    }, 420)
    return () => clearTimeout(to)
  }, [staging, lang, onSentiment])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, staging, busy])

  const send = async (text) => {
    if (!text.trim() || busy || !session) return
    setMessages((m) => [...m, { role: 'user', text }])
    setInput('')
    setBusy(true)
    try {
      const r = await api.chat(session.sessionId, text, lang)
      setStaging({ msg: r, shown: 0 })
    } catch { setBusy(false) }
  }

  const uploadDoc = async (docKey, label) => {
    if (busy || !session) return
    setMessages((m) => [...m, { role: 'user', text: label }])
    setBusy(true)
    try {
      const r = await api.upload(session.sessionId, docKey)
      setMessages((m) => [...m, { role: 'doc', document: r.document }])
      setStaging({
        msg: {
          answerEn: r.chat.answerEn, answerAr: r.chat.answerAr,
          activity: [
            { agent: 'documents', labelEn: 'OCR (PaddleOCR ar+en) — 18 text blocks, 1 table', labelAr: 'التعرف الضوئي — 18 كتلة نصية وجدول واحد' },
            { agent: 'documents', labelEn: `Classified: Salary Certificate (96%) · schema v${r.document.schemaVersion}`, labelAr: 'التصنيف: شهادة راتب (96%)' },
            { agent: 'documents', labelEn: r.document.reviewRequired ? 'Field below threshold → routed to human review' : 'All fields above threshold', labelAr: r.document.reviewRequired ? 'حقل دون حد الثقة ← تحويل للمراجعة البشرية' : 'جميع الحقول فوق حد الثقة' },
          ],
          citations: [], suggestions: r.chat.suggestions, sentiment: { label: 'neutral' },
        },
        shown: 0,
      })
    } catch { setBusy(false) }
  }

  const onSuggestion = (s) => {
    if (s.action?.startsWith('upload:')) uploadDoc(s.action.split(':')[1], lang === 'ar' ? s.ar : s.en)
    else send(lang === 'ar' ? s.ar : s.en)
  }

  return (
    <div className="flex flex-col h-full" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      <div className="flex-1 overflow-y-auto px-1 space-y-3 pb-3">
        {messages.map((m, i) => {
          if (m.role === 'doc') return <DocCard key={i} doc={m.document} lang={lang} />
          const user = m.role === 'user'
          return (
            <div key={i} className={`fade-up flex ${user ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-[13.5px] ${user
                ? 'bg-brand text-white rounded-br-md'
                : m.blocked ? 'bg-[#fdf6f5] border border-[#eeD5d2] rounded-bl-md' : 'bg-panel border border-line rounded-bl-md'}`}>
                {!user && (
                  <div className="flex items-center justify-between gap-3 mb-1.5">
                    <AgentChip agent="resolution" />
                    {m.blocked && <Badge tone="crit">⛔ {lang === 'ar' ? 'رد محجوب جزئياً' : 'guardrail'}</Badge>}
                  </div>
                )}
                <Markdownish text={m.text} className={user ? '' : 'text-ink'} />
                {m.blocked && (
                  <div className="mt-2 text-[11.5px] font-semibold text-crit">{t.blocked}</div>
                )}
                {!user && m.citations?.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {m.citations.map((c, j) => (
                      <span key={j} title={lang === 'ar' ? c.textPreviewAr : c.textPreview}
                        className="text-[11px] font-semibold bg-brand-soft text-brand rounded-full px-2 py-0.5 cursor-help">
                        📎 {c.docId} · {c.article} · p.{c.page}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {(busy || staging) && (
          <div className="fade-up bg-panel border border-line rounded-2xl rounded-bl-md px-4 py-3 max-w-[85%]">
            <div className="flex items-center gap-2 text-[12.5px] text-muted">
              <span className="flex gap-1">
                <span className="typing-dot w-1.5 h-1.5 rounded-full bg-agres inline-block" />
                <span className="typing-dot w-1.5 h-1.5 rounded-full bg-agres inline-block" />
                <span className="typing-dot w-1.5 h-1.5 rounded-full bg-agres inline-block" />
              </span>
              {t.thinking}
            </div>
            {staging && <ActivityFeed items={staging.msg.activity} shown={staging.shown} lang={lang} />}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {suggestions.length > 0 && !busy && (
        <div className="flex flex-wrap gap-2 py-2">
          {suggestions.map((s, i) => (
            <button key={i} onClick={() => onSuggestion(s)}
              className="text-[12.5px] font-semibold border border-brand/30 text-brand bg-brand-soft/50 hover:bg-brand-soft rounded-full px-3 py-1.5 transition">
              {lang === 'ar' ? s.ar : s.en}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={(e) => { e.preventDefault(); send(input) }} className="flex gap-2 pt-2 border-t border-line">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={t.placeholder}
          className="flex-1 bg-panel border border-line rounded-xl px-3.5 py-2.5 text-[13.5px] outline-none focus:border-brand" />
        <button type="submit" disabled={busy || !input.trim()}
          className="bg-brand text-white rounded-xl px-4 font-semibold text-[13px] disabled:opacity-40">{t.send}</button>
      </form>
    </div>
  )
}

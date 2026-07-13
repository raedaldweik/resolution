import { useState } from 'react'
import Chat from '../Chat'
import { Badge, Card, GovLockup, SectionTitle } from '../ui'

const FATIMA = '784-1985-9384756-1'

const AGENT_ROWS = [
  { color: '#6d4b9e', en: ['Customer Resolution', 'resolves complaints & inquiries end-to-end'], ar: ['حل شكاوى المتعاملين', 'يحل الشكاوى والاستفسارات من البداية للنهاية'] },
  { color: '#3a63a8', en: ['Document Processing', 'reads your documents — Arabic & English'], ar: ['معالجة المستندات', 'يقرأ مستنداتك بالعربية والإنجليزية'] },
  { color: '#0b8a6d', en: ['Knowledge & Decision', 'every answer cited to official policy'], ar: ['المعرفة والقرار', 'كل إجابة موثقة من السياسات الرسمية'] },
  { color: '#b91c2c', en: ['Guardrails', 'unverified facts are never sent to you'], ar: ['الحوكمة', 'لا تصلك أي معلومات غير موثقة'] },
]

function Landing({ ar, onSignIn }) {
  return (
    <div className="h-full flex items-center justify-center" dir={ar ? 'rtl' : 'ltr'}>
      <div className="glass-card w-[920px] max-w-[94vw] overflow-hidden">
        <div className="grid md:grid-cols-[1.15fr_1fr]">
          {/* left — welcome + sign in */}
          <div className="p-9 flex flex-col justify-center">
            <GovLockup large />
            <h1 className="mt-7 text-[27px] leading-snug font-extrabold text-ink" style={{ textWrap: 'balance' }}>
              {ar ? 'مرحباً بكم في الخدمات الذكية لوزارة تمكين المجتمع' : 'Welcome to MoCE Intelligent Services'}
            </h1>
            <p className="mt-2.5 text-[13.5px] text-muted leading-relaxed max-w-[46ch]">
              {ar
                ? 'مساعد ذكي يحل شكاواكم واستفساراتكم فوراً — بإجابات موثقة من السياسات الرسمية وبإشراف بشري كامل.'
                : 'An intelligent assistant that resolves your complaints and inquiries on the spot — with answers cited to official policy and full human oversight.'}
            </p>
            <button onClick={onSignIn}
              className="mt-6 w-full md:w-[340px] rounded-xl py-3.5 font-bold text-[14.5px] text-white transition hover:opacity-95 hover:-translate-y-px"
              style={{ background: 'linear-gradient(135deg, #1b2430, #101820 65%)', boxShadow: '0 4px 14px rgba(16,24,32,0.35), inset 0 1px 0 rgba(202,161,75,0.45)' }}>
              🔐 {ar ? 'تسجيل الدخول عبر الهوية الرقمية UAEPass' : 'Sign in with UAEPass'}
            </button>
            <div className="mt-2.5 text-[11px] text-faint">
              {ar ? '(محاكاة — تسجيل دخول كـ فاطمة المنصوري)' : '(Simulated — signs in as Fatima Al Mansoori)'}
            </div>
            <div className="mt-6 flex flex-wrap gap-2">
              {(ar ? ['متاح ٢٤/٧', 'العربية والإنجليزية', 'إجابات موثقة بالمصادر'] : ['Available 24/7', 'العربية & English', 'Every answer cited']).map((x) => (
                <span key={x} className="suggestion-chip !cursor-default">{x}</span>
              ))}
            </div>
          </div>

          {/* right — the agent team */}
          <div className="p-9 border-t md:border-t-0 border-ink/10"
            style={ar ? { borderRight: '1px solid rgba(15,23,42,0.08)', background: 'linear-gradient(160deg, rgba(182,138,53,0.07), rgba(182,138,53,0.02))' }
                      : { borderLeft: '1px solid rgba(15,23,42,0.08)', background: 'linear-gradient(160deg, rgba(182,138,53,0.07), rgba(182,138,53,0.02))' }}>
            <div className="panel-title mb-4">{ar ? 'فريق من الوكلاء المتخصصين في خدمتكم' : 'A team of specialist AI agents at your service'}</div>
            <div className="space-y-3">
              {AGENT_ROWS.map((a) => (
                <div key={a.color} className="glass-strong-card p-3 flex items-start gap-3">
                  <span className="mt-1 w-2.5 h-2.5 rounded-full shrink-0" style={{ background: a.color }} />
                  <div>
                    <div className="text-[13px] font-extrabold text-ink">{ar ? a.ar[0] : a.en[0]}</div>
                    <div className="text-[11.5px] text-muted mt-0.5">{ar ? a.ar[1] : a.en[1]}</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-5 pt-4 border-t border-ink/10 text-[11px] text-muted leading-relaxed">
              {ar
                ? 'القرارات المؤثرة على مزاياكم تخضع دائماً لاعتماد بشري على مرحلتين وفق ميثاق الخدمات الرقمية.'
                : 'Decisions affecting your benefits always require two-stage human approval under the Digital Services Charter.'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Portal({ lang }) {
  const [signedIn, setSignedIn] = useState(false)
  const ar = lang === 'ar'

  if (!signedIn) return <Landing ar={ar} onSignIn={() => setSignedIn(true)} />

  return (
    <div className="h-full grid grid-cols-[1fr_300px] gap-4" dir={ar ? 'rtl' : 'ltr'}>
      <Card className="flex flex-col min-h-0 h-full">
        <div className="flex items-center justify-between pb-3 border-b border-ink/10 mb-3">
          <div>
            <div className="font-extrabold text-[15px] text-ink">
              {ar ? 'مساعد الحلول — وكيل ذكي' : 'Resolution Assistant'}
            </div>
            <div className="text-[11.5px] text-muted">
              {ar ? 'موثّق عبر الهوية الرقمية · فاطمة المنصوري' : 'Authenticated via UAEPass · Fatima Al Mansoori'}
            </div>
          </div>
          <Badge tone="res">{ar ? 'وكيل حل شكاوى المتعاملين' : 'Customer Resolution Agent'}</Badge>
        </div>
        <div className="flex-1 min-h-0">
          <Chat channel="citizen" citizenId={FATIMA} lang={lang} />
        </div>
      </Card>

      <div className="space-y-4 overflow-y-auto">
        <Card>
          <SectionTitle>{ar ? 'ملف المستفيدة' : 'Beneficiary profile'}</SectionTitle>
          <div className="text-[13px] space-y-1.5">
            <div className="font-bold text-[14px] text-ink">{ar ? 'فاطمة المنصوري' : 'Fatima Al Mansoori'}</div>
            <div className="text-muted tabnums">784-1985-9384756-1</div>
            <div className="text-muted">{ar ? 'الشارقة · أسرة من 5 أفراد' : 'Sharjah · family of 5'}</div>
          </div>
        </Card>
        <Card>
          <SectionTitle>{ar ? 'المزايا' : 'Benefits'}</SectionTitle>
          <div className="text-[13px]">
            <div className="flex items-center justify-between">
              <span className="font-semibold">{ar ? 'علاوة غلاء المعيشة' : 'Inflation Allowance'}</span>
              <span className="tabnums font-bold text-ink">AED 2,350</span>
            </div>
            <div className="text-[11.5px] text-muted mt-1">
              {ar ? 'الحالة تُحدّث مباشرة أثناء المحادثة' : 'Status updates live during the conversation'}
            </div>
          </div>
        </Card>
        <Card>
          <SectionTitle>{ar ? 'كيف يعمل' : 'Behind the scenes'}</SectionTitle>
          <ul className="text-[12px] text-muted space-y-2 leading-relaxed list-none">
            <li><span className="font-bold text-agres">● {ar ? 'وكيل الحلول' : 'Resolution agent'}</span> — {ar ? 'يفرز: استفسار أم شكوى، ثم ينسّق بقية الوكلاء' : 'triages query vs complaint, then orchestrates the other agents (A2A)'}</li>
            <li><span className="font-bold text-agdoc">● {ar ? 'معالجة المستندات' : 'Document agent'}</span> — {ar ? 'OCR واستخراج بثقة لكل حقل' : 'OCR + per-field confidence extraction'}</li>
            <li><span className="font-bold text-agknow">● {ar ? 'المعرفة والقرار' : 'Knowledge agent'}</span> — {ar ? 'سياسات موثقة + مسارات قرار' : 'cited policy + decision flows'}</li>
            <li><span className="font-bold text-crit">● {ar ? 'الحوكمة' : 'Guardrails'}</span> — {ar ? 'كل واقعة تُتحقق قبل الإرسال' : 'every fact verified before sending'}</li>
          </ul>
        </Card>
      </div>
    </div>
  )
}

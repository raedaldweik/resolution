import { useState } from 'react'
import Chat from '../Chat'
import { Badge, Card, SectionTitle } from '../ui'

const FATIMA = '784-1985-9384756-1'

export default function Portal({ lang }) {
  const [signedIn, setSignedIn] = useState(false)
  const ar = lang === 'ar'

  if (!signedIn) {
    return (
      <div className="h-full flex items-center justify-center" dir={ar ? 'rtl' : 'ltr'}>
        <Card className="w-[420px] text-center p-8">
          <div className="text-4xl mb-3">🇦🇪</div>
          <h2 className="text-xl font-extrabold">{ar ? 'بوابة خدمات وزارة تمكين المجتمع' : 'MoCE Citizen Services Portal'}</h2>
          <p className="text-muted text-[13px] mt-2 leading-relaxed">
            {ar ? 'سجّلي الدخول بالهوية الرقمية للوصول إلى مساعد الحلول الذكي.'
              : 'Sign in with UAEPass to access the intelligent resolution assistant.'}
          </p>
          <button onClick={() => setSignedIn(true)}
            className="mt-5 w-full bg-[#101820] text-white rounded-xl py-3 font-bold text-[14px] hover:opacity-90 transition">
            🔐 {ar ? 'تسجيل الدخول عبر UAEPass' : 'Sign in with UAEPass'}
          </button>
          <div className="mt-3 text-[11px] text-muted">
            {ar ? '(محاكاة — تسجيل دخول كـ فاطمة المنصوري)' : '(Simulated — signs in as Fatima Al Mansoori)'}
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="h-full grid grid-cols-[1fr_300px] gap-4" dir={ar ? 'rtl' : 'ltr'}>
      <Card className="flex flex-col min-h-0 h-full">
        <div className="flex items-center justify-between pb-3 border-b border-line mb-3">
          <div>
            <div className="font-extrabold text-[15px]">
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
            <div className="font-bold text-[14px]">{ar ? 'فاطمة المنصوري' : 'Fatima Al Mansoori'}</div>
            <div className="text-muted tabnums">784-1985-9384756-1</div>
            <div className="text-muted">{ar ? 'الشارقة · أسرة من 5 أفراد' : 'Sharjah · family of 5'}</div>
          </div>
        </Card>
        <Card>
          <SectionTitle>{ar ? 'المزايا' : 'Benefits'}</SectionTitle>
          <div className="text-[13px]">
            <div className="flex items-center justify-between">
              <span className="font-semibold">{ar ? 'علاوة غلاء المعيشة' : 'Inflation Allowance'}</span>
              <span className="tabnums font-bold">AED 2,350</span>
            </div>
            <div className="text-[11.5px] text-muted mt-1">
              {ar ? 'الحالة تُحدّث مباشرة أثناء المحادثة' : 'Status updates live during the conversation'}
            </div>
          </div>
        </Card>
        <Card>
          <SectionTitle>{ar ? 'كيف يعمل' : 'Behind the scenes'}</SectionTitle>
          <ul className="text-[12px] text-muted space-y-2 leading-relaxed">
            <li><span className="font-semibold text-agres">● {ar ? 'وكيل الحلول' : 'Resolution agent'}</span> — {ar ? 'ينسّق ويستدعي بقية الوكلاء' : 'orchestrates & calls other agents (A2A)'}</li>
            <li><span className="font-semibold text-agdoc">● {ar ? 'معالجة المستندات' : 'Document agent'}</span> — {ar ? 'OCR واستخراج بثقة لكل حقل' : 'OCR + per-field confidence extraction'}</li>
            <li><span className="font-semibold text-agknow">● {ar ? 'المعرفة والقرار' : 'Knowledge agent'}</span> — {ar ? 'سياسات موثقة + مسارات قرار' : 'cited policy + decision flows'}</li>
            <li><span className="font-semibold text-crit">● {ar ? 'الحوكمة' : 'Guardrails'}</span> — {ar ? 'كل واقعة تُتحقق قبل الإرسال' : 'every fact verified before sending'}</li>
          </ul>
        </Card>
      </div>
    </div>
  )
}

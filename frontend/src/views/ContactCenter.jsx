import { useEffect, useState } from 'react'
import { api } from '../api'
import Chat from '../Chat'
import { Badge, Btn, Card, SectionTitle } from '../ui'

export default function ContactCenter() {
  const [eid, setEid] = useState('784-1985-9384756-1')
  const [citizen, setCitizen] = useState(null)
  const [escalations, setEscalations] = useState([])
  const [sentiment, setSentiment] = useState({ score: 0.2, label: 'neutral' })

  const lookup = async () => {
    try { setCitizen(await api.citizen(eid.trim())) } catch { setCitizen(null) }
  }
  useEffect(() => {
    const iv = setInterval(() => api.escalations().then((r) => setEscalations(r.escalations)).catch(() => {}), 2500)
    api.escalations().then((r) => setEscalations(r.escalations)).catch(() => {})
    return () => clearInterval(iv)
  }, [])

  const frustrated = sentiment.label === 'frustrated'

  return (
    <div className="h-full grid grid-cols-[300px_1fr_300px] gap-4">
      {/* citizen 360 */}
      <div className="space-y-4 overflow-y-auto">
        <Card>
          <SectionTitle>Citizen lookup</SectionTitle>
          <div className="flex gap-2">
            <input value={eid} onChange={(e) => setEid(e.target.value)} placeholder="Emirates ID"
              className="glass-input flex-1 px-2.5 py-1.5 text-[12.5px] tabnums" />
            <Btn small onClick={lookup}>Find</Btn>
          </div>
          {citizen && (
            <div className="mt-3 text-[13px] space-y-1">
              <div className="font-bold">{citizen.nameEn} <span className="text-muted font-normal">· {citizen.nameAr}</span></div>
              <div className="text-muted">{citizen.emirate} · family of {citizen.familySize}</div>
              <div className="text-muted">{citizen.employment.employerEn}</div>
            </div>
          )}
        </Card>
        {citizen && (
          <>
            <Card>
              <SectionTitle>Benefits</SectionTitle>
              {citizen.benefits.map((b) => (
                <div key={b.benefitId} className="text-[12.5px] flex items-center justify-between gap-2">
                  <span>{b.program}</span>
                  <Badge tone={b.status === 'ACTIVE' ? 'ok' : b.status === 'SUSPENDED' ? 'warn' : 'crit'}>{b.status}</Badge>
                </div>
              ))}
            </Card>
            <Card>
              <SectionTitle>Payment history</SectionTitle>
              <div className="space-y-1">
                {citizen.payments.map((p, i) => (
                  <div key={i} className="flex justify-between text-[12px] tabnums">
                    <span className="text-muted">{p.date}</span>
                    <span className={p.status === 'PAID' ? '' : 'text-warn font-semibold'}>
                      {p.status === 'PAID' ? `AED ${p.amountAED.toLocaleString()}` : 'skipped'}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
            {citizen.notifications?.length > 0 && (
              <Card>
                <SectionTitle>Sent notifications</SectionTitle>
                {citizen.notifications.map((n, i) => (
                  <div key={i} className="text-[11.5px] text-muted border-b border-line last:border-0 py-1.5">📱 {n.textEn}</div>
                ))}
              </Card>
            )}
          </>
        )}
      </div>

      {/* supervised chat */}
      <Card className="flex flex-col min-h-0 h-full">
        <div className="flex items-center justify-between pb-3 border-b border-line mb-3">
          <div>
            <div className="font-extrabold text-[15px]">Supervised AI investigation</div>
            <div className="text-[11.5px] text-muted">Contact-centre channel · human stays in control</div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Citizen sentiment</span>
            <Badge tone={frustrated ? 'crit' : 'ok'}>{frustrated ? '😤 frustrated — offer handoff' : '🙂 neutral'}</Badge>
          </div>
        </div>
        <div className="flex-1 min-h-0">
          <Chat channel="contact_center" citizenId={citizen?.emiratesId || '784-1985-9384756-1'} onSentiment={setSentiment} />
        </div>
      </Card>

      {/* escalations */}
      <div className="space-y-4 overflow-y-auto">
        <Card>
          <SectionTitle right={<Badge tone={escalations.length ? 'crit' : 'neutral'}>{escalations.length}</Badge>}>
            Escalation inbox
          </SectionTitle>
          {escalations.length === 0 && <div className="text-[12px] text-muted">No open escalations.</div>}
          <div className="space-y-2.5">
            {escalations.map((e) => (
              <div key={e.escalationId} className="border border-[#eed5d2] bg-[#fdf6f5] rounded-lg p-2.5 text-[12px]">
                <div className="flex items-center justify-between">
                  <span className="font-bold">{e.escalationId}</span>
                  <Badge tone="crit">guardrail block</Badge>
                </div>
                <div className="mt-1 text-muted">{e.citizen} · {e.channel}</div>
                <div className="mt-1">“{e.question}”</div>
                <div className="mt-1.5 text-crit font-semibold">{e.reason}</div>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <SectionTitle>Why responses get blocked</SectionTitle>
          <p className="text-[12px] text-muted leading-relaxed">
            Every name, date, and amount in a draft reply is checked by <span className="font-semibold text-ink">verify_claims</span> against
            system records. Unverifiable facts block the response and open an escalation — target hallucination rate ≤ 0.5%.
          </p>
        </Card>
      </div>
    </div>
  )
}

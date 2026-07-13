import { useEffect, useState } from 'react'
import { api } from '../api'
import { Badge, Btn, Card, Drawer, SectionTitle, Stat } from '../ui'

function AlignmentChart({ history, gates }) {
  // single-series line + two gate reference lines; y domain 0.7–1.0
  const W = 560, H = 150, PAD = { l: 40, r: 12, t: 12, b: 22 }
  const xs = (i) => PAD.l + (i / (history.length - 1)) * (W - PAD.l - PAD.r)
  const ys = (v) => PAD.t + (1 - (v - 0.7) / 0.3) * (H - PAD.t - PAD.b)
  const path = history.map((h, i) => `${i ? 'L' : 'M'}${xs(i)},${ys(h.alignment)}`).join(' ')
  const last = history[history.length - 1]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
      aria-label={`AI–human alignment trend, latest ${(last.alignment * 100).toFixed(1)}%`}>
      {[0.7, 0.8, 0.9, 1.0].map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={ys(v)} y2={ys(v)} stroke="#e4e7e3" strokeWidth="1" />
          <text x={PAD.l - 6} y={ys(v) + 3.5} textAnchor="end" fontSize="9.5" fill="#62726c" className="tabnums">{Math.round(v * 100)}%</text>
        </g>
      ))}
      {/* gates */}
      <line x1={PAD.l} x2={W - PAD.r} y1={ys(gates.supervised)} y2={ys(gates.supervised)} stroke="#a4660b" strokeWidth="1.5" strokeDasharray="5 4" />
      <text x={W - PAD.r} y={ys(gates.supervised) - 4} textAnchor="end" fontSize="9.5" fill="#a4660b" fontWeight="700">Supervised autonomy ≥ 90%</text>
      <line x1={PAD.l} x2={W - PAD.r} y1={ys(gates.full)} y2={ys(gates.full)} stroke="#1a7f37" strokeWidth="1.5" strokeDasharray="5 4" />
      <text x={W - PAD.r} y={ys(gates.full) - 4} textAnchor="end" fontSize="9.5" fill="#1a7f37" fontWeight="700">Full autonomy ≥ 95%</text>
      <path d={path} fill="none" stroke="#0b6a4f" strokeWidth="2" strokeLinecap="round" />
      {history.map((h, i) => (
        <circle key={i} cx={xs(i)} cy={ys(h.alignment)} r={i === history.length - 1 ? 4.5 : 3}
          fill={i === history.length - 1 ? '#0b6a4f' : '#fff'} stroke="#0b6a4f" strokeWidth="1.6">
          <title>{h.month}: {(h.alignment * 100).toFixed(1)}% over {h.cases} cases</title>
        </circle>
      ))}
      <text x={xs(history.length - 1)} y={ys(last.alignment) - 9} textAnchor="middle" fontSize="10.5" fontWeight="800" fill="#0b6a4f" className="tabnums">
        {(last.alignment * 100).toFixed(1)}%
      </text>
      {history.map((h, i) => (
        <text key={i} x={xs(i)} y={H - 6} textAnchor="middle" fontSize="9" fill="#62726c">{h.month.slice(5)}</text>
      ))}
    </svg>
  )
}

const STATUS_TONE = { PENDING_STAGE_1: 'warn', PENDING_STAGE_2: 'case', CLOSED: 'ok', RETURNED: 'crit' }

export default function Cases() {
  const [cases, setCases] = useState([])
  const [auto, setAuto] = useState(null)
  const [open, setOpen] = useState(null)

  const load = () => {
    api.cases().then((r) => setCases(r.cases)).catch(() => {})
    api.autonomy().then(setAuto).catch(() => {})
  }
  useEffect(() => { load(); const iv = setInterval(load, 2500); return () => clearInterval(iv) }, [])

  const approve = async (stage) => {
    const actor = stage === 1 ? 'n.alhammadi@moce.gov.ae (Social Worker)' : 'k.almazrouei@moce.gov.ae (Social Auditor)'
    const r = await api.approve(open.caseId, stage, actor)
    setOpen(r.case)
    load()
  }

  return (
    <div className="h-full overflow-y-auto space-y-4">
      {auto && (
        <div className="grid grid-cols-[1fr_340px] gap-4">
          <Card>
            <SectionTitle right={<Badge tone="case">Learning-to-Autonomy framework</Badge>}>
              AI ↔ human decision alignment — road to autonomy
            </SectionTitle>
            <AlignmentChart history={auto.history} gates={auto.gates} />
          </Card>
          <div className="flex flex-col gap-4">
            <Stat label="Current phase" value={auto.phase === 'LEARNING' ? 'Learning' : auto.phase.replaceAll('_', ' ').toLowerCase()}
              sub="Human decides · AI recommendation tracked" tone="text-agcase" />
            <Stat label="Alignment" value={`${(auto.currentAlignment * 100).toFixed(1)}%`}
              sub={`${auto.aligned.toLocaleString()} of ${auto.casesEvaluated.toLocaleString()} cases · gate: 90%`} />
          </div>
        </div>
      )}

      <Card>
        <SectionTitle>Case queue — two-stage approval (Social Worker → Social Auditor)</SectionTitle>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-left text-muted">
                <th className="py-1.5 pr-3 font-semibold">Case</th>
                <th className="py-1.5 pr-3 font-semibold">Type</th>
                <th className="py-1.5 pr-3 font-semibold">Citizen</th>
                <th className="py-1.5 pr-3 font-semibold">AI recommendation</th>
                <th className="py-1.5 pr-3 font-semibold">Priority / SLA</th>
                <th className="py-1.5 pr-3 font-semibold">Status</th>
                <th className="py-1.5 font-semibold"></th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.caseId} className="border-t border-line">
                  <td className="py-2.5 pr-3 font-bold tabnums">{c.caseId}</td>
                  <td className="py-2.5 pr-3">{c.type}</td>
                  <td className="py-2.5 pr-3">{c.citizenName}</td>
                  <td className="py-2.5 pr-3">
                    <Badge tone="know">{c.recommendation.recommendation || c.recommendation.outcome} · {Math.round(c.recommendation.confidence * 100)}%</Badge>
                  </td>
                  <td className="py-2.5 pr-3 text-muted">{c.priority} · {c.slaHours}h</td>
                  <td className="py-2.5 pr-3"><Badge tone={STATUS_TONE[c.status] || 'neutral'}>{c.status.replaceAll('_', ' ')}</Badge></td>
                  <td className="py-2.5 text-right"><Btn small tone="ghost" onClick={() => setOpen(c)}>Open</Btn></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Drawer open={!!open} onClose={() => setOpen(null)} title={open ? `${open.caseId} — ${open.type}` : ''} wide>
        {open && (
          <div className="space-y-5">
            <div className="flex gap-2 flex-wrap">
              <Badge tone={STATUS_TONE[open.status] || 'neutral'}>{open.status.replaceAll('_', ' ')}</Badge>
              <Badge tone="neutral">{open.citizenName}</Badge>
              <Badge tone="neutral">{open.priority} · SLA {open.slaHours}h</Badge>
              {open.aiHumanAligned != null && (
                <Badge tone={open.aiHumanAligned ? 'ok' : 'crit'}>{open.aiHumanAligned ? 'AI–human aligned' : 'human override'}</Badge>
              )}
            </div>

            <Card>
              <SectionTitle>AI recommendation — Knowledge & Decision agent</SectionTitle>
              <div className="flex items-center gap-2 flex-wrap mb-2">
                <Badge tone="know">{open.recommendation.recommendation || open.recommendation.outcome}</Badge>
                <Badge tone="neutral">confidence {Math.round(open.recommendation.confidence * 100)}%</Badge>
                <Badge tone={open.recommendation.risk === 'LOW' ? 'ok' : 'warn'}>risk {open.recommendation.risk}</Badge>
                {open.recommendation.decisionFlow && (
                  <Badge tone="gold">{open.recommendation.decisionFlow.flow} v{open.recommendation.decisionFlow.version}</Badge>
                )}
              </div>
              <p className="text-[13px] leading-relaxed">{open.recommendation.rationale}</p>
              {open.recommendation.evidence?.length > 0 && (
                <div className="mt-2 flex gap-1.5 flex-wrap">
                  {open.recommendation.evidence.map((e, i) => (
                    <span key={i} className="text-[11px] font-semibold bg-brand-soft text-brand rounded-full px-2 py-0.5">
                      📎 {e.docId} · {e.article} · p.{e.page}
                    </span>
                  ))}
                </div>
              )}
              {open.recommendation.financialImpact && (
                <div className="mt-2.5 text-[12.5px] text-muted tabnums">
                  Financial impact: AED {open.recommendation.financialImpact.backpayAED.toLocaleString()} back-pay
                  ({open.recommendation.financialImpact.backpayMonths} months × AED {open.recommendation.financialImpact.monthlyAED.toLocaleString()})
                </div>
              )}
            </Card>

            <Card>
              <SectionTitle>Two-stage approval</SectionTitle>
              <div className="space-y-3">
                {open.stages.map((s) => (
                  <div key={s.stage} className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="text-[13px]">
                      <span className="font-bold">Stage {s.stage} — {s.role}</span>
                      {s.decision
                        ? <span className="text-muted"> · {s.decision.replaceAll('_', ' ').toLowerCase()} by {s.actor}</span>
                        : <span className="text-muted"> · pending</span>}
                    </div>
                    {!s.decision && ((s.stage === 1 && open.status === 'PENDING_STAGE_1') || (s.stage === 2 && open.status === 'PENDING_STAGE_2')) && (
                      <div className="flex gap-2">
                        <Btn small onClick={() => approve(s.stage)}>✓ Approve recommendation</Btn>
                      </div>
                    )}
                    {s.decision && <Badge tone="ok">✓ {new Date(s.at).toLocaleString()}</Badge>}
                  </div>
                ))}
              </div>
              <div className="mt-3 text-[11.5px] text-muted">
                Case cannot close until both stages complete (SAS Workflow Manager BPMN in production).
                Stage-2 approval releases the back-payment and notifies the citizen automatically.
              </div>
            </Card>

            <Card>
              <SectionTitle>Timeline</SectionTitle>
              <div className="space-y-1.5">
                {open.timeline.map((t, i) => (
                  <div key={i} className="flex gap-2.5 text-[12px]">
                    <span className="text-muted tabnums whitespace-nowrap">{String(t.at).slice(0, 16).replace('T', ' ')}</span>
                    <span>{t.event}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}
      </Drawer>
    </div>
  )
}

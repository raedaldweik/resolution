import { useEffect, useState } from 'react'
import { api } from '../api'
import { AGENTS, AgentChip, Badge, Card, Drawer, SectionTitle, Stat } from '../ui'

function ConfidenceHistogram({ data }) {
  // sequential single hue (brand ramp), light→dark with magnitude
  const W = 480, H = 150, PAD = { l: 8, r: 8, t: 18, b: 20 }
  const max = Math.max(...data.map((d) => d.count))
  const bw = (W - PAD.l - PAD.r) / data.length
  const ramp = ['#cfe5db', '#a5cfbe', '#77b59e', '#3f9377', '#0b6a4f']
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Recommendation confidence distribution, 30 days">
      {data.map((d, i) => {
        const h = Math.max(3, (d.count / max) * (H - PAD.t - PAD.b))
        const x = PAD.l + i * bw + 3
        const y = H - PAD.b - h
        const isMax = d.count === max
        return (
          <g key={d.bucket}>
            <rect x={x} y={y} width={bw - 6} height={h} rx="4" fill={ramp[i]}>
              <title>{d.bucket}: {d.count.toLocaleString()} recommendations</title>
            </rect>
            {isMax && (
              <text x={x + (bw - 6) / 2} y={y - 5} textAnchor="middle" fontSize="10.5" fontWeight="800" fill="#0b6a4f" className="tabnums">
                {d.count.toLocaleString()}
              </text>
            )}
            <text x={x + (bw - 6) / 2} y={H - 6} textAnchor="middle" fontSize="9" fill="#62726c" className="tabnums">{d.bucket}</text>
          </g>
        )
      })}
    </svg>
  )
}

function CostByAgent({ costs }) {
  // categorical — color follows the agent identity used across the whole app
  const entries = [
    ['documents', costs.documents], ['knowledge', costs.knowledge],
    ['case', costs.case], ['resolution', costs.resolution],
  ]
  const max = Math.max(...entries.map(([, v]) => v))
  return (
    <div className="space-y-2">
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-center gap-2.5 text-[12px]">
          <span className="w-24 shrink-0 font-semibold" style={{ color: AGENTS[k].color }}>{AGENTS[k].short}</span>
          <span className="flex-1 h-2.5 rounded-full bg-line/60 overflow-hidden">
            <span className="block h-full rounded-full" style={{ width: `${(v / max) * 100}%`, background: AGENTS[k].color }} />
          </span>
          <span className="tabnums text-muted w-16 text-right">${v.toFixed(2)}</span>
        </div>
      ))}
    </div>
  )
}

const STATUS_TONE = { completed: 'ok', blocked: 'crit', review: 'warn', running: 'neutral' }

export default function Governance() {
  const [metrics, setMetrics] = useState(null)
  const [traces, setTraces] = useState([])
  const [detail, setDetail] = useState(null)

  const load = () => {
    api.metrics().then(setMetrics).catch(() => {})
    api.traces().then((r) => setTraces(r.traces)).catch(() => {})
  }
  useEffect(() => { load(); const iv = setInterval(load, 3000); return () => clearInterval(iv) }, [])
  if (!metrics) return null

  const openTrace = async (id) => setDetail(await api.trace(id))

  return (
    <div className="h-full overflow-y-auto space-y-4">
      <div className="flex gap-4 flex-wrap">
        <Stat label="Queries (30d)" value={metrics.queries30d.toLocaleString()} sub={`${metrics.liveTraces} live this session`} />
        <Stat label="Hallucination rate" value={`${(metrics.hallucinationRate * 100).toFixed(2)}%`}
          sub={`${metrics.hallucinationBlocks30d} blocked · target ≤ 0.5%`} tone="text-ok" />
        <Stat label="Avg. recommendation confidence" value={`${Math.round(metrics.avgConfidence * 100)}%`} sub="all agents, 30 days" />
        <Stat label="Containment" value={`${Math.round(metrics.containmentRate * 100)}%`} sub="resolved without human handoff" />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <SectionTitle>Recommendation confidence distribution (30d)</SectionTitle>
          <ConfidenceHistogram data={metrics.confidenceHistogram} />
        </Card>
        <Card>
          <SectionTitle>LLM token cost by agent (30d)</SectionTitle>
          <CostByAgent costs={metrics.tokenCostByAgentUSD} />
          <div className="mt-3 text-[11.5px] text-muted">
            In production these figures come from SAS RAM's per-query telemetry (llmCalls include token counts and cost).
          </div>
        </Card>
      </div>

      <Card>
        <SectionTitle right={<Badge tone="brand">every answer fully traceable</Badge>}>
          Reasoning traces — live session
        </SectionTitle>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-muted">
                <th className="py-1.5 pr-3 font-semibold">Trace</th>
                <th className="py-1.5 pr-3 font-semibold">Agent</th>
                <th className="py-1.5 pr-3 font-semibold">Prompt / task</th>
                <th className="py-1.5 pr-3 font-semibold">Calls</th>
                <th className="py-1.5 pr-3 font-semibold">Status</th>
                <th className="py-1.5 pr-3 font-semibold">Cost</th>
                <th className="py-1.5 font-semibold"></th>
              </tr>
            </thead>
            <tbody>
              {traces.map((t) => (
                <tr key={t.traceId} className="border-t border-line">
                  <td className="py-2 pr-3 tabnums font-semibold">{t.traceId}</td>
                  <td className="py-2 pr-3 whitespace-nowrap"><AgentChip agent={
                    t.agent.includes('Document') ? 'documents' : t.agent.includes('Knowledge') ? 'knowledge'
                      : t.agent.includes('Case') ? 'case' : 'resolution'} /></td>
                  <td className="py-2 pr-3 max-w-[320px] truncate" title={t.prompt}>{t.prompt}</td>
                  <td className="py-2 pr-3 text-muted tabnums whitespace-nowrap">
                    🔧{t.toolCalls} · 🧠{t.llmCalls} · 📚{t.retrievalCalls}{t.guardrails > 0 && <span className="text-crit"> · 🛡{t.guardrails}</span>}
                  </td>
                  <td className="py-2 pr-3"><Badge tone={STATUS_TONE[t.status] || 'neutral'}>{t.status}</Badge></td>
                  <td className="py-2 pr-3 tabnums text-muted">${t.costUSD.toFixed(4)}</td>
                  <td className="py-2 text-right">
                    <button onClick={() => openTrace(t.traceId)} className="text-brand font-semibold text-[12px] hover:underline">Inspect</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Drawer open={!!detail} onClose={() => setDetail(null)} title={detail ? `${detail.traceId} — full reasoning trace` : ''} wide>
        {detail && (
          <div className="space-y-4">
            <div className="flex gap-2 flex-wrap">
              <Badge tone="res">{detail.agent}</Badge>
              <Badge tone={STATUS_TONE[detail.status] || 'neutral'}>{detail.status}</Badge>
              <Badge tone="neutral">{detail.ms} ms</Badge>
              <Badge tone="neutral">${detail.costUSD.toFixed(4)}</Badge>
            </div>
            <Card>
              <SectionTitle>Prompt → answer</SectionTitle>
              <div className="text-[12.5px]"><span className="text-muted">Prompt:</span> {detail.prompt}</div>
              <div className="text-[12.5px] mt-1.5"><span className="text-muted">Answer:</span> {detail.answerPreview}…</div>
            </Card>

            {detail.retrievalCalls.length > 0 && (
              <Card>
                <SectionTitle>📚 Retrieval calls (RAG)</SectionTitle>
                {detail.retrievalCalls.map((r) => (
                  <div key={r.id} className="text-[12px] mb-2.5">
                    <div className="text-muted">{r.collection} · “{r.query}” · {r.ms} ms</div>
                    <div className="mt-1.5 space-y-1.5">
                      {r.chunks.map((c, i) => (
                        <div key={i} className="border border-line rounded-lg p-2">
                          <div className="font-semibold text-[11.5px]">{c.docId} · {c.article} · p.{c.page} <span className="text-muted font-normal">score {c.score}</span></div>
                          <div className="text-muted mt-0.5">{c.textPreview}…</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </Card>
            )}

            {detail.toolCalls.length > 0 && (
              <Card>
                <SectionTitle>🔧 Tool calls (MCP)</SectionTitle>
                <div className="space-y-2">
                  {detail.toolCalls.map((c) => (
                    <div key={c.id} className="border border-line rounded-lg p-2.5 text-[11.5px]">
                      <div className="flex items-center justify-between">
                        <span className="font-bold">{c.tool}<span className="text-muted font-normal"> @ {c.server}</span></span>
                        <span className="text-muted tabnums">{c.ms} ms</span>
                      </div>
                      <div className="mt-1 text-muted">in: <code className="text-[10.5px]">{JSON.stringify(c.args)}</code></div>
                      <div className="mt-0.5 text-muted">out: <code className="text-[10.5px]">{JSON.stringify(c.result)}</code></div>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {detail.llmCalls.length > 0 && (
              <Card>
                <SectionTitle>🧠 LLM calls</SectionTitle>
                <div className="space-y-2">
                  {detail.llmCalls.map((c) => (
                    <div key={c.id} className="border border-line rounded-lg p-2.5 text-[11.5px]">
                      <div className="flex items-center justify-between">
                        <span className="font-bold">{c.purpose}</span>
                        <span className="text-muted tabnums">{c.promptTokens}+{c.completionTokens} tok · ${c.costUSD.toFixed(5)} · {c.ms} ms</span>
                      </div>
                      <div className="mt-1 text-muted">model: {c.model}</div>
                      <div className="mt-0.5 text-muted">prompt: {c.promptPreview}</div>
                      <div className="mt-0.5 text-muted">completion: {c.completionPreview}</div>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {detail.guardrails.length > 0 && (
              <Card>
                <SectionTitle>🛡 Guardrails — verify_claims</SectionTitle>
                {detail.guardrails.map((g, i) => (
                  <div key={i}>
                    <Badge tone="crit">{g.verdict}</Badge>
                    <div className="mt-2 space-y-1">
                      {g.claims.map((c, j) => (
                        <div key={j} className="flex items-center gap-2 text-[12px]">
                          <span className={c.verified ? 'text-ok' : 'text-crit'}>{c.verified ? '✓' : '✗'}</span>
                          <span>{c.claim}</span>
                          <span className="text-muted text-[11px]">{c.verified ? `(${c.source})` : '(no source — blocked)'}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </Card>
            )}
          </div>
        )}
      </Drawer>
    </div>
  )
}

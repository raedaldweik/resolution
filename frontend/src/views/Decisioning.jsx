import { useEffect, useState } from 'react'
import { api } from '../api'
import { Badge, Btn, Card, SectionTitle } from '../ui'

const AHMED = '784-1990-1122334-2'

export default function Decisioning() {
  const [st, setSt] = useState(null)
  const [threshold, setThreshold] = useState(null)
  const [test, setTest] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = () => api.decisioning().then((s) => {
    setSt(s)
    const inc = (s.draftRules || s.rules).find((r) => r.ruleId === 'INC-004')
    setThreshold(inc?.params?.threshold)
  })
  useEffect(() => { load() }, [])

  if (!st) return null
  const rules = st.draftRules || st.rules
  const hasDraft = !!st.draftVersion

  const saveDraft = async () => {
    setBusy(true)
    await api.updateRule('INC-004', { threshold: Number(threshold) })
    await load(); setBusy(false)
  }
  const publish = async () => {
    setBusy(true)
    await api.publish(`Income threshold set to AED ${Number(threshold).toLocaleString()}`)
    await load(); setTest(null); setBusy(false)
  }
  const runTest = async () => {
    setBusy(true)
    setTest(await api.testFlow(AHMED))
    setBusy(false)
  }

  return (
    <div className="h-full overflow-y-auto grid grid-cols-[1fr_380px] gap-4">
      <div className="space-y-4">
        <Card>
          <SectionTitle right={
            <div className="flex gap-1.5">
              <Badge tone="gold">published v{st.publishedVersion}</Badge>
              {hasDraft && <Badge tone="warn">draft v{st.draftVersion} — unpublished</Badge>}
            </div>
          }>
            {st.name}
          </SectionTitle>
          <div className="text-[12px] text-muted mb-3">
            Decision flow <span className="font-semibold text-ink">{st.flowName}</span> · MAS module{' '}
            <code className="bg-ink/5 px-1.5 py-0.5 rounded text-[11px]">{st.masModule}</code> — in production this
            screen <em>is</em> SAS Intelligent Decisioning; MoCE analysts author and publish without any vendor.
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="text-left text-muted">
                  <th className="py-1.5 pr-3 font-semibold">Rule</th>
                  <th className="py-1.5 pr-3 font-semibold">Name</th>
                  <th className="py-1.5 pr-3 font-semibold">Expression</th>
                  <th className="py-1.5 font-semibold">Parameters</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.ruleId} className="border-t border-line align-middle">
                    <td className="py-2 pr-3 font-bold tabnums">{r.ruleId}</td>
                    <td className="py-2 pr-3">{r.name}</td>
                    <td className="py-2 pr-3"><code className="text-[11px] bg-ink/5 rounded px-1.5 py-0.5">{r.expression}</code></td>
                    <td className="py-2">
                      {r.ruleId === 'INC-004' ? (
                        <span className="flex items-center gap-2">
                          <span className="text-[11.5px] text-muted">threshold AED</span>
                          <input type="number" step="1000" value={threshold ?? ''}
                            onChange={(e) => setThreshold(e.target.value)}
                            className="w-24 border-2 border-gold/50 rounded-lg px-2 py-1 tabnums text-[12.5px] outline-none focus:border-brand" />
                          <Btn small tone="ghost" disabled={busy} onClick={saveDraft}>Save draft</Btn>
                        </span>
                      ) : r.editable === false ? (
                        <span className="text-[11px] text-muted">🔒 locked</span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {hasDraft && (
            <div className="mt-3 flex items-center gap-3 bg-gold-soft border border-gold/30 rounded-xl px-3.5 py-2.5">
              <span className="text-[12.5px]">Draft v{st.draftVersion} ready — publishing makes it live for <b>every agent instantly</b>, no retraining.</span>
              <Btn disabled={busy} onClick={publish}>🚀 Publish v{st.draftVersion}</Btn>
            </div>
          )}
        </Card>

        <Card>
          <SectionTitle>Test runner — execute the flow before/after publishing</SectionTitle>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="text-[13px]">Test citizen: <b>Ahmed Al Suwaidi</b> <span className="text-muted tabnums">(verified income AED 27,000)</span></div>
            <Btn small disabled={busy} onClick={runTest}>▶ Run decision flow (published v{st.publishedVersion})</Btn>
          </div>
          {test && (
            <div className="mt-3 fade-up">
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <Badge tone={test.outcome === 'ELIGIBLE' ? 'ok' : 'crit'}>{test.outcome}</Badge>
                <Badge tone="neutral">v{test.version}</Badge>
                <Badge tone="neutral">confidence {Math.round(test.confidence * 100)}%</Badge>
                {test.executedOn && (
                  <Badge tone={test.live ? 'gold' : 'neutral'}>
                    {test.live ? '⚡ ' : ''}{test.executedOn}
                  </Badge>
                )}
              </div>
              <div className="space-y-1">
                {test.ruleFires.map((f) => (
                  <div key={f.ruleId} className="flex items-center gap-2 text-[12.5px]">
                    <span className={f.passed ? 'text-ok' : 'text-crit'}>{f.passed ? '✓' : '✗'}</span>
                    <span className="font-semibold tabnums w-16">{f.ruleId}</span>
                    <span className="text-muted">{f.detail}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      <div className="space-y-4">
        <Card>
          <SectionTitle>Version history</SectionTitle>
          <div className="space-y-2">
            {[...st.history].reverse().map((h) => (
              <div key={h.version} className="text-[12.5px] border-b border-line last:border-0 pb-2">
                <div className="flex items-center gap-2">
                  <Badge tone={h.version === st.publishedVersion ? 'gold' : 'neutral'}>v{h.version}</Badge>
                  <span className="text-muted tabnums text-[11.5px]">{String(h.publishedAt).slice(0, 16).replace('T', ' ')}</span>
                </div>
                <div className="mt-1">{h.note}</div>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <SectionTitle>Generated score code (DS2)</SectionTitle>
          <pre className="text-[10.5px] leading-relaxed bg-[#1c2430] text-[#e8d9b0] rounded-xl p-3.5 overflow-x-auto">{st.ds2Preview}</pre>
          <div className="mt-2 text-[11.5px] text-muted">
            Published to SAS Micro Analytic Service — millisecond scoring, callable by every agent through MCP.
          </div>
        </Card>
      </div>
    </div>
  )
}

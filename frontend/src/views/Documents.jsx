import { useEffect, useState } from 'react'
import { api } from '../api'
import { Badge, Btn, Card, Conf, Drawer, SectionTitle } from '../ui'

/* A faux scanned salary certificate with annotation boxes — stands in for the
   annotated-document view a production review UI renders over the real file. */
function CertPreview({ doc, highlightKey }) {
  const f = Object.fromEntries(doc.fields.map((x) => [x.key, x]))
  const Row = ({ k, labelEn, ar }) => (
    <div className={`flex justify-between items-baseline px-3 py-1.5 rounded ${highlightKey === k ? 'bg-[#fdf3e2] outline outline-2 outline-warn' : ''}`}>
      <span className="text-[10.5px] text-[#777]">{labelEn} · <span dir="rtl">{ar}</span></span>
      <span className="text-[12px] font-semibold tabnums text-[#222]">{f[k]?.value}</span>
    </div>
  )
  return (
    <div className={`bg-[#fbfaf7] border border-[#d8d4c8] rounded-lg p-4 shadow-inner ${doc.quality !== 'clean' ? 'blur-[0.4px] contrast-[0.92]' : ''}`}
      style={{ fontFamily: 'Georgia, serif' }}>
      <div className="text-center border-b border-[#d8d4c8] pb-2 mb-2">
        <div className="text-[13px] font-bold text-[#333]">AL NOOR TRADING L.L.C · شركة النور للتجارة ذ.م.م</div>
        <div className="text-[10px] text-[#888] tracking-[0.2em] uppercase mt-0.5">Salary Certificate · شهادة راتب</div>
      </div>
      <div className="space-y-0.5">
        <Row k="employee_name" labelEn="Employee" ar="اسم الموظف" />
        <Row k="employer_name" labelEn="Employer" ar="جهة العمل" />
        <Row k="monthly_income" labelEn="Gross monthly income (AED)" ar="الدخل الشهري" />
        <Row k="issue_date" labelEn="Issue date" ar="تاريخ الإصدار" />
      </div>
      <div className="flex justify-end mt-3">
        <div className={`w-16 h-16 rounded-full border-2 border-[#a33] text-[#a33] text-[7px] flex items-center justify-center text-center rotate-[-12deg] opacity-70 ${highlightKey === 'stamp' ? 'outline outline-2 outline-warn' : ''}`}>
          CHAMBER OF<br />COMMERCE<br />★ SHJ ★
        </div>
      </div>
    </div>
  )
}

export default function Documents() {
  const [queue, setQueue] = useState([])
  const [schemas, setSchemas] = useState([])
  const [open, setOpen] = useState(null) // doc under review
  const [corrections, setCorrections] = useState({})
  const [done, setDone] = useState(null)

  const load = () => {
    api.reviewQueue().then((r) => setQueue(r.queue)).catch(() => {})
    api.schemas().then((r) => setSchemas(r.schemas)).catch(() => {})
  }
  useEffect(() => { load(); const iv = setInterval(load, 2500); return () => clearInterval(iv) }, [])

  const approve = async () => {
    await api.review(open.documentId, corrections)
    setDone(open.documentId)
    setOpen(null)
    setCorrections({})
    load()
  }

  return (
    <div className="h-full grid grid-cols-[1fr_330px] gap-4 overflow-y-auto">
      <div className="space-y-4">
        <Card>
          <SectionTitle right={<Badge tone={queue.length ? 'warn' : 'ok'}>{queue.length} pending</Badge>}>
            Human review queue — fields below confidence threshold
          </SectionTitle>
          {queue.length === 0 && (
            <div className="text-[13px] text-muted py-6 text-center">
              {done ? '✅ Review complete — the Resolution agent resumed automatically (check the citizen chat).'
                : 'Queue is empty. Upload the scanned salary certificate in the Citizen Portal to trigger a review.'}
            </div>
          )}
          <div className="space-y-2.5">
            {queue.map((d) => (
              <div key={d.documentId} className="border border-line rounded-xl p-3.5 flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <div className="font-bold text-[13.5px]">📄 {d.fileName}</div>
                  <div className="text-[12px] text-muted mt-0.5">
                    {d.docTypeName} · schema v{d.schemaVersion} · quality: {d.quality}
                  </div>
                  <div className="mt-1.5 flex gap-1.5 flex-wrap">
                    {d.fields.filter((f) => f.needsReview).map((f) => (
                      <Badge key={f.key} tone="warn">{f.labelEn}: {Math.round(f.confidence * 100)}% &lt; {Math.round(f.threshold * 100)}%</Badge>
                    ))}
                  </div>
                </div>
                <Btn onClick={() => { setOpen(d); setCorrections({}) }}>Review document</Btn>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <SectionTitle>Document type registry — ministry-owned, no code</SectionTitle>
          {schemas.map((s) => (
            <div key={s.typeId} className="text-[13px]">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold">{s.nameEn}</span>
                <span className="text-muted" dir="rtl">{s.nameAr}</span>
                <Badge tone="doc">schema v{s.version}</Badge>
                <Badge tone="neutral">{s.fields.length} fields</Badge>
              </div>
              <div className="mt-2 overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="text-left text-muted">
                      <th className="py-1 pr-3 font-semibold">Field</th>
                      <th className="py-1 pr-3 font-semibold">Required</th>
                      <th className="py-1 font-semibold">Confidence threshold</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.fields.map((f) => (
                      <tr key={f.key} className="border-t border-line">
                        <td className="py-1.5 pr-3">{f.labelEn}</td>
                        <td className="py-1.5 pr-3">{f.required ? 'yes' : 'no'}</td>
                        <td className="py-1.5 tabnums">{Math.round(f.threshold * 100)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-2 text-[11.5px] text-muted">
                Validations: {s.validations.join(' · ')}
              </div>
            </div>
          ))}
        </Card>
      </div>

      <div className="space-y-4">
        <Card>
          <SectionTitle>Why this matters</SectionTitle>
          <p className="text-[12px] text-muted leading-relaxed">
            MoCE administrators define document types, extraction fields, validation rules, and confidence
            thresholds here — <span className="font-semibold text-ink">no vendor, no code</span>. New document
            types are tested against samples before publishing (schema versioning). Reviewer corrections
            are captured as training data, and MoCE owns all of it.
          </p>
        </Card>
        <Card>
          <SectionTitle>Production swap</SectionTitle>
          <p className="text-[12px] text-muted leading-relaxed">
            This queue is fed by the <span className="font-semibold text-agdoc">Document Processing agent</span> —
            in production: SAS RAM ingestion with PaddleOCR (Arabic + English), table & stamp detection,
            a Visual Text Analytics classifier, and schema-constrained LLM extraction.
          </p>
        </Card>
      </div>

      <Drawer open={!!open} onClose={() => setOpen(null)} title={open ? `Review — ${open.fileName}` : ''} wide>
        {open && (
          <div className="grid grid-cols-2 gap-5">
            <div>
              <SectionTitle>Annotated document</SectionTitle>
              <CertPreview doc={open} highlightKey={open.fields.find((f) => f.needsReview)?.key} />
              <div className="mt-2 text-[11.5px] text-muted">Low-confidence fields are highlighted on the document.</div>
            </div>
            <div>
              <SectionTitle>Extracted fields</SectionTitle>
              <div className="space-y-3">
                {open.fields.map((f) => (
                  <div key={f.key}>
                    <div className="flex items-center justify-between text-[12px]">
                      <span className={`font-semibold ${f.needsReview ? 'text-warn' : ''}`}>{f.labelEn}</span>
                      <Conf value={f.confidence} threshold={f.threshold} />
                    </div>
                    {f.needsReview ? (
                      <input
                        defaultValue={f.value}
                        onChange={(e) => setCorrections((c) => ({ ...c, [f.key]: e.target.value }))}
                        className="mt-1 w-full border-2 border-warn rounded-lg px-2.5 py-1.5 text-[13px] tabnums outline-none focus:border-brand"
                      />
                    ) : (
                      <div className="mt-1 text-[13px] tabnums text-ink">{f.value}</div>
                    )}
                  </div>
                ))}
              </div>
              <div className="mt-5 flex gap-2">
                <Btn onClick={approve}>✓ Approve & resume agent</Btn>
                <Btn tone="ghost" onClick={() => setOpen(null)}>Cancel</Btn>
              </div>
              <div className="mt-3 text-[11.5px] text-muted">
                Approval resumes the Customer Resolution agent automatically — watch the citizen chat.
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  )
}

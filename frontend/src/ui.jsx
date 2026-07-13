// Shared UI primitives. Agent identity colors are fixed (validated palette):
// documents #3a63a8 · knowledge #0b8a6d · case #a4660b · resolution #6d4b9e
export const AGENTS = {
  documents: { color: '#3a63a8', label: 'Document Processing', short: 'Docs' },
  knowledge: { color: '#0b8a6d', label: 'Knowledge & Decision', short: 'Knowledge' },
  case: { color: '#a4660b', label: 'Case Management', short: 'Case' },
  resolution: { color: '#6d4b9e', label: 'Customer Resolution', short: 'Resolution' },
  guard: { color: '#b3261e', label: 'Guardrail', short: 'Guardrail' },
}

export function Card({ children, className = '', pad = true }) {
  return (
    <div className={`bg-panel border border-line rounded-xl shadow-[0_1px_2px_rgba(20,40,30,.05)] ${pad ? 'p-4' : ''} ${className}`}>
      {children}
    </div>
  )
}

export function SectionTitle({ children, right }) {
  return (
    <div className="flex items-center justify-between mb-2.5">
      <h3 className="text-[11px] font-bold uppercase tracking-[0.1em] text-muted">{children}</h3>
      {right}
    </div>
  )
}

export function Badge({ tone = 'neutral', children }) {
  const tones = {
    neutral: 'bg-line/60 text-ink',
    brand: 'bg-brand-soft text-brand',
    gold: 'bg-gold-soft text-gold',
    ok: 'bg-[#e6f2ea] text-ok',
    warn: 'bg-[#f9efe3] text-warn',
    crit: 'bg-[#f9e8e7] text-crit',
    doc: 'bg-[#e9eef7] text-agdoc',
    know: 'bg-[#e5f3ef] text-agknow',
    case: 'bg-[#f7efe2] text-agcase',
    res: 'bg-[#efeaf6] text-agres',
  }
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function AgentChip({ agent }) {
  const a = AGENTS[agent] || AGENTS.resolution
  return (
    <span className="inline-flex items-center gap-1.5 text-[11.5px] font-semibold" style={{ color: a.color }}>
      <span className="w-2 h-2 rounded-full inline-block" style={{ background: a.color }} />
      {a.label}
    </span>
  )
}

export function Conf({ value, threshold }) {
  const below = threshold != null && value < threshold
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="w-16 h-1.5 rounded-full bg-line overflow-hidden inline-block">
        <span className={`block h-full rounded-full ${below ? 'bg-warn' : 'bg-brand'}`} style={{ width: `${value * 100}%` }} />
      </span>
      <span className={`tabnums text-[11.5px] font-semibold ${below ? 'text-warn' : 'text-muted'}`}>{Math.round(value * 100)}%</span>
    </span>
  )
}

export function Stat({ label, value, sub, tone }) {
  return (
    <Card className="flex-1 min-w-[130px]">
      <div className="text-[11px] font-bold uppercase tracking-[0.08em] text-muted">{label}</div>
      <div className={`text-2xl font-extrabold tabnums mt-1 ${tone || 'text-ink'}`}>{value}</div>
      {sub && <div className="text-[11.5px] text-muted mt-0.5">{sub}</div>}
    </Card>
  )
}

export function Btn({ children, onClick, tone = 'brand', disabled, small }) {
  const tones = {
    brand: 'bg-brand text-white hover:bg-brand-deep',
    ghost: 'bg-transparent border border-line text-ink hover:bg-line/40',
    warn: 'bg-warn text-white hover:opacity-90',
    crit: 'bg-crit text-white hover:opacity-90',
  }
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`${tones[tone]} ${small ? 'px-2.5 py-1 text-[12px]' : 'px-3.5 py-1.5 text-[13px]'} rounded-lg font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand`}
    >
      {children}
    </button>
  )
}

export function Drawer({ open, onClose, title, children, wide }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-ink/30" onClick={onClose} />
      <div className={`relative h-full ${wide ? 'w-[760px]' : 'w-[520px]'} max-w-[95vw] bg-paper shadow-2xl overflow-y-auto fade-up`}>
        <div className="sticky top-0 bg-paper/95 backdrop-blur border-b border-line px-5 py-3.5 flex items-center justify-between z-10">
          <div className="font-bold text-[15px]">{title}</div>
          <button onClick={onClose} aria-label="Close" className="text-muted hover:text-ink text-xl leading-none px-1">×</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export function Markdownish({ text, className = '' }) {
  // minimal **bold** + newline renderer for scripted answers
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g)
  return (
    <div className={`md-strong whitespace-pre-wrap leading-relaxed ${className}`}>
      {parts.map((p, i) =>
        p.startsWith('**') ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>
      )}
    </div>
  )
}

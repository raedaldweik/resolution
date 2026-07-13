// Shared UI primitives — glass design system (Finance/NCGR assistant recipe, MoCE theme).
// Agent identity colors are fixed (validated palette):
// documents #3a63a8 · knowledge #0b8a6d · case #a4660b · resolution #6d4b9e
export const AGENTS = {
  documents: { color: '#3a63a8', label: 'Document Processing', short: 'Docs' },
  knowledge: { color: '#0b8a6d', label: 'Knowledge & Decision', short: 'Knowledge' },
  case: { color: '#a4660b', label: 'Case Management', short: 'Case' },
  resolution: { color: '#6d4b9e', label: 'Customer Resolution', short: 'Resolution' },
  guard: { color: '#b91c2c', label: 'Guardrail', short: 'Guardrail' },
}

export function Card({ children, className = '', pad = true }) {
  return <div className={`glass-card ${pad ? 'p-4' : ''} ${className}`}>{children}</div>
}

export function SectionTitle({ children, right }) {
  return (
    <div className="flex items-center justify-between mb-3 gap-3">
      <h3 className="panel-title">{children}</h3>
      {right}
    </div>
  )
}

export function Badge({ tone = 'neutral', children }) {
  const tones = {
    neutral: 'bg-ink/[0.06] text-ink-2',
    brand: 'bg-brand-soft text-brand-lo',
    gold: 'bg-gold-soft text-[#8a6a28]',
    ok: 'bg-[rgba(4,120,87,0.10)] text-ok',
    warn: 'bg-[rgba(180,83,9,0.10)] text-warn',
    crit: 'bg-[rgba(185,28,44,0.09)] text-crit',
    doc: 'bg-[rgba(58,99,168,0.10)] text-agdoc',
    know: 'bg-[rgba(11,138,109,0.10)] text-agknow',
    case: 'bg-[rgba(164,102,11,0.10)] text-agcase',
    res: 'bg-[rgba(109,75,158,0.10)] text-agres',
  }
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10.5px] font-bold whitespace-nowrap ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function AgentChip({ agent }) {
  const a = AGENTS[agent] || AGENTS.resolution
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-bold" style={{ color: a.color }}>
      <span className="w-2 h-2 rounded-full inline-block" style={{ background: a.color }} />
      {a.label}
    </span>
  )
}

export function Conf({ value, threshold }) {
  const below = threshold != null && value < threshold
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="w-16 h-1.5 rounded-full bg-ink/10 overflow-hidden inline-block">
        <span className={`block h-full rounded-full ${below ? 'bg-warn' : 'bg-brand'}`} style={{ width: `${value * 100}%` }} />
      </span>
      <span className={`tabnums text-[11px] font-bold ${below ? 'text-warn' : 'text-muted'}`}>{Math.round(value * 100)}%</span>
    </span>
  )
}

export function Stat({ label, value, sub, tone }) {
  return (
    <Card className="flex-1 min-w-[140px]">
      <div className="panel-title">{label}</div>
      <div className={`text-[26px] font-extrabold tabnums mt-2 ${tone || 'text-ink'}`}>{value}</div>
      {sub && <div className="text-[11.5px] text-muted mt-0.5">{sub}</div>}
    </Card>
  )
}

export function Btn({ children, onClick, tone = 'brand', disabled, small }) {
  const cls = tone === 'brand' ? 'btn-primary' : 'btn-ghost'
  return (
    <button onClick={onClick} disabled={disabled}
      className={`${cls} ${small ? 'px-3 py-1.5 text-[12px]' : 'px-4 py-2 text-[13px]'}`}>
      {children}
    </button>
  )
}

export function Drawer({ open, onClose, title, children, wide }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-ink/25 backdrop-blur-[2px]" onClick={onClose} />
      <div className={`relative h-full ${wide ? 'w-[780px]' : 'w-[540px]'} max-w-[95vw] overflow-y-auto fade-up`}
        style={{ background: 'linear-gradient(140deg, #f7f3ec 0%, #eef0f2 55%, #f2ecdf 100%)', boxShadow: '-18px 0 60px rgba(15,23,42,0.22)' }}>
        <div className="sticky top-0 z-10 px-5 py-4 flex items-center justify-between border-b border-ink/10"
          style={{ background: 'rgba(247,243,236,0.92)', backdropFilter: 'blur(14px)' }}>
          <div className="font-extrabold text-[15px] text-ink">{title}</div>
          <button onClick={onClose} aria-label="Close" className="text-muted hover:text-ink text-xl leading-none px-1.5">×</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export function Markdownish({ text, className = '' }) {
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g)
  return (
    <div className={`md-strong whitespace-pre-wrap leading-relaxed ${className}`}>
      {parts.map((p, i) =>
        p.startsWith('**') ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { api } from './api'
import Portal from './views/Portal'
import ContactCenter from './views/ContactCenter'
import Documents from './views/Documents'
import Cases from './views/Cases'
import Decisioning from './views/Decisioning'
import Governance from './views/Governance'

const NAV = [
  { key: 'portal', icon: '🧕', label: 'Citizen Portal', sub: 'Customer Resolution · UAEPass', agent: '#6d4b9e' },
  { key: 'contact', icon: '🎧', label: 'Contact Center', sub: 'Supervised AI · escalations', agent: '#6d4b9e' },
  { key: 'documents', icon: '📄', label: 'Document Review', sub: 'Agent 1 · HITL queue', agent: '#3a63a8' },
  { key: 'cases', icon: '🗂️', label: 'Case Management', sub: 'Agent 3 · two-stage approval', agent: '#a4660b' },
  { key: 'decisioning', icon: '⚖️', label: 'Decision Studio', sub: 'Intelligent Decisioning', agent: '#0b8a6d' },
  { key: 'governance', icon: '🛡️', label: 'Governance', sub: 'Traces · metrics · drift', agent: '#0e3d2f' },
]

export default function App() {
  const [view, setView] = useState('portal')
  const [lang, setLang] = useState('en')

  useEffect(() => { api.meta().catch(() => {}) }, [])

  const reset = async () => {
    await api.reset()
    window.location.reload()
  }

  return (
    <div className="h-full flex">
      {/* sidebar */}
      <aside className="w-[250px] shrink-0 bg-brand-deep text-white flex flex-col">
        <div className="px-5 pt-6 pb-5 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-white/10 flex items-center justify-center text-lg">🇦🇪</div>
            <div>
              <div className="font-extrabold text-[14px] leading-tight">MoCE Agent Ecosystem</div>
              <div className="text-[10.5px] text-white/60">Ministry of Community Empowerment</div>
            </div>
          </div>
          <div className="mt-3 inline-flex items-center gap-1.5 bg-gold/20 text-[#e8d49a] rounded-full px-2.5 py-1 text-[10.5px] font-bold tracking-wide">
            ⚡ SIMULATION — SAS swap-ready
          </div>
        </div>
        <nav className="flex-1 py-3 px-3 space-y-1">
          {NAV.map((n) => (
            <button key={n.key} onClick={() => setView(n.key)}
              className={`w-full text-left rounded-xl px-3 py-2.5 transition flex items-center gap-3
                ${view === n.key ? 'bg-white/10 shadow-inner' : 'hover:bg-white/5'}`}>
              <span className="text-lg">{n.icon}</span>
              <span className="min-w-0">
                <span className="block text-[13px] font-bold leading-tight">{n.label}</span>
                <span className="block text-[10.5px] text-white/55 truncate">{n.sub}</span>
              </span>
              <span className="ml-auto w-1.5 h-6 rounded-full" style={{ background: view === n.key ? n.agent : 'transparent' }} />
            </button>
          ))}
        </nav>
        <div className="p-4 border-t border-white/10 text-[10.5px] text-white/50 leading-relaxed">
          Golden path: Portal → upload scan → Document Review → Portal (proposal) → confirm → Cases (2-stage) →
          Decision Studio (live rule change) → Governance.
        </div>
      </aside>

      {/* main */}
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-[58px] shrink-0 bg-panel border-b border-line px-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="font-extrabold text-[16px]">{NAV.find((n) => n.key === view)?.label}</h1>
            <span className="text-[11px] text-muted hidden md:block">{NAV.find((n) => n.key === view)?.sub}</span>
          </div>
          <div className="flex items-center gap-2.5">
            {view === 'portal' && (
              <div className="flex rounded-lg border border-line overflow-hidden text-[12px] font-bold">
                <button onClick={() => setLang('en')} className={`px-3 py-1.5 ${lang === 'en' ? 'bg-brand text-white' : 'bg-panel text-muted'}`}>EN</button>
                <button onClick={() => setLang('ar')} className={`px-3 py-1.5 ${lang === 'ar' ? 'bg-brand text-white' : 'bg-panel text-muted'}`}>العربية</button>
              </div>
            )}
            <button onClick={reset} className="text-[12px] font-semibold text-muted border border-line rounded-lg px-3 py-1.5 hover:text-ink hover:bg-line/40 transition">
              ↺ Reset demo
            </button>
          </div>
        </header>
        {/* keep every view mounted so chat sessions and polling survive navigation */}
        <main className="flex-1 min-h-0 p-4">
          <div className={view === 'portal' ? 'h-full' : 'hidden'}><Portal lang={lang} /></div>
          <div className={view === 'contact' ? 'h-full' : 'hidden'}><ContactCenter /></div>
          <div className={view === 'documents' ? 'h-full' : 'hidden'}><Documents /></div>
          <div className={view === 'cases' ? 'h-full' : 'hidden'}><Cases /></div>
          <div className={view === 'decisioning' ? 'h-full' : 'hidden'}><Decisioning /></div>
          <div className={view === 'governance' ? 'h-full' : 'hidden'}><Governance /></div>
        </main>
      </div>
    </div>
  )
}

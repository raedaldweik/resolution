import { useState } from 'react'
import { api } from './api'
import { GovLockup } from './ui'
import Portal from './views/Portal'
import ContactCenter from './views/ContactCenter'
import Documents from './views/Documents'
import Cases from './views/Cases'
import Decisioning from './views/Decisioning'
import Governance from './views/Governance'

const NAV = [
  { key: 'portal', icon: '🧕', label: 'Citizen Portal', accent: '#6d4b9e' },
  { key: 'contact', icon: '🎧', label: 'Contact Center', accent: '#6d4b9e' },
  { key: 'documents', icon: '📄', label: 'Document Review', accent: '#3a63a8' },
  { key: 'cases', icon: '🗂️', label: 'Case Management', accent: '#a4660b' },
  { key: 'decisioning', icon: '⚖️', label: 'Decision Studio', accent: '#0b8a6d' },
  { key: 'governance', icon: '🛡️', label: 'Governance', accent: '#8a6a28' },
]


function Bokeh() {
  return (
    <div className="bokeh-layer" aria-hidden="true">
      <div className="bokeh-dot mega-green b1" /><div className="bokeh-dot mega-blue b2" />
      <div className="bokeh-dot mega-gold b3" /><div className="bokeh-dot mega-green b4" />
      <div className="bokeh-dot mega-blue b5" />
      <div className="bokeh-dot blob-green s1" /><div className="bokeh-dot blob-gold s2" />
      <div className="bokeh-dot blob-blue s3" /><div className="bokeh-dot blob-green s4" />
      <div className="bokeh-dot blob-gold s5" /><div className="bokeh-dot blob-blue s6" />
    </div>
  )
}

export default function App() {
  const [view, setView] = useState('portal')
  const [lang, setLang] = useState('en')

  const reset = async () => { await api.reset(); window.location.reload() }

  return (
    <div className="app-shell">
      <Bokeh />

      <header className="app-header">
        <GovLockup />
        <div className="accent-line" />
        <div className="app-title">Agent Ecosystem</div>
        <div className="status-pill"><span className="status-dot" /> SIMULATION · SAS swap-ready</div>
        {view === 'portal' && (
          <div className="flex rounded-full overflow-hidden border border-ink/10" style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.8)' }}>
            <button onClick={() => setLang('en')}
              className={`px-3.5 py-1.5 text-[11.5px] font-extrabold transition ${lang === 'en' ? 'btn-primary rounded-none' : 'text-muted bg-white/60'}`}>EN</button>
            <button onClick={() => setLang('ar')}
              className={`px-3.5 py-1.5 text-[11.5px] font-extrabold transition ${lang === 'ar' ? 'btn-primary rounded-none' : 'text-muted bg-white/60'}`}>العربية</button>
          </div>
        )}
        <button onClick={reset} className="btn-ghost px-3.5 py-1.5 text-[12px]">↺ Reset</button>
      </header>

      <nav className="view-tabs" aria-label="Demo views">
        {NAV.map((n) => (
          <button key={n.key} onClick={() => setView(n.key)}
            className={`view-tab ${view === n.key ? 'active' : ''}`}
            style={{ '--tab-accent': n.accent }}>
            <span className="tab-dot" />
            <span>{n.icon}</span> {n.label}
          </button>
        ))}
      </nav>

      {/* keep every view mounted so chat sessions and polling survive navigation */}
      <main className="flex-1 min-h-0 p-4 md:px-6 relative z-[1]">
        <div className={view === 'portal' ? 'h-full' : 'hidden'}><Portal lang={lang} /></div>
        <div className={view === 'contact' ? 'h-full' : 'hidden'}><ContactCenter /></div>
        <div className={view === 'documents' ? 'h-full' : 'hidden'}><Documents /></div>
        <div className={view === 'cases' ? 'h-full' : 'hidden'}><Cases /></div>
        <div className={view === 'decisioning' ? 'h-full' : 'hidden'}><Decisioning /></div>
        <div className={view === 'governance' ? 'h-full' : 'hidden'}><Governance /></div>
      </main>
    </div>
  )
}

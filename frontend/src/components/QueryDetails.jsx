import { useState, useEffect } from 'react';
import { getQueryTrace } from '../services/api';

const fmt = (v) => {
  if (v == null) return '';
  if (typeof v === 'string') return v;
  try { return JSON.stringify(v, null, 2); } catch { return String(v); }
};

function Section({ title, count, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(138,106,40,0.14)' }}>
      <button onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left transition-all hover:bg-[rgba(138,106,40,0.04)]"
        style={{ background: 'rgba(138,106,40,0.05)' }}>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--gold)" strokeWidth="2.5"
          style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }}>
          <polyline points="9 18 15 12 9 6" />
        </svg>
        <span className="text-[12px] font-bold" style={{ color: 'var(--text)' }}>{title}</span>
        {count != null && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full font-bold"
            style={{ background: 'rgba(138,106,40,0.10)', color: 'var(--gold)' }}>{count}</span>
        )}
      </button>
      {open && <div className="px-4 py-3 space-y-3">{children}</div>}
    </div>
  );
}

function Mono({ label, value, max = 4000 }) {
  if (value == null || value === '') return null;
  const text = fmt(value);
  return (
    <div>
      {label && <p className="text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: 'var(--text-dim)' }}>{label}</p>}
      <pre className="text-[11px] px-2.5 py-2 rounded-lg whitespace-pre-wrap break-all max-h-[260px] overflow-y-auto font-mono leading-[1.6]"
        style={{ background: 'rgba(15,23,42,0.035)', color: 'var(--text-md)', border: '1px solid rgba(15,23,42,0.06)' }}>
        {text.slice(0, max)}{text.length > max ? '\n… (truncated)' : ''}
      </pre>
    </div>
  );
}

const Pill = ({ children }) => (
  <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
    style={{ background: 'rgba(138,106,40,0.08)', color: 'var(--gold-lo)', border: '1px solid rgba(138,106,40,0.15)' }}>
    {children}
  </span>
);

/** Full traceability popup for one answer: the question, tool calls with
 *  inputs/outputs, LLM calls, retrieval (RAG) calls, retrieved passages,
 *  and token usage — pulled from RAM's /toolCalls, /llmCalls, and
 *  /retrievalCalls resources for this query. */
export default function QueryDetails({ data, query, onClose, onOpenSource }) {
  const [trace, setTrace] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!data?.queryId) { setLoading(false); return; }
    getQueryTrace(data.queryId)
      .then(setTrace)
      .catch(() => setTrace(null))
      .finally(() => setLoading(false));
  }, [data?.queryId]);

  if (!data) return null;
  const usage = data.usage || {};
  const toolCalls = trace?.toolCalls?.length ? trace.toolCalls : (data.toolCalls || []);
  const llmCalls = trace?.llmCalls || [];
  const retrievalCalls = trace?.retrievalCalls || [];
  const context = data.context || [];

  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-6" onClick={onClose}
      style={{ background: 'rgba(10,37,64,0.45)', backdropFilter: 'blur(4px)' }}>
      <div className="glass-card w-full max-w-[760px] max-h-[85vh] flex flex-col animate-slide-up"
        onClick={e => e.stopPropagation()} style={{ background: 'rgba(255,255,255,0.96)' }}>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[rgba(138,106,40,0.10)]">
          <div className="flex items-center gap-2 min-w-0">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--gold)" strokeWidth="2" className="shrink-0">
              <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
              <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
            </svg>
            <span className="text-sm font-bold" style={{ color: 'var(--text)' }}>Query details</span>
            {loading && <span className="text-[10.5px] animate-pulse" style={{ color: 'var(--text-dim)' }}>loading trace…</span>}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-[rgba(138,106,40,0.08)]" style={{ color: 'var(--text-dim)' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">

          {/* Question */}
          <div className="rounded-xl px-4 py-3" style={{ background: 'rgba(138,106,40,0.05)', border: '1px solid rgba(138,106,40,0.14)' }}>
            <p className="text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: 'var(--text-dim)' }}>Input prompt</p>
            <p className="text-[12.5px] leading-relaxed" style={{ color: 'var(--text)' }}>{query || data.content || '(unknown)'}</p>
          </div>

          {/* Usage summary */}
          <div className="flex flex-wrap gap-2">
            {data.target && <Pill>target: {data.target}</Pill>}
            {usage.llmTotalTokens != null && <Pill>{usage.llmTotalTokens.toLocaleString()} tokens</Pill>}
            {usage.llmPromptTokens != null && <Pill>{usage.llmPromptTokens.toLocaleString()} prompt / {usage.llmCompletionTokens?.toLocaleString() ?? 0} completion</Pill>}
            {usage.llmTotalCost != null && <Pill>${Number(usage.llmTotalCost).toFixed(4)}</Pill>}
            {data.queryId && <Pill>query {String(data.queryId).slice(0, 8)}…</Pill>}
          </div>

          {/* Tool calls */}
          <Section title="Tool calls" count={toolCalls.length} defaultOpen={toolCalls.length > 0}>
            {toolCalls.length === 0 && <p className="text-[11.5px]" style={{ color: 'var(--text-dim)' }}>No tool calls recorded for this query.</p>}
            {toolCalls.map((c, i) => (
              <div key={c.id || i} className="rounded-lg px-3 py-2.5 space-y-2" style={{ border: '1px solid rgba(138,106,40,0.10)' }}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0"
                    style={{ background: 'rgba(138,106,40,0.12)', color: 'var(--gold)' }}>{i + 1}</span>
                  <span className="text-[12px] font-bold font-mono" style={{ color: 'var(--gold-lo)' }}>{c.toolName || 'tool'}</span>
                  {c.output?.isError && <Pill>error</Pill>}
                  {c.cost != null && c.cost > 0 && <Pill>${Number(c.cost).toFixed(4)}</Pill>}
                </div>
                <Mono label="Input" value={c.input} />
                <Mono label="Output" value={c.output?.structuredContent ?? c.output?.content ?? c.output} />
              </div>
            ))}
          </Section>

          {/* Retrieval (RAG) calls */}
          <Section title="Retrieval calls (RAG)" count={retrievalCalls.length}>
            {retrievalCalls.length === 0 && <p className="text-[11.5px]" style={{ color: 'var(--text-dim)' }}>No retrieval calls recorded for this query.</p>}
            {retrievalCalls.map((c, i) => (
              <div key={c.id || i} className="rounded-lg px-3 py-2.5 space-y-2" style={{ border: '1px solid rgba(138,106,40,0.10)' }}>
                <Mono label="Input" value={c.input} />
                <Mono label="Output" value={c.output} />
              </div>
            ))}
          </Section>

          {/* LLM calls */}
          <Section title="LLM calls" count={llmCalls.length}>
            {llmCalls.length === 0 && <p className="text-[11.5px]" style={{ color: 'var(--text-dim)' }}>No LLM calls recorded for this query.</p>}
            {llmCalls.map((c, i) => (
              <div key={c.id || i} className="rounded-lg px-3 py-2.5 space-y-2" style={{ border: '1px solid rgba(138,106,40,0.10)' }}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[12px] font-bold font-mono" style={{ color: 'var(--gold-lo)' }}>
                    {c.input?.modelName || 'LLM'}
                  </span>
                  {c.input?.modelProvider && <Pill>{c.input.modelProvider}</Pill>}
                  {c.input?.temperature != null && <Pill>temp {c.input.temperature}</Pill>}
                  {(c.promptTokens != null || c.completionTokens != null) && (
                    <Pill>{c.promptTokens ?? 0} prompt / {c.completionTokens ?? 0} completion tok</Pill>
                  )}
                  {(c.promptCost != null || c.completionCost != null) && (
                    <Pill>${(Number(c.promptCost || 0) + Number(c.completionCost || 0)).toFixed(4)}</Pill>
                  )}
                </div>
                <Mono label="Prompt" value={c.input?.content} />
                <Mono label="Response" value={c.output?.response} />
              </div>
            ))}
          </Section>

          {/* Retrieved passages */}
          <Section title="Retrieved context" count={context.length}>
            {context.length === 0 && <p className="text-[11.5px]" style={{ color: 'var(--text-dim)' }}>No context passages attached to this answer.</p>}
            {context.map((doc, i) => {
              const meta = doc?.metadata || {};
              const label = meta.filename || meta.source || meta.file_name || meta.title || `Source ${i + 1}`;
              return (
                <div key={i} className="rounded-lg px-3 py-2.5" style={{ border: '1px solid rgba(138,106,40,0.10)' }}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-[11.5px] font-bold truncate" style={{ color: 'var(--gold-lo)' }}>{label}</span>
                    {meta.page != null && <Pill>p. {meta.page}</Pill>}
                    {onOpenSource && (
                      <button onClick={() => onOpenSource(doc)} className="text-[10.5px] font-semibold hover:underline ml-auto shrink-0"
                        style={{ color: 'var(--gold)' }}>open ↗</button>
                    )}
                  </div>
                  <p className="text-[11.5px] leading-[1.7] whitespace-pre-wrap max-h-[140px] overflow-y-auto" style={{ color: 'var(--text-md)' }}>
                    {doc.pageContent || doc.page_content || doc.content || '(no text)'}
                  </p>
                </div>
              );
            })}
          </Section>
        </div>
      </div>
    </div>
  );
}

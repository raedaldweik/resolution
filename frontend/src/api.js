const j = (r) => {
  if (!r.ok) throw new Error(`API ${r.status}`)
  return r.json()
}
const get = (url) => fetch(url).then(j)
const post = (url, body) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }).then(j)

export const api = {
  meta: () => get('/api/meta'),
  reset: () => post('/api/demo/reset'),
  createSession: (channel, citizenId) => post('/api/session', { channel, citizenId }),
  chat: (sessionId, message, lang) => post('/api/chat', { sessionId, message, lang }),
  events: (sessionId) => get(`/api/session/${sessionId}/events`),
  upload: (sessionId, docKey) => post('/api/documents/upload', { sessionId, docKey }),
  reviewQueue: () => get('/api/documents/queue'),
  review: (docId, corrections) => post(`/api/documents/${docId}/review`, { corrections }),
  schemas: () => get('/api/documents/schemas'),
  citizen: (eid) => get(`/api/citizens/${eid}`),
  escalations: () => get('/api/escalations'),
  cases: () => get('/api/cases'),
  approve: (caseId, stage, actor, decision) => post(`/api/cases/${caseId}/approve`, { stage, actor, decision }),
  autonomy: () => get('/api/autonomy'),
  decisioning: () => get('/api/decisioning'),
  updateRule: (ruleId, params) => post(`/api/decisioning/rules/${ruleId}`, { params }),
  publish: (note) => post('/api/decisioning/publish', { note }),
  testFlow: (citizenId, version) => post('/api/decisioning/test', { citizenId, version }),
  traces: () => get('/api/governance/traces'),
  trace: (id) => get(`/api/governance/traces/${id}`),
  metrics: () => get('/api/governance/metrics'),
}

export type AgentSource = 'page_canonical' | 'handoff_imported' | 'analysis_result' | string
export interface AgentPage { page: string; active?: boolean; pinned?: boolean; since?: number; active_at?: number }
export interface AgentAction { name: string; args: Record<string, unknown> }
export interface AgentPlan {
  plan_id: string
  status: string
  page_id: string
  expected_revision: string
  actions: AgentAction[]
  results?: Array<Record<string, unknown>>
  state_revision?: string
  canonical?: AgentSnapshot
}
export interface AgentSnapshot {
  page_id: string
  state_revision: string
  source: AgentSource
  dataset?: { id?: string; name?: string; [key: string]: unknown }
  selection?: { group?: string | null; n_cells?: number | null; [key: string]: unknown } | null
  locus?: { chrom?: string; start?: number; end?: number } | null
  views?: Array<{ pane?: string; type?: string; [key: string]: unknown }>
  layout?: string
  [key: string]: unknown
}

async function agentRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) } })
  if (!response.ok) {
    let detail = String(response.status) + ' ' + response.statusText
    try {
      const body = await response.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* plain error response */ }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export const agentPages = () => agentRequest<AgentPage[]>('api/agent/pages')
export const attachAgentPage = (pageId: string) =>
  agentRequest<{ page_id: string; state_revision: string; status: string }>('api/agent/attach', { method: 'POST', body: JSON.stringify({ page_id: pageId }) })
export const loadAgentSnapshot = (pageId: string) =>
  agentRequest<AgentSnapshot>('api/agent/snapshot?' + new URLSearchParams({ page: pageId }))
export const pendingAgentPlans = (pageId?: string) =>
  agentRequest<AgentPlan[]>(pageId ? 'api/agent/plans?' + new URLSearchParams({ page: pageId }) : 'api/agent/plans')
export const loadPlanStatus = (planId: string) => agentRequest<AgentPlan>('api/agent/plans/' + encodeURIComponent(planId))
export const approveAgentPlan = (planId: string) =>
  agentRequest<AgentPlan>('api/agent/plans/' + encodeURIComponent(planId) + '/approve', { method: 'POST' })
export const rejectAgentPlan = (planId: string) =>
  agentRequest<AgentPlan>('api/agent/plans/' + encodeURIComponent(planId) + '/reject', { method: 'POST' })
export const applyAgentPlan = (planId: string) =>
  agentRequest<AgentPlan>('api/agent/plans/' + encodeURIComponent(planId) + '/apply', { method: 'POST' })

export function sourceLabel(source: AgentSource): string {
  return { page_canonical: 'Page canonical', handoff_imported: 'Handoff imported', analysis_result: 'Analysis result' }[source] ?? source
}
export function planStatusLabel(status: string): string {
  return { pending: 'Pending', approved: 'Approved', rejected: 'Rejected', stale: 'Stale', applied: 'Applied', failed: 'Failed' }[status] ?? status
}
export function formatLocus(locus: AgentSnapshot['locus']): string {
  if (!locus?.chrom) return '—'
  if (typeof locus.start !== 'number' || typeof locus.end !== 'number') return locus.chrom
  return locus.chrom + ':' + locus.start.toLocaleString() + '–' + locus.end.toLocaleString()
}
export function pendingPlanView(canonical: AgentSnapshot, plan: AgentPlan): { canonical: AgentSnapshot; requestedActions: AgentAction[] } {
  return { canonical, requestedActions: plan.actions }
}
export function formatAction(action: AgentAction): string {
  const args = Object.entries(action.args ?? {}).map(([key, value]) => key + '=' + (typeof value === 'string' ? value : JSON.stringify(value))).join(', ')
  return args ? action.name + ' (' + args + ')' : action.name
}

export type AgentSource = 'page_canonical' | 'handoff_imported' | 'analysis_result' | string
export interface AgentPage { page: string; active?: boolean; pinned?: boolean; since?: number; active_at?: number }
export type AgentSetupStage = 'not_running' | 'browser_ready' | 'page_connected' | 'page_pinned'
export interface AgentSetupStatus { stage: AgentSetupStage; pages: AgentPage[]; selected_page_id?: string }
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
  can_undo?: boolean
  undo_reason?: string
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

interface AgentSessionProof { token: string; csrf_token: string; expires_in?: number }
let sessionProof: AgentSessionProof | null = null
let sessionPromise: Promise<AgentSessionProof> | null = null

export async function initAgentSession(): Promise<AgentSessionProof> {
  if (sessionProof) return sessionProof
  if (!sessionPromise) {
    sessionPromise = fetch('api/control/session')
      .then(async (response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
        return response.json() as Promise<AgentSessionProof>
      })
      .then((proof) => { sessionProof = proof; return proof })
      .finally(() => { sessionPromise = null })
  }
  return sessionPromise
}

async function agentRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? 'GET'
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(init?.headers as Record<string, string> ?? {}) }
  if (method !== 'GET' && method !== 'HEAD') {
    const proof = await initAgentSession()
    headers.Authorization = `Bearer ${proof.token}`
    headers['X-CSRF-Token'] = proof.csrf_token
  }
  const response = await fetch(path, { ...init, headers })
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
export function setupStageForPage(status: Pick<AgentSetupStatus, 'stage' | 'pages'>, selectedPageId?: string): AgentSetupStage {
  if (status.stage === 'not_running') return 'not_running'
  if (!selectedPageId) return status.stage
  const selected = status.pages.find((page) => page.page === selectedPageId)
  if (selected) return selected.pinned ? 'page_pinned' : 'page_connected'
  return status.pages.length > 0 ? 'page_connected' : 'browser_ready'
}

export async function agentSetupStatus(selectedPageId?: string): Promise<AgentSetupStatus> {
  try {
    await agentRequest<Record<string, unknown>>('api/health')
  } catch {
    return { stage: 'not_running', pages: [], ...(selectedPageId ? { selected_page_id: selectedPageId } : {}) }
  }
  const pages = await agentPages()
  const globalStage: AgentSetupStage = pages.some((page) => page.pinned)
    ? 'page_pinned'
    : pages.length > 0 ? 'page_connected' : 'browser_ready'
  const stage = setupStageForPage({ stage: globalStage, pages }, selectedPageId)
  return { stage, pages, ...(selectedPageId ? { selected_page_id: selectedPageId } : {}) }
}
export const attachAgentPage = (pageId: string) =>
  agentRequest<{ page_id: string; state_revision: string; status: string }>('api/agent/attach', { method: 'POST', body: JSON.stringify({ page_id: pageId }) })
export const loadAgentSnapshot = (pageId: string) =>
  agentRequest<AgentSnapshot>('api/agent/snapshot?' + new URLSearchParams({ page: pageId }))
export const pendingAgentPlans = (pageId?: string) =>
  agentRequest<AgentPlan[]>(pageId ? 'api/agent/plans?' + new URLSearchParams({ page: pageId }) : 'api/agent/plans')
export const loadPlanStatus = (planId: string) => agentRequest<AgentPlan>('api/agent/plans/' + encodeURIComponent(planId))
export const approveAgentPlan = (planId: string) =>
  agentRequest<AgentPlan>('api/agent/ui/plans/' + encodeURIComponent(planId) + '/approve', { method: 'POST' })
export const rejectAgentPlan = (planId: string) =>
  agentRequest<AgentPlan>('api/agent/ui/plans/' + encodeURIComponent(planId) + '/reject', { method: 'POST' })
export const applyAgentPlan = (planId: string) =>
  agentRequest<AgentPlan>('api/agent/ui/plans/' + encodeURIComponent(planId) + '/apply', { method: 'POST' })
export const agentHistory = (pageId: string) =>
  agentRequest<AgentPlan[]>('api/agent/history?' + new URLSearchParams({ page: pageId }))
export const undoAgentPlan = (planId: string, pageId: string, expectedRevision: string) =>
  agentRequest<AgentPlan>('api/agent/ui/plans/' + encodeURIComponent(planId) + '/undo?' + new URLSearchParams({ page_id: pageId, expected_revision: expectedRevision }), { method: 'POST' })

export function sourceLabel(source: AgentSource): string {
  return { page_canonical: 'Page canonical', handoff_imported: 'Handoff imported', analysis_result: 'Analysis result' }[source] ?? source
}
export function setupStageLabel(stage: AgentSetupStage | string): string {
  return {
    not_running: 'Not running',
    browser_ready: 'Browser ready',
    page_connected: 'Page connected',
    page_pinned: 'Page pinned',
  }[stage] ?? stage
}
export function nextSetupAction(stage: AgentSetupStage | string): string {
  return {
    not_running: 'Start local WebUI',
    browser_ready: 'Open local page',
    page_connected: 'Pin page',
    page_pinned: 'Ready for analysis',
  }[stage] ?? 'Check local WebUI'
}
export function planStatusLabel(status: string): string {
  return { pending: 'Pending', approved: 'Approved', rejected: 'Rejected', stale: 'Stale', applied: 'Applied', failed: 'Failed', undone: 'Undone' }[status] ?? status
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

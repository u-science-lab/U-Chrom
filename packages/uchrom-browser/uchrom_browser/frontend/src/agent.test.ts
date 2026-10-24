import { describe, expect, it, vi } from 'vitest'
import { agentHistory, agentSetupStatus, approveAgentPlan, applyAgentPlan, nextSetupAction, planStatusLabel, rejectAgentPlan, setupStageLabel, setupStageForPage, sourceLabel, pendingPlanView, type AgentPlan, type AgentSnapshot } from './agent'

const snapshot: AgentSnapshot = {
  page_id: 'ptest',
  state_revision: 'r_2',
  source: 'page_canonical',
  dataset: { id: 'd1', name: 'Toy' },
  selection: { group: 'g1', n_cells: 3 },
  locus: { chrom: 'chr1', start: 10, end: 100 },
  views: [{ pane: 'P1', type: '3d' }],
  layout: 'tabs',
}

describe('agent state helpers', () => {
  it('labels setup stages and next actions for the local connection flow', () => {
    expect(setupStageLabel('not_running')).toContain('Not running')
    expect(nextSetupAction('not_running')).toBe('Start local WebUI')
    expect(nextSetupAction('browser_ready')).toBe('Open local page')
    expect(nextSetupAction('page_connected')).toBe('Pin page')
    expect(nextSetupAction('page_pinned')).toBe('Ready for analysis')
  })

  it('reads setup status from health and connected pages through the API boundary', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
      paths.push(String(input))
      if (String(input) === 'api/health') return new Response(JSON.stringify({ status: 'ok' }), { status: 200 })
      return new Response(JSON.stringify([{ page: 'p1', pinned: true }]), { status: 200 })
    })
    const status = await agentSetupStatus()
    expect(status.stage).toBe('page_pinned')
    expect(paths).toEqual(['api/health', 'api/agent/pages'])
    vi.unstubAllGlobals()
  })

  it('derives setup stage from the selected page rather than any pinned page', () => {
    const status = {
      stage: 'page_pinned' as const,
      pages: [{ page: 'p1', pinned: true }, { page: 'p2', pinned: false }],
    }
    expect(setupStageForPage(status, 'p1')).toBe('page_pinned')
    expect(setupStageForPage(status, 'p2')).toBe('page_connected')
  })

  it('labels each snapshot source distinctly', () => {
    expect(sourceLabel('page_canonical')).toBe('Page canonical')
    expect(sourceLabel('handoff_imported')).toBe('Handoff imported')
    expect(sourceLabel('analysis_result')).toBe('Analysis result')
  })

  it('keeps pending requested actions separate from the canonical snapshot', () => {
    const plan: AgentPlan = {
      plan_id: 'p1',
      status: 'pending',
      page_id: 'ptest',
      expected_revision: 'r_2',
      actions: [{ name: 'set_locus', args: { chrom: 'chr2', start: 1, end: 2 } }],
    }
    const view = pendingPlanView(snapshot, plan)
    expect(view.canonical).toBe(snapshot)
    expect(view.requestedActions).toEqual(plan.actions)
    expect(view.canonical.locus).toEqual(snapshot.locus)
  })

  it('maps plan statuses to stable labels', () => {
    expect(planStatusLabel('stale')).toBe('Stale')
    expect(planStatusLabel('rejected')).toBe('Rejected')
    expect(planStatusLabel('applied')).toBe('Applied')
  })

  it('routes approval, rejection, apply, and history through the UI-only endpoints', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
      paths.push(String(input))
      return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    await approveAgentPlan('p1')
    await rejectAgentPlan('p1')
    await applyAgentPlan('p1')
    await agentHistory('ptest')
    expect(paths).toEqual([
      'api/control/session',
      'api/agent/ui/plans/p1/approve',
      'api/agent/ui/plans/p1/reject',
      'api/agent/ui/plans/p1/apply',
      'api/agent/history?page=ptest',
    ])
    vi.unstubAllGlobals()
  })
})

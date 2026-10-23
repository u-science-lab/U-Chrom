import { describe, expect, it, vi } from 'vitest'
import { agentHistory, approveAgentPlan, applyAgentPlan, planStatusLabel, rejectAgentPlan, sourceLabel, pendingPlanView, type AgentPlan, type AgentSnapshot } from './agent'

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
      'api/agent/ui/plans/p1/approve',
      'api/agent/ui/plans/p1/reject',
      'api/agent/ui/plans/p1/apply',
      'api/agent/history?page=ptest',
    ])
    vi.unstubAllGlobals()
  })
})

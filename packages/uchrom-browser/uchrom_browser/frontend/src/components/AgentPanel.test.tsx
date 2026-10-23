import { describe, expect, it } from 'vitest'
import { agentPanelViewModel } from './AgentPanel'

const snapshot = { page_id: 'page-1', state_revision: 'r-2', source: 'page_canonical' as const }

describe('AgentPanel setup feedback and mutation guard', () => {
  it.each([
    ['not_running', 'Not running', 'Start local WebUI'],
    ['browser_ready', 'Browser ready', 'Open local page'],
    ['page_connected', 'Page connected', 'Pin page'],
    ['page_pinned', 'Page pinned', 'Ready for analysis'],
  ] as const)('renders %s stage and next action', (stage, stageLabel, nextAction) => {
    const view = agentPanelViewModel(stage, null, null)
    expect(view.stageLabel).toBe(stageLabel)
    expect(view.nextAction).toBe(nextAction)
  })

  it('disables Apply when the plan page or revision is stale', () => {
    expect(agentPanelViewModel('page_pinned', snapshot, {
      page_id: 'page-1', expected_revision: 'r-2',
    }).canApply).toBe(true)
    expect(agentPanelViewModel('page_pinned', snapshot, {
      page_id: 'page-2', expected_revision: 'r-2',
    }).canApply).toBe(false)
    expect(agentPanelViewModel('page_pinned', snapshot, {
      page_id: 'page-1', expected_revision: 'r-1',
    }).canApply).toBe(false)
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'

const groupApi = vi.hoisted(() => ({
  fetchGroupCells: vi.fn(),
  registerGroup: vi.fn(),
}))

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return { ...actual, ...groupApi }
})

import { ACTIONS, TOOLS, runAction } from './actions'
import { DEFAULT_VIEW, useStore } from './store'
import type { DatasetSummary } from './types'
import { workspaceOf } from './workspace'

const dataset: DatasetSummary = {
  id: 'd1',
  name: 'sample',
  path: '/sample',
  n_spots: 0,
  n_traces: 0,
  n_cells: 2,
  xyz_unit: null,
  trace_mode: false,
  chroms: [{ name: 'chr15', start: 0, end: 10_000, n_spots: 0, n_traces: 0 }],
}

function seed() {
  useStore.setState({
    datasets: [dataset],
    activeDatasetId: dataset.id,
    cells: { [dataset.id]: [
      { cell_id: 'c1', n_spots: 1, n_traces: 1, n_chroms: 1 },
      { cell_id: 'c2', n_spots: 1, n_traces: 1, n_chroms: 1 },
    ] },
    views: { [dataset.id]: { ...DEFAULT_VIEW } },
    savedGroups: {},
    workspace: workspaceOf(['3d']),
    workspaceOwner: dataset.name,
  })
}

describe('agent action state matches the browser', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    seed()
  })

  it('select_cells stores and returns the canonical cells registered by the server', async () => {
    groupApi.registerGroup.mockResolvedValue({ id: 'gcanonical', name: 'picked', n_cells: 2, n_unknown: 1 })
    groupApi.fetchGroupCells.mockResolvedValue({ group: 'gcanonical', name: 'picked', n_cells: 2, cells: ['c1', 'c2'] })

    const result = await ACTIONS.select_cells({ cells: ['c1', 'unknown', 'c1', 'c2'], name: 'picked' })

    expect(groupApi.registerGroup).toHaveBeenCalledWith('d1', ['c1', 'unknown', 'c1', 'c2'], 'picked')
    expect(groupApi.fetchGroupCells).toHaveBeenCalledWith('d1', 'gcanonical')
    expect(result).toEqual({ group: 'gcanonical', cells: ['c1', 'c2'], n_cells: 2, n_unknown: 1 })
    expect(await ACTIONS.get_selection({})).toMatchObject({ cells: ['c1', 'c2'], group: 'gcanonical' })
    expect(useStore.getState().savedGroups.sample[0].cells).toEqual(['c1', 'c2'])
  })

  it('set_locus returns and stores the range the browser resolves after clipping', async () => {
    const result = await ACTIONS.set_locus({ chrom: 'chr15', start: -500, end: 2_000 })

    expect(result).toEqual({ chrom: 'chr15', start: 0, end: 2_500 })
    expect((await ACTIONS.describe_workspace({}) as { locus: unknown }).locus).toEqual(result)
  })

  it('describes the default locus currently shown when none was stored', async () => {
    expect((await ACTIONS.describe_workspace({}) as { locus: unknown }).locus).toEqual({ chrom: 'chr15', start: 0, end: 10_000 })
  })

  it('lets an agent set and inspect the stats chromosome scope', async () => {
    const tool = TOOLS.find((t) => t.name === 'open_view')!
    const schema = tool.inputSchema as { properties: { chrom_scope: { enum: string[] } } }
    expect(schema.properties.chrom_scope.enum).toEqual(['all', 'locus'])

    await ACTIONS.open_view({ type: 'stats', stats: 'rg', chrom_scope: 'locus' })
    await ACTIONS.open_view({ type: 'stats', stats: 'rg' })
    const description = await ACTIONS.describe_workspace({}) as { views: Array<{ type: string; chrom_scope?: string }> }

    expect(description.views.filter((view) => view.type === 'stats').map((view) => view.chrom_scope)).toEqual(['locus', 'all'])
  })

  it('describes every mutable displayed view and pane setting for canonical revisions', async () => {
    const before = await ACTIONS.describe_workspace({}) as Record<string, any>
    expect(before.view).toMatchObject({ hiddenChroms: [], overviewColor: 'cell' })
    expect(before.workspace.panes[0]).toMatchObject({ type: '3d', embeddingKey: null, dims: [0, 1] })

    useStore.getState().setHiddenChroms(['chr15'])
    useStore.getState().setOverviewColor('field')
    useStore.getState().setWorkspace((ws) => ({
      ...ws,
      panes: ws.panes.map((pane) => ({ ...pane, source: 'distance', scope: { kind: 'all' } })),
    }))

    const after = await ACTIONS.describe_workspace({}) as Record<string, any>
    expect(after.view.hiddenChroms).toEqual(['chr15'])
    expect(after.view.overviewColor).toBe('field')
    expect(after.workspace.panes[0]).toMatchObject({ source: 'distance', scope: { kind: 'all' } })
    expect(after).not.toEqual(before)
  })

  it('blocks direct store mutations while the agent lease is active', () => {
    useStore.getState().setAgentLease(true)
    const before = useStore.getState()
    before.setHiddenChroms(['chr15'])
    before.setOverviewColor('field')
    before.setWorkspace((ws) => ({ ...ws, layout: 'tabs' }))
    const after = useStore.getState()
    expect(after.views.d1.hiddenChroms).toEqual([])
    expect(after.views.d1.overviewColor).toBe('cell')
    expect(after.workspace.layout).toBe(before.workspace.layout)
    useStore.getState().setAgentLease(false)
  })

  it('rejects action and WebMCP entry points while the agent lease is active', async () => {
    useStore.getState().setAgentLease(true)
    await expect(runAction('arrange', { layout: 'tabs' })).rejects.toThrow(/agent lease active/)
    expect(useStore.getState().workspace.layout).toBe('grid')
    useStore.getState().setAgentLease(false)
  })

})

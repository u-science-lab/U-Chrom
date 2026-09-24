import { beforeEach, describe, expect, it } from 'vitest'
import { captureFilename, safePart, timestamp } from './capture'
import { applyRowSetting, migrateRows, parseRows, setRowScope, type GenomeRow } from './genomeRows'
import {
  describeGroup,
  fieldGroupCells,
  fieldGroupRef,
  lassoSelect,
  nextGroupName,
  resolveRowScope,
  resolveScope,
  specLabel,
  parseFieldRef,
  parseSavedGroups,
  pointInPolygon,
  removeGroup,
  renameGroup,
  scopeKey,
  scopeLabel,
  scopeParams,
  simplifyPath,
  upsertGroup,
  type Pt,
  type SavedGroup,
} from './groups'
import { displayParts } from './render/partition'
import { splitPoints } from './render/points'
import { decodeGeometry } from './api'
import { activeSavedGroups, activeView, useStore } from './store'
import { encodeGeometry, sampleHeader } from './testing'
import type { CellField, DatasetSummary, PointSet } from './types'
import { defaultWorkspace, dropGroupScope, dropUnknownGroups, migratePaneScope, parseWorkspace, pinnedCell, pinnedGroup, setPaneScope, updatePane } from './workspace'

const square: Pt[] = [
  [0, 0],
  [10, 0],
  [10, 10],
  [0, 10],
]

describe('lasso', () => {
  it('point in polygon (even-odd), convex and concave', () => {
    expect(pointInPolygon(5, 5, square)).toBe(true)
    expect(pointInPolygon(11, 5, square)).toBe(false)
    expect(pointInPolygon(-1, -1, square)).toBe(false)
    // a "U": the notch is outside
    const u: Pt[] = [
      [0, 0],
      [9, 0],
      [9, 9],
      [6, 9],
      [6, 3],
      [3, 3],
      [3, 9],
      [0, 9],
    ]
    expect(pointInPolygon(1.5, 6, u)).toBe(true)
    expect(pointInPolygon(4.5, 6, u)).toBe(false)
    expect(pointInPolygon(4.5, 1, u)).toBe(true)
  })
  it('selects the ids of points inside; NaN points never', () => {
    const px = new Float32Array([5, 5, 20, 5, NaN, NaN, 1, 9])
    expect(lassoSelect(px, ['a', 'b', 'c', 'd'], square)).toEqual(['a', 'd'])
    expect(lassoSelect(px, ['a', 'b', 'c', 'd'], square.slice(0, 2))).toEqual([]) // not a polygon
  })
  it('simplifies a dense path', () => {
    const pts: Pt[] = [
      [0, 0],
      [0.5, 0],
      [1, 0],
      [3, 0],
      [3, 0.2],
    ]
    expect(simplifyPath(pts, 2)).toEqual([
      [0, 0],
      [3, 0],
    ])
  })
})

describe('group references', () => {
  it('field refs round-trip; values may contain = and +', () => {
    const r = fieldGroupRef('cell_type', 'MLI2+PLI')
    expect(r).toBe('field:cell_type=MLI2+PLI')
    expect(parseFieldRef(r)).toEqual({ field: 'cell_type', value: 'MLI2+PLI' })
    expect(parseFieldRef('field:x=a=b')).toEqual({ field: 'x', value: 'a=b' })
    expect(parseFieldRef('g0123456789ab')).toBeNull()
    expect(parseFieldRef('field:=a')).toBeNull()
  })
  it('field group cells come from the field values', () => {
    const vals = new Map<string, string | number | null>([
      ['c1', 'A'],
      ['c2', 'B'],
      ['c3', 'A'],
      ['c4', null],
    ])
    expect(fieldGroupCells(vals, 'A')).toEqual(['c1', 'c3'])
    expect(fieldGroupCells(undefined, 'A')).toBeNull()
  })
  it('describes field, saved and selection groups', () => {
    const field: CellField = { name: 'cell_type', group: 'cell', label: 'cell_type', kind: 'category', min: null, max: null, n_valid: 3, categories: [{ value: 'A', count: 2 }, { value: 'B', count: 1 }] }
    const saved: SavedGroup[] = [{ id: 'g1', name: 'mine', color: 'rgb(1, 2, 3)', cells: ['c2'] }]
    const vals = new Map([
      ['c1', 'A'],
      ['c2', 'B'],
      ['c3', 'A'],
    ])
    const ctx = { fields: [field], saved, selection: { id: 'g2', cells: ['c1', 'c2'] }, values: () => vals }
    const a = describeGroup('field:cell_type=A', ctx)!
    expect(a.name).toBe('A')
    expect(a.cells).toEqual(['c1', 'c3'])
    expect(a.kind).toBe('field')
    expect(describeGroup('field:cell_type=B', ctx)!.color).not.toBe(a.color)
    expect(describeGroup('g1', ctx)).toMatchObject({ name: 'mine', color: 'rgb(1, 2, 3)', cells: ['c2'], kind: 'saved' })
    expect(describeGroup('g2', ctx)).toMatchObject({ kind: 'selection', cells: ['c1', 'c2'] })
    expect(describeGroup('g9', ctx)).toBeNull()
    expect(describeGroup('field:nope=A', ctx)).toBeNull()
  })
})

describe('saved-group reducers', () => {
  const g = (id: string, name = id): SavedGroup => ({ id, name, color: '#fff', cells: [id] })
  it('upsert / rename / remove', () => {
    let list = upsertGroup([], g('a'))
    list = upsertGroup(list, g('b'))
    list = upsertGroup(list, { ...g('a'), name: 'A2' })
    expect(list.map((x) => x.name)).toEqual(['A2', 'b'])
    expect(renameGroup(list, 'b', '  B  ').map((x) => x.name)).toEqual(['A2', 'B'])
    expect(renameGroup(list, 'b', '   ').map((x) => x.name)).toEqual(['A2', 'b']) // blank ignored
    expect(removeGroup(list, 'a').map((x) => x.id)).toEqual(['b'])
  })
  it('default names skip used ones', () => {
    expect(nextGroupName([])).toBe('selection 1')
    expect(nextGroupName([g('x', 'selection 1'), g('y', 'selection 3')])).toBe('selection 2')
  })
  it('parses persisted groups, dropping junk', () => {
    const raw = { ds: [g('a'), { id: 1 }, { ...g('b'), cells: [1] }], other: 'nope', empty: [] }
    expect(parseSavedGroups(raw)).toEqual({ ds: [g('a')] })
    expect(parseSavedGroups(null)).toEqual({})
    expect(parseSavedGroups([1, 2])).toEqual({})
  })
})

describe('scopes: one explicit cells setting', () => {
  const none = { focusCell: null, focusGroup: null }
  const lasso = { focusCell: null, focusGroup: 'gsel' }
  const cell = { focusCell: 'c1', focusGroup: null }
  it('All cells never changes with focus, selection or lasso', () => {
    for (const f of [none, lasso, cell]) expect(resolveScope({ kind: 'all' }, f)).toEqual({ kind: 'all' })
  })
  it('Follow focus: the focused cell, else the focused group / selection, else all', () => {
    expect(resolveScope({ kind: 'focus' }, none)).toEqual({ kind: 'all' })
    expect(resolveScope({ kind: 'focus' }, lasso)).toEqual({ kind: 'group', group: 'gsel' })
    expect(resolveScope({ kind: 'focus' }, cell)).toEqual({ kind: 'cell', cell: 'c1' })
    expect(resolveScope(undefined, lasso)).toEqual({ kind: 'group', group: 'gsel' }) // absent = follow focus
  })
  it('Cell / Group are fixed', () => {
    expect(resolveScope({ kind: 'cell', cell: 'c9' }, lasso)).toEqual({ kind: 'cell', cell: 'c9' })
    expect(resolveScope({ kind: 'group', group: 'field:t=A' }, cell)).toEqual({ kind: 'group', group: 'field:t=A' })
  })
  it('rows: same as view (default) takes the view; anything else is its own', () => {
    const view = resolveScope({ kind: 'focus' }, lasso)
    expect(resolveRowScope(undefined, view, lasso)).toBe(view)
    expect(resolveRowScope({ kind: 'view' }, view, lasso)).toBe(view)
    // the reported bug: an "all cells" row must stay all after a lasso
    expect(resolveRowScope({ kind: 'all' }, view, lasso)).toEqual({ kind: 'all' })
    expect(resolveRowScope({ kind: 'focus' }, { kind: 'all' }, lasso)).toEqual({ kind: 'group', group: 'gsel' })
  })
  it('labels say what a setting resolves to', () => {
    const sel = { ref: 'gsel', name: 'selection', color: '#fff', cells: Array(10).fill('x'), kind: 'selection' as const }
    expect(specLabel({ kind: 'focus' }, { kind: 'group', group: 'gsel' }, sel, 47)).toBe('Follow focus → selection (10 cells)')
    expect(specLabel({ kind: 'view' }, { kind: 'all' }, null, 47)).toBe('Same as view → All cells (47)')
    expect(specLabel({ kind: 'all' }, { kind: 'all' }, null, 47)).toBe('All cells (47)')
    expect(specLabel({ kind: 'cell', cell: 'c1' }, { kind: 'cell', cell: 'c1' }, null, 47, new Map([['c1', 'Bergmann']]))).toBe('📌 cell c1 · Bergmann')
    expect(scopeLabel({ kind: 'group', group: 'g' }, { ref: 'g', name: 'Bergmann', color: '#fff', cells: ['a', 'b'], kind: 'field' })).toBe('Bergmann (2 cells)')
  })
  it('query params and keys', () => {
    const c = { kind: 'cell', cell: 'c1' } as const
    expect(scopeParams(c)).toEqual({ cellId: 'c1', group: null })
    expect(scopeParams({ kind: 'group', group: 'g' })).toEqual({ cellId: null, group: 'g' })
    expect(scopeParams({ kind: 'all' })).toEqual({ cellId: null, group: null })
    expect(new Set([scopeKey(c), scopeKey({ kind: 'group', group: 'c1' }), scopeKey({ kind: 'all' })]).size).toBe(3)
  })
})

describe('migration of stored layouts', () => {
  it('pane: group → group; cell → cell; matrix with "focused cell" off → all; else follow focus', () => {
    expect(migratePaneScope({ id: 'a', type: '3d', group: 'g1', cell: 'c1' } as never)).toEqual({ kind: 'group', group: 'g1' })
    expect(migratePaneScope({ id: 'a', type: '3d', cell: 'c1' } as never)).toEqual({ kind: 'cell', cell: 'c1' })
    expect(migratePaneScope({ id: 'a', type: 'matrix', followFocus: false } as never)).toEqual({ kind: 'all' })
    expect(migratePaneScope({ id: 'a', type: 'matrix', followFocus: true } as never)).toEqual({ kind: 'focus' })
    expect(migratePaneScope({ id: 'a', type: 'genome' } as never)).toEqual({ kind: 'focus' })
    expect(migratePaneScope({ id: 'a', type: 'genome', scope: { kind: 'all' } } as never)).toEqual({ kind: 'all' })
  })
  it('rows: cell only off → All cells, on → Same as view, a group → that group; aggregate moves onto tracks', () => {
    const raw = [
      { id: 'r1', kind: 'matrix', source: 'distance', followFocus: false },
      { id: 'r2', kind: 'matrix', source: 'distance', followFocus: true },
      { id: 'r3', kind: 'track', track: 'H3K27ac' },
      { id: 'r4', kind: 'track', track: 'H3K27ac', group: 'field:t=A' },
      { id: 'r5', kind: 'intervals', key: 'tads' },
    ]
    const off = migrateRows(parseRows(raw)!, raw, { tracksCellOnly: false, agg: 'max' })
    expect(off.map((r) => r.scope ?? null)).toEqual([{ kind: 'all' }, null, { kind: 'all' }, { kind: 'group', group: 'field:t=A' }, null])
    expect(off[2].agg).toBe('max')
    const on = migrateRows(parseRows(raw)!, raw, { tracksCellOnly: true })
    expect(on[2].scope).toBeUndefined() // same as view
  })
  it('a whole saved workspace migrates through parseWorkspace', () => {
    const old = {
      layout: 'columns',
      panes: [
        { id: 'P1', type: '3d', cell: 'c7', embeddingKey: null, dims: [0, 1] },
        {
          id: 'P2',
          type: 'genome',
          followFocus: false,
          agg: 'median',
          genomeRows: { takei: [{ id: 'r1', kind: 'matrix', source: 'distance', followFocus: false }, { id: 'r2', kind: 'track', track: 'H3K27ac' }] },
          embeddingKey: null,
          dims: [0, 1],
        },
      ],
      activePane: 'P1',
      sizes: [0.5, 0.5],
      maximized: null,
    }
    const ws = parseWorkspace(old)!
    expect(pinnedCell(ws.panes[0])).toBe('c7')
    expect(ws.panes[1].scope).toBeUndefined() // follow focus
    expect(ws.panes[1].genomeRows!.takei.map((r) => r.scope)).toEqual([{ kind: 'all' }, { kind: 'all' }])
    expect(ws.panes[1].genomeRows!.takei[1].agg).toBe('median')
    expect('followFocus' in ws.panes[1]).toBe(false)
    // and round-trips unchanged
    expect(parseWorkspace(JSON.parse(JSON.stringify(ws)))).toEqual(ws)
  })
})

describe('workspace: cells settings', () => {
  it('a pane holds one setting', () => {
    let ws = defaultWorkspace(true)
    ws = setPaneScope(ws, 'P1', { kind: 'group', group: 'field:cell_type=A' })
    expect(pinnedGroup(ws.panes[0])).toBe('field:cell_type=A')
    ws = setPaneScope(ws, 'P1', { kind: 'cell', cell: 'c1' })
    expect([pinnedGroup(ws.panes[0]), pinnedCell(ws.panes[0])]).toEqual([null, 'c1'])
  })
  it('a deleted group is dropped from panes (→ follow focus), overlays and rows (→ same as view)', () => {
    let ws = defaultWorkspace(true)
    const rows: GenomeRow[] = [
      { id: 'r1', kind: 'track', track: 'H3K27ac', scope: { kind: 'group', group: 'g1' } },
      { id: 'r2', kind: 'track', track: 'H3K27ac', scope: { kind: 'group', group: 'g2' } },
    ]
    ws = updatePane(ws, 'P1', { scope: { kind: 'group', group: 'g1' }, compareGroups: ['g1', 'g2'], genomeRows: { ds: rows } })
    const out = dropGroupScope(ws, 'g1')
    expect(out.panes[0].scope).toEqual({ kind: 'focus' })
    expect(out.panes[0].compareGroups).toEqual(['g2'])
    expect(out.panes[0].genomeRows!.ds.map((r) => r.scope)).toEqual([{ kind: 'view' }, { kind: 'group', group: 'g2' }])
    expect(dropGroupScope(out, 'g1')).toBe(out)
  })
  it("another dataset's groups are dropped from panes, not from its rows", () => {
    const rows: GenomeRow[] = [{ id: 'r1', kind: 'track', scope: { kind: 'group', group: 'gOther' } }]
    const ws = updatePane(defaultWorkspace(true), 'P1', { scope: { kind: 'group', group: 'gOther' }, compareGroups: ['field:t=A', 'gOther'], genomeRows: { other: rows } })
    const known = (r: string) => r.startsWith('field:')
    const out = dropUnknownGroups(ws, known)
    expect(out.panes[0]).toMatchObject({ scope: { kind: 'focus' }, compareGroups: ['field:t=A'] })
    expect(out.panes[0].genomeRows!.other[0].scope).toEqual({ kind: 'group', group: 'gOther' })
    expect(dropUnknownGroups(out, known)).toBe(out)
  })
  it('row settings: scope ("view" stored as absent) and aggregate', () => {
    const rows: GenomeRow[] = [{ id: 'r1', kind: 'track' }]
    const all = setRowScope(rows, 'r1', { kind: 'all' })
    expect(all[0].scope).toEqual({ kind: 'all' })
    expect('scope' in setRowScope(all, 'r1', { kind: 'view' })[0]).toBe(false)
    expect(applyRowSetting(rows, 'r1', 'agg', 'median')[0].agg).toBe('median')
    expect(applyRowSetting(rows, 'r1', 'agg', 'mode')).toBe(rows)
    expect(parseRows([{ id: 'r', kind: 'track', scope: { kind: 'group', group: 5 } }])![0].scope).toBeUndefined()
  })
})

describe('group focus in the 3-D display split', () => {
  it('a set of cells is main, the others context', () => {
    const g = decodeGeometry(encodeGeometry(sampleHeader(), [0, 0, 0, 1, 0, 0, 3, 0, 0, 0, 1, 0, 0, 4, 0], [0, 100, 200, 100, 200], [0, 3, 5]))
    const parts = displayParts(g, new Set(), new Set(['c1']))
    expect(parts.main!.header.segments.map((s) => s.cell_id)).toEqual(['c1'])
    expect(parts.context!.header.segments.map((s) => s.cell_id)).toEqual([null])
    expect(displayParts(g, new Set(), new Set()).main).toBeNull() // group still loading: all context
  })
  it('points follow the same split', () => {
    const ps: PointSet = { name: 'rna', n: 3, positions: new Float32Array(9), cellIds: ['a', 'b', null], labels: ['x', 'x', 'x'], values: {} }
    const s = splitPoints(ps, new Set(), new Set(['a', 'b']))
    expect([...s.main]).toEqual([0, 1])
    expect([...s.context]).toEqual([2])
  })
})

describe('store: focus and saved groups', () => {
  const ds = { id: 'd1', name: 'demo', path: '', n_spots: 0, n_traces: 0, n_cells: 3, xyz_unit: null, trace_mode: false, chroms: [] } as DatasetSummary
  beforeEach(() => {
    useStore.setState({ datasets: [ds], activeDatasetId: 'd1', views: {}, savedGroups: {}, layers: [], cells: {}, cellValues: {} })
  })
  it('a cell and a group focus exclude each other; All cells clears both', () => {
    const s = useStore.getState()
    s.focusGroup('field:cell_type=A')
    expect(activeView(useStore.getState())).toMatchObject({ focusGroup: 'field:cell_type=A', focusCell: null })
    s.focusCell('c1')
    expect(activeView(useStore.getState())).toMatchObject({ focusGroup: null, focusCell: 'c1' })
    s.focusGroup('g1')
    s.focusCell(null)
    expect(activeView(useStore.getState())).toMatchObject({ focusGroup: null, focusCell: null })
  })
  it('a lasso selection is focused, then saved under its id with a default name and colour', () => {
    const s = useStore.getState()
    s.setSelection({ id: 'gabc', cells: ['c1', 'c2'] })
    expect(activeView(useStore.getState()).focusGroup).toBe('gabc')
    s.saveSelection('')
    const saved = activeSavedGroups(useStore.getState())
    expect(saved).toHaveLength(1)
    expect(saved[0]).toMatchObject({ id: 'gabc', name: 'selection 1', cells: ['c1', 'c2'] })
    expect(activeView(useStore.getState())).toMatchObject({ selection: null, focusGroup: 'gabc' })
    s.renameSavedGroup('gabc', 'Purkinje-like')
    expect(activeSavedGroups(useStore.getState())[0].name).toBe('Purkinje-like')
    s.deleteSavedGroup('gabc')
    expect(activeSavedGroups(useStore.getState())).toEqual([])
    expect(activeView(useStore.getState()).focusGroup).toBeNull()
  })
  it('discarding the selection releases its focus', () => {
    const s = useStore.getState()
    s.setSelection({ id: 'gx', cells: ['c1'] })
    s.setSelection(null)
    expect(activeView(useStore.getState())).toMatchObject({ selection: null, focusGroup: null })
  })
})

describe('PNG filename', () => {
  const date = new Date(2026, 8, 24, 15, 30, 7)
  it('timestamp is local yyyymmdd-hhmmss', () => {
    expect(timestamp(date)).toBe('20260924-153007')
  })
  it('names dataset, view, scope or locus', () => {
    expect(captureFilename({ dataset: 'takei2025_fov0', type: '3d', scope: null, date })).toBe('uchrom_takei2025_fov0_3d_all_20260924-153007.png')
    expect(captureFilename({ dataset: 'takei2025_fov0', type: 'embedding', scope: 'cell-1_0_34', date })).toBe('uchrom_takei2025_fov0_embedding_cell-1_0_34_20260924-153007.png')
    expect(captureFilename({ dataset: 'sim cell/1', type: 'genome', locus: { chrom: 'chr1', start: 3_000_000, end: 195_375_000 }, date })).toBe(
      'uchrom_sim-cell-1_genome_chr1-3M-195.375M_20260924-153007.png',
    )
    expect(captureFilename({ dataset: 'd', type: 'matrix', scope: 'MLI2+PLI', locus: { chrom: 'chr2', start: 0, end: 1_000_000 }, date })).toBe(
      'uchrom_d_matrix_chr2-0-1M_MLI2+PLI_20260924-153007.png',
    )
  })
  it('unsafe characters are replaced', () => {
    expect(safePart(' a/b\\c:d ')).toBe('a-b-c-d')
    expect(safePart('///')).toBe('x')
  })
})

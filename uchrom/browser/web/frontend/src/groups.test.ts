import { beforeEach, describe, expect, it } from 'vitest'
import { captureFilename, safePart, timestamp } from './capture'
import { applyRowSetting, parseRows, type GenomeRow } from './genomeRows'
import {
  describeGroup,
  fieldGroupCells,
  fieldGroupRef,
  lassoSelect,
  nextGroupName,
  paneScope,
  parseFieldRef,
  parseSavedGroups,
  pointInPolygon,
  removeGroup,
  renameGroup,
  rowScope,
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
import { defaultWorkspace, dropGroupScope, dropUnknownGroups, parseWorkspace, pinPane, setPaneGroup, updatePane } from './workspace'

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

describe('scopes', () => {
  it('pane group > pinned cell > focused cell > focused group > all', () => {
    const none = { focusCell: null, focusGroup: null }
    expect(paneScope({}, none)).toEqual({ kind: 'all' })
    expect(paneScope({}, { focusCell: null, focusGroup: 'g1' })).toEqual({ kind: 'group', group: 'g1' })
    expect(paneScope({}, { focusCell: 'c1', focusGroup: 'g1' })).toEqual({ kind: 'cell', cell: 'c1' })
    expect(paneScope({ cell: 'c2' }, { focusCell: 'c1', focusGroup: null })).toEqual({ kind: 'cell', cell: 'c2' })
    expect(paneScope({ cell: 'c2', group: 'g3' }, { focusCell: 'c1', focusGroup: 'g1' })).toEqual({ kind: 'group', group: 'g3' })
  })
  it('a row group overrides the pane scope; params and keys', () => {
    const pane = { kind: 'cell', cell: 'c1' } as const
    expect(rowScope({}, pane)).toBe(pane)
    expect(rowScope({ group: 'g' }, pane)).toEqual({ kind: 'group', group: 'g' })
    expect(scopeParams(pane)).toEqual({ cellId: 'c1', group: null })
    expect(scopeParams({ kind: 'group', group: 'g' })).toEqual({ cellId: null, group: 'g' })
    expect(scopeParams({ kind: 'all' })).toEqual({ cellId: null, group: null })
    expect(new Set([scopeKey(pane), scopeKey({ kind: 'group', group: 'c1' }), scopeKey({ kind: 'all' })]).size).toBe(3)
    expect(scopeLabel({ kind: 'group', group: 'g' }, { ref: 'g', name: 'Bergmann', color: '#fff', cells: ['a', 'b'], kind: 'field' })).toBe('Bergmann (2 cells)')
  })
})

describe('workspace: group scopes', () => {
  it('pinning a cell clears a group and vice versa', () => {
    let ws = defaultWorkspace(true)
    ws = setPaneGroup(ws, 'P1', 'field:cell_type=A')
    expect(ws.panes[0]).toMatchObject({ group: 'field:cell_type=A', cell: null })
    ws = pinPane(ws, 'P1', 'c1')
    expect(ws.panes[0]).toMatchObject({ group: null, cell: 'c1' })
  })
  it('a deleted group is dropped from panes, overlays and rows', () => {
    let ws = defaultWorkspace(true)
    const rows: GenomeRow[] = [
      { id: 'r1', kind: 'track', track: 'H3K27ac', group: 'g1' },
      { id: 'r2', kind: 'track', track: 'H3K27ac', group: 'g2' },
    ]
    ws = updatePane(ws, 'P1', { group: 'g1', compareGroups: ['g1', 'g2'], genomeRows: { ds: rows } })
    const out = dropGroupScope(ws, 'g1')
    expect(out.panes[0].group).toBeNull()
    expect(out.panes[0].compareGroups).toEqual(['g2'])
    expect(out.panes[0].genomeRows!.ds.map((r) => r.group)).toEqual([null, 'g2'])
    expect(dropGroupScope(out, 'g1')).toBe(out) // nothing left: same object
  })
  it("another dataset's groups are dropped from panes, not from its rows", () => {
    const rows: GenomeRow[] = [{ id: 'r1', kind: 'track', group: 'gOther' }]
    const ws = updatePane(defaultWorkspace(true), 'P1', { group: 'gOther', compareGroups: ['field:t=A', 'gOther'], genomeRows: { other: rows } })
    const known = (r: string) => r.startsWith('field:')
    const out = dropUnknownGroups(ws, known)
    expect(out.panes[0]).toMatchObject({ group: null, compareGroups: ['field:t=A'] })
    expect(out.panes[0].genomeRows!.other[0].group).toBe('gOther')
    expect(dropUnknownGroups(out, known)).toBe(out)
  })
  it('persisted group scopes survive parsing', () => {
    const ws = updatePane(defaultWorkspace(true), 'P2', { group: 'field:t=A', compareGroups: ['g1'], genomeRows: { ds: [{ id: 'r1', kind: 'track', group: 'g1' }] } })
    const back = parseWorkspace(JSON.parse(JSON.stringify(ws)))!
    expect(back.panes[1]).toMatchObject({ group: 'field:t=A', compareGroups: ['g1'] })
    expect(back.panes[1].genomeRows!.ds[0].group).toBe('g1')
    expect(parseRows([{ id: 'r', kind: 'track', group: 5 }])![0].group).toBeUndefined()
  })
  it('row group setting: a ref, or empty for the pane scope', () => {
    const rows: GenomeRow[] = [{ id: 'r1', kind: 'track' }]
    expect(applyRowSetting(rows, 'r1', 'group', 'field:t=A')[0].group).toBe('field:t=A')
    expect(applyRowSetting(rows, 'r1', 'group', '')[0].group).toBeNull()
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

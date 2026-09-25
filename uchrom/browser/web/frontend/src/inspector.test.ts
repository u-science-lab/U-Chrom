import { describe, expect, it } from 'vitest'
import { addRow, applyRowSetting, rowPatch, MAX_ROW_H, type GenomeRow } from './genomeRows'
import { ensureActivePane, inspectorSections, leftSections, paneTitle, sidebarSections, type DatasetFacts } from './inspector'
import { addPane, defaultWorkspace, PANE_TYPES, type WorkspaceState } from './workspace'

const imaging: DatasetFacts = { hasCoords: true, nCells: 47, nChroms: 20, nPointSets: 0 }
const withRna: DatasetFacts = { ...imaging, nPointSets: 1 }
const scHiC: DatasetFacts = { hasCoords: false, nCells: 5313, nChroms: 0, nPointSets: 0 }
const sim: DatasetFacts = { hasCoords: true, nCells: 1, nChroms: 20, nPointSets: 0 }

describe('inspector sections per pane type', () => {
  it('3-D: layers, subsets, style, chromosomes (+ points when there are point sets)', () => {
    expect(inspectorSections({ type: '3d' }, imaging)).toEqual(['pin', 'layers', 'subset', 'style', 'chroms'])
    expect(inspectorSections({ type: '3d' }, withRna)).toEqual(['pin', 'layers', 'subset', 'style', 'chroms', 'points'])
    // one cell: nothing to pin
    expect(inspectorSections({ type: '3d' }, sim)).toEqual(['layers', 'subset', 'style', 'chroms'])
    // no coordinates: just say so
    expect(inspectorSections({ type: '3d' }, scHiC)).toEqual(['pin', 'noCoords'])
  })
  it('other views: their own inputs', () => {
    expect(inspectorSections({ type: 'genome' }, scHiC)).toEqual(['pin', 'genomeRows'])
    expect(inspectorSections({ type: 'matrix' }, sim)).toEqual(['matrix'])
    expect(inspectorSections({ type: 'embedding' }, imaging)).toEqual(['pin', 'embedding'])
    expect(inspectorSections({ type: 'stats' }, imaging)).toEqual(['pin', 'stats'])
    expect(inspectorSections(undefined, imaging)).toEqual([])
    expect(inspectorSections({ type: '3d' }, null)).toEqual([])
  })
})

describe('left side bar', () => {
  it('is the same whichever pane is active', () => {
    let ws: WorkspaceState = defaultWorkspace({ hasCoords: true, hasEmbeddings: true, hasTracks: false })
    for (const t of PANE_TYPES) ws = addPane(ws, t)
    const lefts = ws.panes.map((p) => sidebarSections({ ...ws, activePane: p.id }, imaging).left)
    for (const l of lefts) expect(l).toEqual(['cells', 'groups', 'cellInfo', 'colour'])
    // …while the right one follows the active pane
    const rights = new Set(ws.panes.map((p) => sidebarSections({ ...ws, activePane: p.id }, imaging).right.join(',')))
    expect(rights.size).toBe(PANE_TYPES.length)
  })
  it('shows the cell list and the colouring only for multi-cell data', () => {
    expect(leftSections(sim)).toEqual(['cellInfo'])
    expect(leftSections(scHiC)).toEqual(['cells', 'groups', 'cellInfo', 'colour'])
    expect(leftSections(null)).toEqual([])
  })
})

describe('active pane', () => {
  it('falls back to the first pane and titles panes by type and position', () => {
    const ws = addPane(defaultWorkspace(false), 'genome')
    expect(ensureActivePane(ws)).toBe(ws)
    expect(ensureActivePane({ ...ws, activePane: 'gone' }).activePane).toBe('P1')
    expect(paneTitle(ws, ws.panes[2])).toBe('Genome · pane 3')
    expect(paneTitle(ws, ws.panes[0])).toBe('3D · pane 1')
  })
})

describe('genome row settings edited in the inspector', () => {
  const rows: GenomeRow[] = addRow(addRow([], { kind: 'matrix', source: 'all_cells', resolution: 500000 }), { kind: 'track', track: 'H3K27ac' })
  it('update the row they belong to', () => {
    expect(applyRowSetting(rows, 'r1', 'source', 'type_L5IT')[0]).toMatchObject({ source: 'type_L5IT', resolution: null })
    expect(applyRowSetting(rows, 'r1', 'resolution', '1000000')[0].resolution).toBe(1e6)
    expect(applyRowSetting(rows, 'r1', 'resolution', '')[0].resolution).toBeNull()
    expect(applyRowSetting(rows, 'r1', 'balance', true)[0].balance).toBe(true)
    expect(applyRowSetting(rows, 'r1', 'flip', true)[0].flip).toBe(true)
    expect(applyRowSetting(rows, 'r1', 'stat', 'mean')[0].stat).toBe('mean')
    expect(applyRowSetting(rows, 'r1', 'maxDist', '5M')[0].maxDist).toBe(5e6)
    expect(applyRowSetting(rows, 'r1', 'maxDist', '')[0].maxDist).toBeNull()
    expect(applyRowSetting(rows, 'r1', 'threshold', '0.3')[0].threshold).toBe(0.3)
    expect(applyRowSetting(rows, 'r2', 'track', 'H3K9me3')[1].track).toBe('H3K9me3')
    expect(applyRowSetting(rows, 'r2', 'height', '5000')[1].height).toBe(MAX_ROW_H)
    expect(applyRowSetting(rows, 'r2', 'height', '')[1].height).toBeNull()
    // the other row is untouched
    expect(applyRowSetting(rows, 'r2', 'height', '60')[0]).toBe(rows[0])
  })
  it('refuses invalid input (rows unchanged)', () => {
    for (const [k, v] of [
      ['maxDist', 'far'],
      ['height', '-3'],
      ['stat', 'mode'],
      ['resolution', 'x'],
      ['source', ''],
      ['track', true],
    ] as const)
      expect(applyRowSetting(rows, 'r1', k, v)).toBe(rows)
    expect(rowPatch('balance', 'yes')).toBeNull()
  })
})

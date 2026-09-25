import { describe, expect, it } from 'vitest'
import {
  addRow,
  defaultRows,
  depthScale,
  moveRow,
  parseRows,
  rasterTriangle,
  removeRow,
  resizeRow,
  resolveHeights,
  MIN_AUTO_MATRIX_H,
  MAX_ROW_H,
  MIN_ROW_H,
  triangleBins,
  trianglePos,
  updateRow,
  type GenomeRow,
  type TriangleGeom,
} from './genomeRows'
import type { ContactMapInfo, DatasetSummary } from './types'
import { defaultWorkspace, parseWorkspace } from './workspace'

// 10 regular 10-bp bins over [0, 100); 10 px wide → 10 bp per px
const starts = Array.from({ length: 10 }, (_, i) => i * 10)
const ends = starts.map((s) => s + 10)
const geom = (p: Partial<TriangleGeom> = {}): TriangleGeom => ({ start: 0, bpPerPx: 10, height: 5, k: 1, flip: false, maxDist: null, ...p })

describe('rotated triangle: inverse mapping', () => {
  it('maps screen x to the genomic midpoint and depth to half the separation (i = x − y, j = x + y)', () => {
    // diagonal at the bottom: the bottom pixel row is next to the diagonal
    expect(trianglePos(4.5, 4.5, geom())).toEqual([40, 50])
    expect(triangleBins(4.5, 4.5, geom(), starts, ends)).toEqual([4, 5])
    // top row of the column: the far corner of the triangle
    expect(triangleBins(4.5, 0.5, geom(), starts, ends)).toEqual([0, 9])
    expect(triangleBins(6.5, 2.5, geom(), starts, ends)).toEqual([4, 9])
  })
  it('flip puts the diagonal at the top', () => {
    expect(triangleBins(4.5, 0.5, geom({ flip: true }), starts, ends)).toEqual([4, 5])
    expect(triangleBins(4.5, 4.5, geom({ flip: true }), starts, ends)).toEqual([0, 9])
  })
  it('is null outside the triangle, the row, or a bin', () => {
    expect(triangleBins(0.5, 0.5, geom(), starts, ends)).toBeNull() // left of the triangle
    expect(triangleBins(9.5, 1.5, geom(), starts, ends)).toBeNull() // right of it
    expect(trianglePos(5, -1, geom())).toBeNull()
    expect(trianglePos(5, 6, geom())).toBeNull()
    // a gap between bins
    expect(triangleBins(2.5, 4.5, geom(), [0, 30], [20, 40])).toBeNull()
  })
  it('clips at the maximum distance and stretches depth to fit it', () => {
    expect(trianglePos(5, 0, geom({ maxDist: 60 }))).toBeNull() // separation 100 > 60
    expect(trianglePos(5, 2, geom({ maxDist: 60 }))).toEqual([20, 80])
    // k so that 40 bp spans the 5-px height: separation 2·t·k·bpPerPx = 40 at t = 5
    const k = depthScale(40, 10, 5)
    expect(k).toBeCloseTo(0.4)
    const p = trianglePos(5, 0, geom({ maxDist: 40, k }))!
    expect(p[1] - p[0]).toBeCloseTo(40)
    expect(depthScale(null, 10, 5)).toBe(1)
  })
})

describe('rotated triangle: raster', () => {
  // colour of cell (i, j) encodes the pair: r = 10·i, g = 10·j
  const n = 10
  const colors = new Uint8ClampedArray(4 * n * n)
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) colors.set([10 * i, 10 * j, 0, 255], 4 * (i * n + j))

  for (const g of [geom(), geom({ flip: true }), geom({ maxDist: 50 }), geom({ k: depthScale(40, 10, 5), maxDist: 40 })]) {
    it(`agrees with the inverse mapping at every pixel centre (flip ${g.flip}, maxDist ${g.maxDist})`, () => {
      const px = rasterTriangle(10, 5, g, starts, ends, colors)
      for (let y = 0; y < 5; y++)
        for (let x = 0; x < 10; x++) {
          const b = triangleBins(x + 0.5, y + 0.5, g, starts, ends)
          const o = 4 * (y * 10 + x)
          if (!b) expect(px[o + 3]).toBe(0)
          else expect([px[o], px[o + 1], px[o + 3]]).toEqual([10 * b[0], 10 * b[1], 255])
        }
    })
  }
  it('leaves nothing drawn deeper than maxDist', () => {
    const px = rasterTriangle(10, 5, geom({ maxDist: 20 }), starts, ends, colors)
    // separation at pixel row y is 2·(5 − y − 0.5)·10: rows 0..3 exceed 20 bp
    for (let y = 0; y < 4; y++) for (let x = 0; x < 10; x++) expect(px[4 * (y * 10 + x) + 3]).toBe(0)
    expect(px.some((v, i) => i % 4 === 3 && v === 255)).toBe(true)
  })
})

describe('row reducers', () => {
  const base: GenomeRow[] = addRow(addRow(addRow([], { kind: 'matrix', source: 'distance' }), { kind: 'track', track: 'H3K27ac' }), { kind: 'intervals', key: 'tads' })
  it('adds rows with unique ids', () => {
    expect(base.map((r) => r.id)).toEqual(['r1', 'r2', 'r3'])
    const more = addRow(removeRow(base, 'r2'), { kind: 'track', track: 'x' })
    expect(new Set(more.map((r) => r.id)).size).toBe(3)
  })
  it('removes, moves (clamped) and updates', () => {
    expect(removeRow(base, 'r2').map((r) => r.id)).toEqual(['r1', 'r3'])
    expect(moveRow(base, 'r3', -1).map((r) => r.id)).toEqual(['r1', 'r3', 'r2'])
    expect(moveRow(base, 'r1', -1)).toBe(base)
    expect(moveRow(base, 'r1', 5).map((r) => r.id)).toEqual(['r2', 'r3', 'r1'])
    expect(updateRow(base, 'r1', { stat: 'mean' })[0].stat).toBe('mean')
    expect(resizeRow(base, 'r1', 5)[0].height).toBe(MIN_ROW_H)
    expect(resizeRow(base, 'r1', 1e6)[0].height).toBe(MAX_ROW_H)
  })
  it('matrix rows without a height share the free height', () => {
    // track 44 + intervals 22 fixed; the matrix gets the rest
    // (3 px of row separators)
    expect(resolveHeights(base, 469)).toEqual([400, 44, 22])
    const two = addRow(base, { kind: 'matrix', source: 'x' })
    expect(resolveHeights(two, 470)).toEqual([200, 44, 22, 200])
    expect(resolveHeights(two, 100)).toEqual([MIN_AUTO_MATRIX_H, 44, 22, MIN_AUTO_MATRIX_H])
    expect(resolveHeights(updateRow(two, 'r1', { height: 300 }), 470)).toEqual([300, 44, 22, MIN_AUTO_MATRIX_H])
    // capped at the full triangle of the axis width
    expect(resolveHeights(base, 469, 500)).toEqual([250, 44, 22])
  })
  it('parses persisted rows, rejecting malformed ones', () => {
    expect(parseRows(JSON.parse(JSON.stringify(base)))).toEqual(base)
    expect(parseRows([{ id: 'a', kind: 'pie' }])).toBeNull()
    expect(parseRows([{ id: 'a', kind: 'track' }, { id: 'a', kind: 'track' }])).toBeNull()
    expect(parseRows([{ id: 'a', kind: 'matrix', height: -3, maxDist: 'x', stat: 'mean' }])).toEqual([{ id: 'a', kind: 'matrix', stat: 'mean' }])
  })
})

describe('default rows per dataset', () => {
  const cmap = (key: string, per_cell = false): ContactMapInfo => ({ key, kind: per_cell ? 'scool' : 'mcool', label: key, resolutions: [], chroms: [], per_cell, n_cells: 0 })
  const ds = (p: Partial<DatasetSummary>) => ({ has_coords: true, n_spots: 10, contact_maps: [], tracks: [], intervals: [], ...p }) as DatasetSummary
  const sig = (rows: GenomeRow[]) => rows.map((r) => `${r.kind}:${r.source ?? r.track ?? r.key}`)
  it('simulation: Hi-C over 3-D distance', () => {
    expect(sig(defaultRows(ds({ contact_maps: [cmap('cell1_contacts')] })))).toEqual(['matrix:cell1_contacts', 'matrix:distance'])
  })
  it('imaging with marks: distance triangle over six marks', () => {
    const tracks = ['H3K9me3', 'foo', 'H3K27ac', 'H3K4me3', 'H3K27me3', 'LaminB1', 'H3K36me3', 'H3K4me1'].map((name) => ({ name }))
    expect(sig(defaultRows(ds({ tracks })))).toEqual([
      'matrix:distance',
      'track:H3K27ac',
      'track:H3K4me3',
      'track:H3K27me3',
      'track:H3K9me3',
      'track:LaminB1',
      'track:H3K36me3',
    ])
    // an old Tracks pane's selection wins
    expect(sig(defaultRows(ds({ tracks }), ['foo']))).toEqual(['matrix:distance', 'track:foo'])
  })
  it('scHi-C without coordinates: merged map over the per-cell map, no tracks', () => {
    const maps = [cmap('all_cells'), cmap('type_L5IT'), cmap('per_cell', true)]
    expect(sig(defaultRows(ds({ has_coords: false, n_spots: 0, contact_maps: maps })))).toEqual(['matrix:all_cells', 'matrix:per_cell'])
  })
  it('coordinates only: the distance triangle; interval tables become rows', () => {
    expect(sig(defaultRows(ds({})))).toEqual(['matrix:distance'])
    expect(sig(defaultRows(ds({ intervals: [{ key: 'tads', n: 3 }] })))).toEqual(['matrix:distance', 'intervals:tads'])
  })
})

describe('migration of old Tracks panes', () => {
  it("opens a saved 'tracks' pane as a genome pane, keeping its track selection", () => {
    const ws = parseWorkspace({ layout: 'columns', panes: [{ id: 'P1', type: '3d' }, { id: 'P2', type: 'tracks', tracks: ['H3K9me3'], agg: 'max' }], sizes: [0.5, 0.5] })!
    expect(ws.panes[1]).toMatchObject({ id: 'P2', type: 'genome', tracks: ['H3K9me3'], agg: 'max' })
  })
  it('round-trips genome rows per dataset and drops malformed ones', () => {
    const rows = addRow([], { kind: 'matrix', source: 'distance', maxDist: 5e6 })
    const ws = parseWorkspace({
      layout: 'tabs',
      panes: [{ id: 'P1', type: 'genome', genomeRows: { sim: rows, bad: [{ id: 1 }] } }],
    })!
    expect(ws.panes[0].genomeRows).toEqual({ sim: rows })
  })
  it('defaults to a genome pane next to 3D for data with contact maps or tracks', () => {
    expect(defaultWorkspace({ hasCoords: true, hasEmbeddings: false, hasTracks: false, hasContactMaps: true }).panes.map((p) => p.type)).toEqual(['3d', 'genome'])
  })
})

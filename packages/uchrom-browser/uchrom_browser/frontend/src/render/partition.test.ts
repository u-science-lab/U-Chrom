import { describe, expect, it } from 'vitest'
import { decodeGeometry } from '../api'
import { encodeGeometry, sampleHeader } from '../testing'
import { cellsOf, displayParts, subsetGeometry, thinGeometry } from './partition'
import type { Geometry, SegmentInfo } from '../types'

// three segments: t1 (c1, chr1, 3 pts) | t2 (null cell, chr1, 2 pts) | t3 (c2, chr2, 2 pts)
function geom() {
  const header = {
    ...sampleHeader(),
    total_points: 7,
    segments: [
      { trace_id: 't1', chrom: 'chr1', cell_id: 'c1', n_points: 3, start: 0, end: 300 },
      { trace_id: 't2', chrom: 'chr1', cell_id: null, n_points: 2, start: 100, end: 300 },
      { trace_id: 't3', chrom: 'chr2', cell_id: 'c2', n_points: 2, start: 0, end: 200 },
    ],
  }
  const pos = [0, 0, 0, 1, 0, 0, 2, 0, 0, 5, 5, 5, 6, 5, 5, 10, 10, 10, 11, 12, 13]
  return decodeGeometry(encodeGeometry(header, pos, [0, 100, 200, 100, 200, 0, 100], [0, 3, 5, 7]))
}

describe('subsetGeometry', () => {
  it('copies kept segments with rebased offsets and a fresh bbox', () => {
    const s = subsetGeometry(geom(), (seg) => seg.trace_id !== 't2')
    expect(Array.from(s.offsets)).toEqual([0, 3, 5])
    expect(Array.from(s.starts)).toEqual([0, 100, 200, 0, 100])
    expect(Array.from(s.positions.slice(9))).toEqual([10, 10, 10, 11, 12, 13])
    expect(s.header).toMatchObject({ n_points: 5, n_segments: 2 })
    expect(s.header.segments.map((x) => x.trace_id)).toEqual(['t1', 't3'])
    expect(s.header.bbox).toEqual({ min: [0, 0, 0], max: [11, 12, 13] })
  })
  it('returns the same object when everything is kept', () => {
    const g = geom()
    expect(subsetGeometry(g, () => true)).toBe(g)
  })
})

describe('displayParts', () => {
  it('hides chromosomes without a focus', () => {
    const p = displayParts(geom(), new Set(['chr2']), null)
    expect(p.main!.header.segments.map((x) => x.trace_id)).toEqual(['t1', 't2'])
    expect(p.context).toBeNull()
  })
  it('splits the focused cell from its context', () => {
    const p = displayParts(geom(), new Set(), 'c2')
    expect(p.main!.header.segments.map((x) => x.trace_id)).toEqual(['t3'])
    expect(p.context!.header.segments.map((x) => x.trace_id)).toEqual(['t1', 't2'])
    expect(p.main!.header.bbox).toEqual({ min: [10, 10, 10], max: [11, 12, 13] })
  })
  it('returns null parts when nothing is left', () => {
    const p = displayParts(geom(), new Set(['chr1', 'chr2']), 'c1')
    expect(p).toEqual({ main: null, context: null })
  })
  it('lists cells in segment order', () => {
    expect(cellsOf(geom())).toEqual(['c1', 'c2'])
  })
})

describe('thinned geometry (camera moving)', () => {
  const seg = (cell: string | null, chrom = 'chr1') => ({ trace_id: 't', cell_id: cell, chrom, n: 2 }) as unknown as SegmentInfo
  const geom = (segs: SegmentInfo[]): Geometry => {
    const n = segs.length * 2
    const offsets = Uint32Array.from({ length: segs.length + 1 }, (_, i) => 2 * i)
    return {
      header: { n_points: n, n_segments: segs.length, total_points: n, truncated: false, segments: segs, bbox: null, chrom_extent: {} },
      positions: Float32Array.from({ length: 3 * n }, (_, i) => i),
      starts: new Uint32Array(n),
      offsets,
    }
  }
  it('keeps every k-th cell whole and maps segments back', () => {
    const g = geom([seg('a'), seg('a', 'chr2'), seg('b'), seg('c'), seg('c'), seg('d')])
    expect(thinGeometry(g, 100)).toBeNull()
    const t = thinGeometry(g, 6)! // 12 points → k = 2: cells a and c
    expect(t.geometry.header.segments.map((s) => s.cell_id)).toEqual(['a', 'a', 'c', 'c'])
    expect([...t.origSeg]).toEqual([0, 1, 3, 4])
    // the kept points are the originals
    expect(t.geometry.positions[6]).toBe(g.positions[6])
  })
  it('thins traces of data without cells', () => {
    const t = thinGeometry(geom([seg(null), seg(null), seg(null), seg(null)]), 3)! // 8 points → k = 3
    expect([...t.origSeg]).toEqual([0, 3])
  })
})

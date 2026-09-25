import { describe, expect, it } from 'vitest'
import { decodeGeometry } from '../api'
import { encodeGeometry, sampleHeader } from '../testing'
import { medianBond, resolveMaxBond, splitForView, splitLongBonds } from './bonds'

// t1: x = 0, 1, 2, 12, 13 (one 10-unit jump) | t2: x = 20, 21
function geom() {
  const header = {
    ...sampleHeader(),
    total_points: 7,
    segments: [
      { trace_id: 't1', chrom: 'chr1', cell_id: 'c1', n_points: 5, start: 0, end: 500 },
      { trace_id: 't2', chrom: 'chr1', cell_id: 'c1', n_points: 2, start: 0, end: 200 },
    ],
  }
  const xs = [0, 1, 2, 12, 13, 20, 21]
  const pos = xs.flatMap((x) => [x, 0, 0])
  return decodeGeometry(encodeGeometry(header, pos, [0, 100, 200, 300, 400, 0, 100], [0, 5, 7]))
}

describe('medianBond', () => {
  it('is the median of consecutive in-segment distances', () => {
    // bonds: 1, 1, 10, 1 | 1  → median 1
    expect(medianBond(geom())).toBe(1)
  })
  it('is null without bonds', () => {
    expect(medianBond({ positions: new Float32Array(6), offsets: Uint32Array.from([0, 1, 2]) })).toBeNull()
  })
})

describe('splitLongBonds', () => {
  it('cuts long bonds into new segments, keeping points in place', () => {
    const g = geom()
    const { geometry: s, broken } = splitLongBonds(g, 5)
    expect(broken).toBe(1)
    expect(Array.from(s.offsets)).toEqual([0, 3, 5, 7])
    expect(s.positions).toBe(g.positions) // same point order → picking indices unchanged
    expect(s.starts).toBe(g.starts)
    expect(s.header.n_segments).toBe(3)
    expect(s.header.segments.map((x) => [x.trace_id, x.n_points, x.start])).toEqual([
      ['t1', 3, 0],
      ['t1', 2, 300],
      ['t2', 2, 0],
    ])
    expect(s.header.segments[2]).toBe(g.header.segments[1]) // untouched segment kept as is
  })
  it('is a no-op for large or disabled thresholds', () => {
    const g = geom()
    expect(splitLongBonds(g, 100).geometry).toBe(g)
    expect(splitLongBonds(g, null)).toEqual({ geometry: g, broken: 0 })
  })
  it('isolates a spot between two long jumps', () => {
    const header = { ...sampleHeader(), total_points: 3, segments: [{ trace_id: 't', chrom: 'chr1', cell_id: null, n_points: 3, start: 0, end: 300 }] }
    const g = decodeGeometry(encodeGeometry(header, [0, 0, 0, 50, 0, 0, 0.5, 0, 0], [0, 100, 200], [0, 3]))
    const { geometry: s, broken } = splitLongBonds(g, 5)
    expect(broken).toBe(2)
    expect(Array.from(s.offsets)).toEqual([0, 1, 2, 3])
  })
})

describe('auto threshold', () => {
  it('is 10 × the median bond and cached per geometry', () => {
    const g = geom()
    expect(resolveMaxBond(g, 'auto')).toBe(10)
    expect(resolveMaxBond(g, 3)).toBe(3)
    expect(resolveMaxBond(g, null)).toBeNull()
    const a = splitForView(g, 'auto')
    expect(a.threshold).toBe(10)
    expect(a.broken).toBe(0) // the 10-unit jump is not > 10
    expect(splitForView(g, 5).geometry).toBe(splitForView(g, 5).geometry)
  })
})

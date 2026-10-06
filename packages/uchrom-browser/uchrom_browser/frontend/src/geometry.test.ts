import { describe, expect, it } from 'vitest'
import { isPartial, mergeGeometry, missingCells } from './geometry'
import type { Geometry, SegmentInfo } from './types'

/** A geometry of whole segments: one [cell, chrom, points] per segment, positions = point index. */
function geo(segs: [string, string, number][], extra: Partial<Geometry['header']> = {}): Geometry {
  const n = segs.reduce((a, s) => a + s[2], 0)
  const positions = new Float32Array(3 * n)
  const starts = new Uint32Array(n)
  const offsets = new Uint32Array(segs.length + 1)
  let at = 0
  const segments: SegmentInfo[] = segs.map(([cell, chrom, k], i) => {
    for (let j = 0; j < k; j++) {
      positions.set([at + j, i, 0], 3 * (at + j))
      starts[at + j] = 1000 * j
    }
    at += k
    offsets[i + 1] = at
    return { trace_id: `${cell}_${chrom}`, chrom, cell_id: cell, n_points: k, start: 0, end: 1000 * k }
  })
  return {
    header: {
      n_points: n, n_segments: segs.length, total_points: n, truncated: false, segments,
      bbox: { min: [0, 0, 0], max: [n, segs.length, 0] }, chrom_extent: { chr1: [0, 5000] }, ...extra,
    },
    positions, starts, offsets,
  }
}

describe('geometry of a sampled overview', () => {
  it('knows when cells may be missing and which', () => {
    const a = geo([['c1', 'chr1', 3], ['c2', 'chr1', 2]], { sample: { cells: 2, of_cells: 5 } })
    expect(isPartial(a)).toBe(true)
    expect(isPartial(geo([['c1', 'chr1', 3]]))).toBe(false)
    expect(isPartial(geo([['c1', 'chr1', 3]], { truncated: true }))).toBe(true)
    expect(missingCells(a, ['c2', 'c4', 'c3'])).toEqual(['c4', 'c3'])
  })

  it('appends the segments of new cells and keeps the arrays aligned', () => {
    const a = geo([['c1', 'chr1', 3], ['c2', 'chr1', 2]], { sample: { cells: 2, of_cells: 5 } })
    const b = geo([['c2', 'chr1', 2], ['c4', 'chr1', 4], ['c4', 'chr2', 1]], { chrom_extent: { chr2: [0, 9000] } })
    const m = mergeGeometry(a, b)
    expect(m.header.n_points).toBe(5 + 5)                       // c2 is not added twice
    expect(m.header.n_segments).toBe(4)
    expect(Array.from(m.offsets)).toEqual([0, 3, 5, 9, 10])
    expect(m.header.segments.map((s) => s.trace_id)).toEqual(['c1_chr1', 'c2_chr1', 'c4_chr1', 'c4_chr2'])
    expect(m.positions.length).toBe(3 * 10)
    expect(Array.from(m.positions.subarray(3 * 5, 3 * 6))).toEqual([2, 1, 0])   // c4's first point, from b
    expect(Array.from(m.starts.subarray(5, 9))).toEqual([0, 1000, 2000, 3000])
    expect(m.header.chrom_extent).toEqual({ chr1: [0, 5000], chr2: [0, 9000] })
    expect(m.header.sample).toEqual({ cells: 2, of_cells: 5 })
    expect(mergeGeometry(m, b)).toBe(m)                           // nothing new: the same object
  })
})

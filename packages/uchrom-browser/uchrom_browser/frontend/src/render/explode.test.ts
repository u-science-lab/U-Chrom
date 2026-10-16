import { describe, expect, it } from 'vitest'
import { decodeGeometry } from '../api'
import { encodeGeometry } from '../testing'
import { subsetGeometry } from './partition'
import { explodeGeometry, explodeOffsets } from './explode'

/**
 * Two cells.  Cell a: chr1 = 2 spots around (-1, 0, 0), chr2 = 2 spots around (3, 0, 0)
 * → cell centre (1, 0, 0); cell b: chr1 alone, far away (its offset is 0).
 */
function geom() {
  const header = {
    total_points: 5,
    truncated: false,
    segments: [
      { trace_id: 'a1', chrom: 'chr1', cell_id: 'a', n_points: 2, start: 0, end: 200 },
      { trace_id: 'a2', chrom: 'chr2', cell_id: 'a', n_points: 2, start: 0, end: 200 },
      { trace_id: 'b1', chrom: 'chr1', cell_id: 'b', n_points: 1, start: 0, end: 100 },
    ],
    bbox: { min: [-2, -1, 0] as [number, number, number], max: [100, 1, 0] as [number, number, number] },
    chrom_extent: {},
  }
  return decodeGeometry(encodeGeometry(header, [-2, 0, 0, 0, 0, 0, 3, -1, 0, 3, 1, 0, 100, 0, 0], [0, 100, 0, 100, 0], [0, 2, 4, 5]))
}

const pts = (p: Float32Array) => Array.from({ length: p.length / 3 }, (_, i) => [p[3 * i], p[3 * i + 1], p[3 * i + 2]])

describe('separated chromosomes', () => {
  it('offsets: copy centroid − cell centroid, per cell', () => {
    const o = explodeOffsets(geom())
    expect(o.get('a\u0000a1\u0000chr1')).toEqual([-2, 0, 0])
    expect(o.get('a\u0000a2\u0000chr2')).toEqual([2, 0, 0])
    expect(o.get('b\u0000b1\u0000chr1')).toEqual([0, 0, 0])
  })

  it('factor 0 is the original structure', () => {
    const g = geom()
    expect(explodeGeometry(g, explodeOffsets(g), 0)).toBe(g)
  })

  it('moves each copy rigidly away from its cell centre and updates the bounding box', () => {
    const g = geom()
    const e = explodeGeometry(g, explodeOffsets(g), 1.5)
    expect(pts(e.positions)).toEqual([
      [-5, 0, 0],
      [-3, 0, 0],
      [6, -1, 0],
      [6, 1, 0],
      [100, 0, 0],
    ])
    // shapes kept: distances within a copy unchanged
    expect(e.positions[3] - e.positions[0]).toBe(g.positions[3] - g.positions[0])
    expect(e.header.bbox).toEqual({ min: [-5, -1, 0], max: [100, 1, 0] })
    // the input is not modified
    expect(g.positions[0]).toBe(-2)
  })

  it('a subset moves with its parent (offsets from the whole geometry)', () => {
    const g = geom()
    const offsets = explodeOffsets(g)
    const sub = subsetGeometry(g, (s) => s.trace_id === 'a2')
    const whole = explodeGeometry(g, offsets, 2)
    const part = explodeGeometry(sub, offsets, 2)
    expect(pts(part.positions)).toEqual(pts(whole.positions).slice(2, 4))
  })

  it('skips non-finite spots in the centroids', () => {
    const header = {
      total_points: 3,
      truncated: false,
      segments: [{ trace_id: 't', chrom: 'chr1', cell_id: null, n_points: 3, start: 0, end: 300 }],
      bbox: null,
      chrom_extent: {},
    }
    const g = decodeGeometry(encodeGeometry(header, [0, 0, 0, NaN, NaN, NaN, 2, 0, 0], [0, 100, 200], [0, 3]))
    expect(explodeOffsets(g).get('\u0000t\u0000chr1')).toEqual([0, 0, 0])
  })
})

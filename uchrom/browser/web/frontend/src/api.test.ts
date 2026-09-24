import { describe, expect, it } from 'vitest'
import { decodeGeometry } from './api'
import { encodeGeometry, sampleHeader } from './testing'

describe('decodeGeometry', () => {
  it('round-trips the binary layout', () => {
    const pos = [0, 0, 0, 1, 0, 0, 2, 0, 0, 3, 4, 0, 1, 1, 0]
    const buf = encodeGeometry(sampleHeader(), pos, [0, 100, 200, 100, 200], [0, 3, 5])
    const g = decodeGeometry(buf)
    expect(g.header.n_points).toBe(5)
    expect(g.header.n_segments).toBe(2)
    expect(g.header.segments[1].cell_id).toBeNull()
    expect(Array.from(g.positions)).toEqual(pos)
    expect(Array.from(g.starts)).toEqual([0, 100, 200, 100, 200])
    expect(Array.from(g.offsets)).toEqual([0, 3, 5])
  })

  it('handles an empty selection', () => {
    const h = { ...sampleHeader(), segments: [], total_points: 0 }
    const g = decodeGeometry(encodeGeometry(h, [], [], [0]))
    expect(g.header.n_points).toBe(0)
    expect(g.offsets.length).toBe(1)
  })

  it('rejects truncated payloads', () => {
    const buf = encodeGeometry(sampleHeader(), new Array(15).fill(0), [0, 1, 2, 3, 4], [0, 3, 5])
    expect(() => decodeGeometry(buf.slice(0, buf.byteLength - 4))).toThrow(/expected/)
    expect(() => decodeGeometry(new ArrayBuffer(2))).toThrow()
  })
})

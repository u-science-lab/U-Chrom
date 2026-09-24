import { describe, expect, it } from 'vitest'
import { autoTubeRadius, bboxDiagonal, buildLineIndex, findSegment, tubeAllowed, tubeVertexEstimate } from './segments'
import { sampleHeader } from '../testing'

describe('buildLineIndex', () => {
  it('connects consecutive points inside segments only', () => {
    expect(Array.from(buildLineIndex(Uint32Array.from([0, 3, 5])))).toEqual([0, 1, 1, 2, 3, 4])
  })
  it('skips single-point segments and handles empty input', () => {
    expect(Array.from(buildLineIndex(Uint32Array.from([0, 1, 3])))).toEqual([1, 2])
    expect(buildLineIndex(Uint32Array.from([0])).length).toBe(0)
  })
})

describe('findSegment', () => {
  const off = Uint32Array.from([0, 3, 5, 9])
  it('binary-searches the owning segment', () => {
    expect([0, 2, 3, 4, 5, 8].map((i) => findSegment(off, i))).toEqual([0, 0, 1, 1, 2, 2])
  })
  it('returns -1 out of range', () => {
    expect(findSegment(off, 9)).toBe(-1)
    expect(findSegment(off, -1)).toBe(-1)
    expect(findSegment(Uint32Array.from([0]), 0)).toBe(-1)
  })
  it('skips empty segments', () => {
    expect(findSegment(Uint32Array.from([0, 2, 2, 4]), 2)).toBe(2)
  })
})

describe('tube sizing', () => {
  const h = { ...sampleHeader(), n_points: 5, n_segments: 2 }
  it('auto radius is 0.35 × the median bond length', () => {
    // bonds of length 1, 2, 4 → median 2 → radius 0.7, independent of bbox size
    const positions = Float32Array.from([0, 0, 0, 1, 0, 0, 3, 0, 0, 100, 0, 0, 100, 4, 0])
    const offsets = Uint32Array.from([0, 3, 5])
    expect(autoTubeRadius({ positions, offsets, header: h })).toBeCloseTo(0.7)
  })
  it('falls back to 0.3% of the bbox diagonal without bonds', () => {
    expect(bboxDiagonal(h.bbox)).toBeCloseTo(5)
    const single = { positions: Float32Array.from([0, 0, 0, 1, 1, 1]), offsets: Uint32Array.from([0, 1, 2]), header: h }
    expect(autoTubeRadius(single)).toBeCloseTo(0.015)
  })
  it('estimates vertices and enforces limits', () => {
    // (2·2+1)·9 + (1·2+1)·9
    expect(tubeVertexEstimate(h, false)).toBe(72)
    expect(tubeAllowed(h)).toBe(true)
    expect(tubeAllowed({ ...h, n_segments: 5000 })).toBe(false)
    expect(tubeAllowed({ ...h, n_points: 600_000 })).toBe(false)
  })
})

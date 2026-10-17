import { describe, expect, it } from 'vitest'
import { plotArea } from './chart'

const M = { left: 62, top: 14, right: 16, bottom: 44 }
const ratio = (b: { w: number; h: number }) => b.w / b.h

describe('plot area of a chart', () => {
  it('fills the space inside the margins when its shape is between 1:1 and 2:1', () => {
    expect(plotArea(527, 372, M)).toEqual({ x: 62, y: 14, w: 449, h: 314 })
  })
  it('a very wide view: 2:1, centred horizontally', () => {
    const b = plotArea(1068, 171, M) // inside: 990 × 113
    expect(ratio(b)).toBeCloseTo(2, 6)
    expect(b.h).toBe(113)
    expect(b.x - M.left).toBeCloseTo(990 - b.x - b.w + M.left, 6) // same space left and right
  })
  it('a very tall view: 1:1, centred vertically', () => {
    const b = plotArea(262, 784, M) // inside: 184 × 726
    expect(b.w).toBe(184)
    expect(b.h).toBe(184)
    expect(b.y).toBeCloseTo(14 + (726 - 184) / 2, 6)
  })
  it('never collapses', () => {
    const b = plotArea(0, 0, M)
    expect(b.w).toBeGreaterThan(0)
    expect(b.h).toBeGreaterThan(0)
  })
})

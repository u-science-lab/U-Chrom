import { describe, expect, it } from 'vitest'
import { NEUTRAL_RGB, cellColor, cellRgb, fieldColor, fieldRange, hexToRgb } from '../colors'
import { fitPlot, nearestPoint, project } from './embedding'

describe('embedding scatter helpers', () => {
  it('fits each axis independently into the padded box, y up', () => {
    const p = fitPlot([0, 10, null], [100, 300, 5], 120, 220, 10)
    expect(p.sx(0)).toBe(10)
    expect(p.sx(10)).toBe(110)
    expect(p.sy(100)).toBe(210) // min y at the bottom
    expect(p.sy(300)).toBe(10)
    expect(p.bounds).toEqual({ x0: 0, x1: 10, y0: 100, y1: 300 }) // null row ignored
  })
  it('handles degenerate and empty data', () => {
    const p = fitPlot([2, 2], [3, 3], 100, 100, 0)
    expect(p.sx(2)).toBe(50)
    expect(fitPlot([], [], 10, 10, 0).bounds).toEqual({ x0: 0, x1: 1, y0: 0, y1: 1 })
  })
  it('projects and hit-tests within a radius', () => {
    const px = project([0, 10, null], [0, 10, 1], fitPlot([0, 10], [0, 10], 100, 100, 0))
    expect(Array.from(px.slice(0, 4))).toEqual([0, 100, 100, 0])
    expect(Number.isNaN(px[4])).toBe(true)
    expect(nearestPoint(px, 3, 97, 8)).toBe(0)
    expect(nearestPoint(px, 96, 3, 8)).toBe(1)
    expect(nearestPoint(px, 50, 50, 8)).toBe(-1)
  })
})

describe('cellRgb matches the 3-D overview colouring', () => {
  const cellIndex = new Map([['a', 0], ['b', 1]])
  it('per cell', () => {
    expect(cellRgb('b', 'cell', '#fff', { cellIndex })).toEqual(cellColor(1))
  })
  it('per field with the shared p99 range', () => {
    const cellValues = new Map<string, number | null>([['a', 1], ['b', 9]])
    const r = fieldRange(cellValues.values())
    expect(cellRgb('b', 'field', '#fff', { cellValues, fieldRange: r })).toEqual(fieldColor(9, r))
  })
  it('custom and neutral', () => {
    expect(cellRgb('a', 'custom', '#ff0000')).toEqual(hexToRgb('#ff0000'))
    expect(cellRgb('a', 'rainbow', '#fff')).toEqual(NEUTRAL_RGB)
  })
})

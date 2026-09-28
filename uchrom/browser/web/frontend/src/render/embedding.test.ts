import { describe, expect, it } from 'vitest'
import { NEUTRAL_RGB, cellColor, cellRgb, fieldColor, fieldRange, hexToRgb } from '../colors'
import { IDENTITY_VIEW, MAX_ZOOM, applyView, fitPlot, fitPlotEqual, gridSpacing, isIdentity, nearestPoint, panBy, project, zoomAt } from './embedding'

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

describe('embedding zoom / pan', () => {
  it('zoomAt keeps the cursor point fixed and clamps', () => {
    const v = zoomAt(IDENTITY_VIEW, 100, 50, 2)
    expect(v.k).toBe(2)
    // the point under the cursor maps to itself
    expect(v.tx + v.k * 100).toBeCloseTo(100)
    expect(v.ty + v.k * 50).toBeCloseTo(50)
    expect(zoomAt(v, 0, 0, 0.1)).toEqual(IDENTITY_VIEW) // below 1 → full view
    expect(zoomAt(IDENTITY_VIEW, 0, 0, 1e9).k).toBe(MAX_ZOOM)
  })
  it('panBy and applyView', () => {
    const v = panBy({ k: 2, tx: 1, ty: 2 }, 10, -5)
    expect(v).toEqual({ k: 2, tx: 11, ty: -3 })
    const px = new Float32Array([1, 2, NaN, NaN])
    const out = applyView(px, v)
    expect(Array.from(out.slice(0, 2))).toEqual([13, 1])
    expect(Number.isNaN(out[2]) && Number.isNaN(out[3])).toBe(true)
    expect(applyView(px, IDENTITY_VIEW)).toBe(px)
    expect(isIdentity(IDENTITY_VIEW)).toBe(true)
  })
})

describe('fitPlotEqual (cell positions to scale)', () => {
  it('one scale for both axes, centred; y down or up', () => {
    // 200 x 100 data in a 100 x 100 box: scale 0.5, centred vertically
    const p = fitPlotEqual([0, 200], [0, 100], 100, 100, 0)
    expect(p.sx(0)).toBeCloseTo(0)
    expect(p.sx(200)).toBeCloseTo(100)
    expect(p.sy(100)).toBeCloseTo(25) // y up: the top of the data at the top
    expect(p.sy(0)).toBeCloseTo(75)
    const d = fitPlotEqual([0, 200], [0, 100], 100, 100, 0, { yDown: true })
    expect(d.sy(0)).toBeCloseTo(25)
    expect(d.sy(100)).toBeCloseTo(75)
  })
  it('fits an image extent instead of the points', () => {
    const p = fitPlotEqual([10], [10], 100, 100, 0, { yDown: true, extent: [0, 1000, 0, 1000] })
    expect(p.sx(1000)).toBeCloseTo(100)
    expect(p.sy(500)).toBeCloseTo(50)
  })
})

describe('gridSpacing', () => {
  it('median gap of distinct coordinates', () => {
    expect(gridSpacing([0, 10, 20, 20, 30], [5, 5, 5, 5, 5])).toBe(10)
    expect(gridSpacing([1, 2, 3], [0, 0.5, 1])).toBe(0.5)
    expect(gridSpacing([1, null], [2, 2])).toBeNull()
  })
})

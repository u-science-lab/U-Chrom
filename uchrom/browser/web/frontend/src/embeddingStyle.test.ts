import { describe, expect, it } from 'vitest'
import { cmap, COLORMAPS } from './colormaps'
import { categoryColor, HIDDEN_RGB, MISSING_RGB, rgbCss } from './colors'
import {
  autoFieldRange,
  autoRadius,
  categoryDotColors,
  categoryLegend,
  DEFAULT_EMB_STYLE,
  defaultRangeMode,
  dotRadius,
  drawOrder,
  fieldScaleRange,
  numericDotColors,
  parseEmbStyle,
  patchEmbStyle,
  quantileSorted,
  resolveEmbStyle,
  solidDotColors,
  sortedFinite,
} from './embeddingStyle'
import type { CellField, CellValue } from './types'
import { parseWorkspace } from './workspace'

const close = (a: number[], b: number[]) => a.forEach((x, i) => expect(x).toBeCloseTo(b[i], 3))

describe('added colormaps', () => {
  it('plasma and Blues endpoints (matplotlib)', () => {
    close(cmap('plasma', 0), [13 / 255, 8 / 255, 135 / 255])
    close(cmap('plasma', 1), [240 / 255, 249 / 255, 33 / 255])
    close(cmap('blues', 0), [247 / 255, 251 / 255, 1])
    close(cmap('blues', 1), [8 / 255, 48 / 255, 107 / 255])
    expect(COLORMAPS.map((c) => c.name)).toEqual(expect.arrayContaining(['viridis', 'magma', 'inferno', 'plasma', 'blues', 'reds', 'greys']))
  })
})

describe('pane style settings', () => {
  it('defaults: overview colouring, auto size, circles', () => {
    const st = resolveEmbStyle(undefined)
    expect(st).toEqual(DEFAULT_EMB_STYLE)
    expect(st.colorBy).toBe('overview')
    expect(st.size).toBeNull()
    expect(st.highOnTop).toBe(true)
  })
  it('parse keeps well-formed fields, clamps size / opacity, drops junk', () => {
    expect(parseEmbStyle(null)).toBeUndefined()
    expect(parseEmbStyle({ bogus: 1, shape: 'star', cmap: 'nope', solid: 'red' })).toBeUndefined()
    expect(parseEmbStyle({ colorBy: 'field', field: 'rna.Mobp', size: 40, opacity: 0, shape: 'square', hidden: ['a'] })).toEqual({
      colorBy: 'field',
      field: 'rna.Mobp',
      size: 10,
      opacity: 0.1,
      shape: 'square',
      hidden: ['a'],
    })
    expect(parseEmbStyle({ hidden: ['a', 3] })).toBeUndefined()
  })
  it('a field colouring without a field resolves to the overview', () => {
    expect(resolveEmbStyle({ colorBy: 'field' }).colorBy).toBe('overview')
  })
  it('patch drops defaults, clears hidden categories on a new field', () => {
    expect(patchEmbStyle(undefined, { size: 3 })).toEqual({ size: 3 })
    expect(patchEmbStyle({ size: 3 }, { size: null })).toBeUndefined()
    expect(patchEmbStyle({ shape: 'square' }, { shape: 'circle' })).toBeUndefined()
    const s = patchEmbStyle({ colorBy: 'field', field: 'cell_type', hidden: ['L2/3'] }, { field: 'subclass' })
    expect(s).toEqual({ colorBy: 'field', field: 'subclass' })
    expect(patchEmbStyle({ colorBy: 'field', field: 'cell_type' }, { hidden: [] })).toEqual({ colorBy: 'field', field: 'cell_type' })
  })
  it('persists with the workspace; old workspaces without it still parse', () => {
    const base = { layout: 'columns', activePane: 'P2', sizes: [0.5, 0.5] }
    const old = parseWorkspace({ ...base, panes: [{ id: 'P1', type: 'matrix' }, { id: 'P2', type: 'embedding', embeddingKey: null, dims: [0, 1] }] })
    expect(old?.panes[1].embStyle).toBeUndefined()
    const ws = parseWorkspace({
      ...base,
      panes: [{ id: 'P1', type: 'matrix' }, { id: 'P2', type: 'embedding', embStyle: { colorBy: 'solid', solid: '#ff0000', opacity: 0.5, junk: true } }],
    })
    expect(ws?.panes[1].embStyle).toEqual({ colorBy: 'solid', solid: '#ff0000', opacity: 0.5 })
    const broken = parseWorkspace({ ...base, panes: [{ id: 'P1', type: 'matrix' }, { id: 'P2', type: 'embedding', embStyle: 'x' }] })
    expect(broken?.panes[1].embStyle).toBeUndefined()
  })
})

describe('numeric ranges', () => {
  it('quantiles interpolate', () => {
    const s = sortedFinite([4, null, 0, 'x', 2, NaN, 1, 3])
    expect([...s]).toEqual([0, 1, 2, 3, 4])
    expect(quantileSorted(s, 0)).toBe(0)
    expect(quantileSorted(s, 0.5)).toBe(2)
    expect(quantileSorted(s, 0.125)).toBeCloseTo(0.5)
    expect(quantileSorted(s, 1)).toBe(4)
    expect(quantileSorted([], 0.5)).toBeNaN()
  })
  it('auto = min–max; quantile clips outliers; sparse genes fall back to the max', () => {
    const v = sortedFinite([...Array.from({ length: 99 }, (_, i) => i), 10000])
    expect(autoFieldRange(v, 'auto')).toEqual([0, 10000])
    const [lo, hi] = autoFieldRange(v, 'quantile')
    expect(lo).toBeCloseTo(0.99)
    expect(hi).toBeLessThan(200)
    const sparse = sortedFinite([...Array(995).fill(0), 1, 2, 3, 4, 5])
    expect(autoFieldRange(sparse, 'quantile')).toEqual([0, 5])
    expect(autoFieldRange(sortedFinite([7, 7]), 'auto')).toEqual([7, 8])
    expect(autoFieldRange(new Float64Array(), 'auto')).toEqual([0, 1])
  })
  it('default range: quantiles for genes / ATAC; manual ends override', () => {
    expect(defaultRangeMode('rna.Mobp')).toBe('quantile')
    expect(defaultRangeMode('atac.Mobp')).toBe('quantile')
    expect(defaultRangeMode('n_contacts')).toBe('auto')
    const v = sortedFinite([0, 10, 20])
    expect(fieldScaleRange(v, { range: null, lo: null, hi: null, field: 'n_contacts' })).toEqual([0, 20])
    expect(fieldScaleRange(v, { range: 'manual', lo: 5, hi: null, field: 'n_contacts' })).toEqual([5, 20])
    expect(fieldScaleRange(v, { range: 'auto', lo: 5, hi: 6, field: 'x' })).toEqual([0, 20]) // lo/hi only in manual mode
  })
})

describe('dot colours and draw order', () => {
  const ids = ['a', 'b', 'c', 'd']
  it('numeric: colormap over the range, missing grey and underneath, high on top', () => {
    const values = new Map<string, CellValue>([
      ['a', 5],
      ['b', null],
      ['c', 0],
      ['d', 10],
    ])
    const st = { ...DEFAULT_EMB_STYLE, cmap: 'magma' as const }
    const d = numericDotColors(ids, values, st, [0, 10])
    expect(d.css[1]).toBe(rgbCss(MISSING_RGB))
    expect(d.css[2]).toBe(rgbCss(cmap('magma', 0)))
    expect(d.css[3]).toBe(rgbCss(cmap('magma', 1)))
    expect([...drawOrder(4, d.key)!]).toEqual([1, 2, 0, 3])
    // high-on-top off: missing still first, the rest in data order
    const d2 = numericDotColors(ids, values, { ...st, highOnTop: false }, [0, 10])
    expect([...drawOrder(4, d2.key)!]).toEqual([1, 0, 2, 3])
    // reversed map swaps the ends
    expect(numericDotColors(ids, values, { ...st, reverse: true }, [0, 10]).css[2]).toBe(rgbCss(cmap('magma', 1)))
  })
  it('categorical: app colours, hidden dark and underneath', () => {
    const field: CellField = { name: 'cell_type', group: 'cell', label: 'cell_type', kind: 'category', min: null, max: null, n_valid: 3, categories: [{ value: 'X', count: 2 }, { value: 'Y', count: 1 }] }
    const values = new Map<string, CellValue>([
      ['a', 'X'],
      ['b', 'Y'],
      ['c', null],
      ['d', 'X'],
    ])
    const d = categoryDotColors(ids, values, field, ['X'])
    expect(d.css[0]).toBe(rgbCss(HIDDEN_RGB))
    expect(d.css[1]).toBe(rgbCss(categoryColor(1, 'Y')))
    expect(d.css[2]).toBe(rgbCss(MISSING_RGB))
    expect(drawOrder(4, d.key)![3]).toBe(1)
    const lg = categoryLegend(field, values, ['X'])
    expect(lg.rows).toEqual([
      { value: 'X', count: 2, color: rgbCss(categoryColor(0, 'X')), off: true },
      { value: 'Y', count: 1, color: rgbCss(categoryColor(1, 'Y')), off: false },
    ])
    expect(lg.missing).toBe(1)
  })
  it('solid colour; bad hex falls back', () => {
    expect(solidDotColors(2, '#ff0000').css).toEqual(['rgb(255, 0, 0)', 'rgb(255, 0, 0)'])
    expect(solidDotColors(1, 'nope').css[0]).toBe(solidDotColors(1, DEFAULT_EMB_STYLE.solid).css[0])
  })
  it('order: null when data order will do; group members last (stable)', () => {
    expect(drawOrder(3, new Float64Array(3))).toBeNull()
    expect([...drawOrder(4, new Float64Array(4), (i) => i === 0 || i === 2)!]).toEqual([1, 3, 0, 2])
    expect([...drawOrder(3, Float64Array.from([2, -Infinity, 1]), (i) => i === 1)!]).toEqual([2, 0, 1])
  })
  it('radius: automatic by cell count unless set', () => {
    expect(autoRadius(5313, 340, 340)).toBe(1.6)
    expect(autoRadius(47, 340, 340)).toBe(3.4)
    expect(autoRadius(47, 1000, 1000)).toBe(6.8)
    expect(dotRadius({ size: 4 }, 5313, 340, 340)).toBe(4)
    expect(dotRadius({ size: null }, 1000, 340, 340)).toBe(2.4)
  })
})

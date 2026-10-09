import { describe, expect, it } from 'vitest'
import {
  autoRange,
  cmap,
  COLORMAPS,
  defaultColorScale,
  effectiveRange,
  parseColorScale,
  resolveColorScale,
  scaleColor,
  scalePos,
  scaleValue,
} from './colormaps'
import { parseRows, setRowColor, type GenomeRow } from './genomeRows'
import { parseWorkspace } from './workspace'

const close = (a: number[], b: number[]) => a.forEach((x, i) => expect(x).toBeCloseTo(b[i], 3))

describe('colormap LUTs', () => {
  it('endpoints of each map', () => {
    close(cmap('fall', 0), [1, 1, 1]) // white …
    close(cmap('fall', 1), [0, 0, 0]) // … to black
    close(cmap('viridis', 0), [68 / 255, 1 / 255, 84 / 255])
    close(cmap('viridis', 1), [253 / 255, 231 / 255, 37 / 255])
    close(cmap('greys', 0), [1, 1, 1])
    close(cmap('rdbu_r', 0.5), [247 / 255, 247 / 255, 247 / 255]) // diverging: white middle
    for (const c of COLORMAPS) for (const t of [0, 0.37, 1]) for (const v of cmap(c.name, t)) expect(v >= 0 && v <= 1).toBe(true)
  })
  it('reverse swaps the ends; out-of-range t clamps', () => {
    expect(cmap('magma', 0, true)).toEqual(cmap('magma', 1))
    expect(cmap('magma', 0.25, true)).toEqual(cmap('magma', 0.75))
    expect(cmap('inferno', -3)).toEqual(cmap('inferno', 0))
    expect(cmap('inferno', 7)).toEqual(cmap('inferno', 1))
    expect(cmap('inferno', NaN)).toEqual(cmap('inferno', 0))
  })
})

describe('colour scales', () => {
  it('log scaling: log1p of the offset from the range start, inverse for colour-bar ticks', () => {
    expect(scalePos(0, [0, 99], true)).toBe(0)
    expect(scalePos(9, [0, 99], true)).toBeCloseTo(Math.log(10) / Math.log(100))
    expect(scalePos(99, [0, 99], true)).toBe(1)
    expect(scalePos(9, [0, 99], false)).toBeCloseTo(9 / 99)
    expect(scaleValue(scalePos(9, [0, 99], true), [0, 99], true)).toBeCloseTo(9)
    expect(scalePos(500, [0, 99], true)).toBe(1) // clipped
  })
  it('a manual range overrides the automatic one; a half-set range keeps the other end', () => {
    const auto: [number, number] = [0.4, 4.7]
    expect(effectiveRange(auto, { min: null, max: null })).toEqual(auto)
    expect(effectiveRange(auto, { min: 1, max: 2 })).toEqual([1, 2])
    expect(effectiveRange(auto, { min: null, max: 3 })).toEqual([0.4, 3])
    const [lo, hi] = effectiveRange(auto, { min: 5, max: 5 })
    expect(hi).toBeGreaterThan(lo) // never a zero-width range
    const cs = { ...defaultColorScale('distance'), reverse: false, min: 1, max: 2 }
    expect(scaleColor(1, cs, effectiveRange(auto, cs), [0, 0, 0])).toEqual(cmap('viridis', 0))
    expect(scaleColor(9, cs, effectiveRange(auto, cs), [0, 0, 0])).toEqual(cmap('viridis', 1))
  })
  it('automatic ranges: contacts from 0, distances p1–p99, diverging symmetric', () => {
    const d = Float32Array.from(Array.from({ length: 101 }, (_, i) => i))
    expect(autoRange(d, 'distance')).toEqual([1, 99])
    expect(autoRange(d, 'contacts')).toEqual([0, 99])
    expect(autoRange(Float32Array.from([-1, 0.5, 3]), 'distance', true)).toEqual([-3, 3])
  })
  it('defaults per kind keep the former look; stored changes resolve over them', () => {
    expect(defaultColorScale('contacts')).toMatchObject({ cmap: 'fall', log: true, reverse: false })
    expect(defaultColorScale('distance')).toMatchObject({ cmap: 'viridis', log: false, reverse: true })
    expect(resolveColorScale('contacts', { cmap: 'reds', max: 50 })).toEqual({ cmap: 'reds', reverse: false, log: true, min: null, max: 50 })
    expect(resolveColorScale('distance', { cmap: 'nope' as never })).toEqual(defaultColorScale('distance'))
    expect(parseColorScale({ cmap: 'magma', log: 'yes', min: NaN, max: 3 })).toEqual({ cmap: 'magma', max: 3 })
    expect(parseColorScale({})).toBeUndefined()
  })
})

describe('colour settings persist with rows and panes', () => {
  it('old rows (no colour) migrate to the defaults; settings round-trip', () => {
    const old = parseRows([{ id: 'r1', kind: 'matrix', source: 'distance' }])!
    expect(old[0].color).toBeUndefined() // → defaults of its kind
    const rows: GenomeRow[] = setRowColor(old, 'r1', { cmap: 'magma', reverse: false, min: 0.2 })
    const ws = parseWorkspace(JSON.parse(JSON.stringify({ layout: 'columns', panes: [{ id: 'P1', type: 'genome', genomeRows: { d: rows } }, { id: 'P2', type: 'matrix', color: { cmap: 'reds', log: false } }] })))!
    expect(ws.panes[0].genomeRows!.d[0].color).toEqual({ cmap: 'magma', reverse: false, min: 0.2 })
    expect(ws.panes[1].color).toEqual({ cmap: 'reds', log: false })
    expect('color' in setRowColor(rows, 'r1', undefined)[0]).toBe(false) // reset
  })
})

describe('log2 ratio maps', () => {
  it('default to a diverging map with a range symmetric around 0', () => {
    expect(defaultColorScale('ratio')).toMatchObject({ cmap: 'rdbu_r', log: false })
    const data = Float32Array.from([-0.3, -0.1, 0, 0.05, 0.1, 0.2, NaN])
    const [lo, hi] = autoRange(data, 'ratio', true)
    expect(lo).toBeCloseTo(-hi)
    expect(hi).toBeGreaterThan(0)
  })
})

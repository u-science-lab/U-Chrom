import { describe, expect, it } from 'vitest'
import { decodeGeometry } from './api'
import { TAB20, cellColor, chromColor, hexToRgb, rainbow, vertexColors } from './colors'
import { encodeGeometry, sampleHeader } from './testing'

const rgbOf = (arr: Float32Array, i: number) => Array.from(arr.slice(3 * i, 3 * i + 3))
const close = (a: number[], b: number[]) => a.forEach((v, k) => expect(v).toBeCloseTo(b[k], 5))

describe('colour helpers', () => {
  it('parses hex colours', () => {
    expect(hexToRgb('#ff0000')).toEqual([1, 0, 0])
    expect(hexToRgb('0f0')).toEqual([0, 1, 0])
    expect(() => hexToRgb('#zzz')).toThrow()
  })
  it('gives stable, distinct chromosome colours', () => {
    expect(chromColor('chr1')).toBe(chromColor('chr1'))
    const names = Array.from({ length: 22 }, (_, i) => `chr${i + 1}`).concat(['chrX', 'chrY'])
    expect(new Set(names.map(chromColor)).size).toBe(names.length)
  })
  it('rainbow runs violet/blue → red and clamps', () => {
    expect(rainbow(1)).toEqual(rainbow(2))
    const [r1, , b1] = rainbow(1)
    const [r0, , b0] = rainbow(0)
    expect(r1).toBeGreaterThan(b1)
    expect(b0).toBeGreaterThan(r0)
  })
})

describe('vertexColors', () => {
  const pos = new Array(15).fill(0)
  const geom = () => decodeGeometry(encodeGeometry(sampleHeader(), pos, [0, 100, 200, 100, 200], [0, 3, 5]))

  it('custom paints everything one colour', () => {
    const c = vertexColors(geom(), 'custom', '#0000ff')
    for (let i = 0; i < 5; i++) expect(rgbOf(c, i)).toEqual([0, 0, 1])
  })
  it('per-trace uses tab20 by first appearance', () => {
    const c = vertexColors(geom(), 'trace', '#fff')
    close(rgbOf(c, 0), hexToRgb(TAB20[0]))
    close(rgbOf(c, 3), hexToRgb(TAB20[1]))
  })
  it('single-chrom rainbow follows genomic position on the dataset-wide extent', () => {
    const c = vertexColors(geom(), 'rainbow', '#fff')
    close(rgbOf(c, 0), rainbow(0))
    close(rgbOf(c, 2), rainbow(200 / 400))
    // same bin in another trace → same colour
    close(rgbOf(c, 1), rgbOf(c, 3))
  })
  it('multi-chrom rainbow colours by chromosome', () => {
    const h = sampleHeader()
    h.segments[1] = { ...h.segments[1], chrom: 'chr2' }
    h.chrom_extent.chr2 = [0, 400]
    const g = decodeGeometry(encodeGeometry(h, pos, [0, 100, 200, 100, 200], [0, 3, 5]))
    const c = vertexColors(g, 'rainbow', '#fff')
    close(rgbOf(c, 0), hexToRgb(chromColor('chr1')))
    close(rgbOf(c, 4), hexToRgb(chromColor('chr2')))
  })
})

describe('chromColors override', () => {
  it('keeps per-chromosome colours for a single visible chromosome', () => {
    const g = decodeGeometry(
      encodeGeometry(
        { ...sampleHeader(), segments: [{ trace_id: 't1', chrom: 'chr2', cell_id: null, n_points: 2, start: 0, end: 200 }] },
        [0, 0, 0, 1, 0, 0],
        [0, 100],
        [0, 2],
      ),
    )
    const gradient = vertexColors(g, 'rainbow', '#ffffff')
    expect(Array.from(gradient.slice(0, 3))).not.toEqual(Array.from(gradient.slice(3, 6)))
    const fixed = vertexColors(g, 'rainbow', '#ffffff', { chromColors: true })
    expect(Array.from(fixed.slice(0, 3))).toEqual(hexToRgb(chromColor('chr2')).map((x) => Math.fround(x)))
    expect(Array.from(fixed.slice(3, 6))).toEqual(Array.from(fixed.slice(0, 3)))
  })
})

describe('per-cell colours', () => {
  const seg = (trace_id: string, cell_id: string | null) => ({ trace_id, chrom: 'chr1', cell_id, n_points: 1, start: 0, end: 100 })
  const g = () =>
    decodeGeometry(
      encodeGeometry(
        { ...sampleHeader(), segments: [seg('a', 'c2'), seg('b', 'c1'), seg('c', 'c2'), seg('d', null)] },
        [0, 0, 0, 1, 0, 0, 2, 0, 0, 3, 0, 0],
        [0, 0, 0, 0],
        [0, 1, 2, 3, 4],
      ),
    )
  it('gives each cell one colour, using the dataset cell order when provided', () => {
    const c = vertexColors(g(), 'cell', '#fff', { cellIndex: new Map([['c1', 0], ['c2', 1]]) })
    const f = (rgb: number[]) => rgb.map((x) => Math.fround(x))
    expect(rgbOf(c, 1)).toEqual(f(cellColor(0)))
    expect(rgbOf(c, 0)).toEqual(f(cellColor(1)))
    expect(rgbOf(c, 2)).toEqual(rgbOf(c, 0)) // same cell, same colour
    expect(rgbOf(c, 3)).toEqual(f([0.6, 0.6, 0.6])) // no cell → grey
  })
  it('neighbouring cell indices get clearly different hues', () => {
    for (let i = 0; i < 200; i++) {
      const [a, b] = [cellColor(i), cellColor(i + 1)]
      expect(Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])).toBeGreaterThan(0.25)
    }
  })
})

import { describe, expect, it } from 'vitest'
import { binAt, decodeMatrix, fall, matrixColor, matrixPixels, matrixRange, quantile, scaleFor } from './matrix'

function encode(header: object, data: number[]): ArrayBuffer {
  let json = new TextEncoder().encode(JSON.stringify(header))
  const pad = (4 - (json.length % 4)) % 4
  if (pad) {
    const p = new Uint8Array(json.length + pad)
    p.set(json)
    p.fill(0x20, json.length)
    json = p
  }
  const buf = new ArrayBuffer(4 + json.length + 4 * data.length)
  new DataView(buf).setUint32(0, json.length, true)
  new Uint8Array(buf, 4, json.length).set(json)
  new Float32Array(buf, 4 + json.length, data.length).set(data)
  return buf
}

const H = { chrom: 'chr21', start: 0, end: 30, n_rows: 2, n_cols: 3, bin_starts: [0, 10, 20], bin_ends: [10, 20, 30], value: 'count' }

describe('binary matrix payload', () => {
  it('decodes header and row-major values (NaN kept)', () => {
    const m = decodeMatrix(encode(H, [1, 2, 3, 4, NaN, 6]))
    expect(m.header.chrom).toBe('chr21')
    expect(Array.from(m.data.slice(0, 4))).toEqual([1, 2, 3, 4])
    expect(Number.isNaN(m.data[4])).toBe(true)
  })
  it('rejects truncated or inconsistent payloads', () => {
    const good = encode(H, [1, 2, 3, 4, 5, 6])
    expect(() => decodeMatrix(good.slice(0, good.byteLength - 4))).toThrow('expected')
    expect(() => decodeMatrix(new ArrayBuffer(2))).toThrow('too short')
  })
})

describe('colour scales', () => {
  it('picks the scale from the value kind', () => {
    expect(scaleFor('count')).toBe('contacts')
    expect(scaleFor('balanced')).toBe('contacts')
    expect(scaleFor('distance')).toBe('distance')
    expect(scaleFor('contact_frequency')).toBe('frequency')
  })
  it('contacts use a log range from the 99th percentile; zeros stay white', () => {
    const data = Float32Array.from([0, 0, 1, 9, 99, NaN])
    const [lo, hi] = matrixRange(data, 'contacts')
    expect(lo).toBe(0)
    expect(hi).toBeCloseTo(Math.log1p(99))
    expect(matrixColor(0, 'contacts', [lo, hi])).toEqual([1, 1, 1])
    expect(matrixColor(99, 'contacts', [lo, hi])).toEqual(fall(1))
    expect(matrixColor(NaN, 'contacts', [lo, hi])).toEqual([0.38, 0.38, 0.4])
  })
  it('distances are reversed: near = bright', () => {
    const near = matrixColor(0.1, 'distance', [0.1, 2])
    const far = matrixColor(2, 'distance', [0.1, 2])
    const lum = (c: number[]) => 0.3 * c[0] + 0.6 * c[1] + 0.1 * c[2]
    expect(lum(near)).toBeGreaterThan(lum(far))
    expect(matrixRange(Float32Array.from([1, 1, 1]), 'distance')).toEqual([1, 2]) // degenerate
  })
  it('makes one RGBA pixel per bin', () => {
    const m = decodeMatrix(encode(H, [0, 1, 2, 3, 4, 5]))
    const px = matrixPixels(m, 'contacts', matrixRange(m.data, 'contacts'))
    expect(px.length).toBe(4 * 6)
    expect(Array.from(px.slice(0, 4))).toEqual([255, 255, 255, 255])
  })
  it('quantile ignores non-finite values', () => {
    expect(quantile(Float32Array.from([NaN, 1, 2, 3]), 0.5)).toBe(2)
    expect(Number.isNaN(quantile([NaN], 0.5))).toBe(true)
  })
})

describe('bin lookup', () => {
  it('finds bins with gaps', () => {
    const s = [0, 10, 50]
    const e = [10, 20, 60]
    expect(binAt(s, e, 15)).toBe(1)
    expect(binAt(s, e, 30)).toBe(-1)
    expect(binAt(s, e, 55)).toBe(2)
    expect(binAt(s, e, 60)).toBe(-1)
  })
})

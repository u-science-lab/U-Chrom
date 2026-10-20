/** Small numeric helpers for the stats / tracks panes (no DOM). */

import { GENOME, type Locus } from './genome'

/** API chromosome parameter for chromosome-scoped stats; null means all chromosomes. */
export function statsChrom(scope: 'all' | 'locus' | undefined, locus: Locus | null | undefined): string | null {
  return scope === 'locus' && locus?.chrom && locus.chrom !== GENOME ? locus.chrom : null
}

export interface Histogram {
  edges: number[]
  counts: number[]
}

/** Histogram of the finite values with `nbins` equal bins over [min, max]. */
export function histogram(values: Iterable<unknown>, nbins = 30, range?: [number, number]): Histogram {
  const v: number[] = []
  for (const x of values) if (typeof x === 'number' && Number.isFinite(x)) v.push(x)
  const n = Math.max(1, Math.floor(nbins))
  let lo = range ? range[0] : Math.min(...v)
  let hi = range ? range[1] : Math.max(...v)
  if (!v.length) [lo, hi] = [0, 1]
  if (hi === lo) [lo, hi] = [lo - 0.5, hi + 0.5]
  const w = (hi - lo) / n
  const edges = Array.from({ length: n + 1 }, (_, i) => lo + i * w)
  const counts = new Array(n).fill(0)
  for (const x of v) {
    if (x < lo || x > hi) continue
    counts[Math.min(n - 1, Math.floor((x - lo) / w))]++
  }
  return { edges, counts }
}

/** Linear map [d0, d1] → [r0, r1]. */
export function linear(d0: number, d1: number, r0: number, r1: number): (v: number) => number {
  const k = d1 !== d0 ? (r1 - r0) / (d1 - d0) : 0
  return (v) => r0 + (v - d0) * k
}

/** Log10 map [d0, d1] (both > 0) → [r0, r1]; non-positive inputs → NaN. */
export function logScale(d0: number, d1: number, r0: number, r1: number): (v: number) => number {
  const a = Math.log10(d0)
  const b = Math.log10(d1)
  const k = b !== a ? (r1 - r0) / (b - a) : 0
  return (v) => (v > 0 ? r0 + (Math.log10(v) - a) * k : NaN)
}

/** [min, max] of the finite values (fallback [0, 1]). */
export function extent(values: Iterable<unknown>): [number, number] {
  let lo = Infinity
  let hi = -Infinity
  for (const x of values) {
    if (typeof x !== 'number' || !Number.isFinite(x)) continue
    if (x < lo) lo = x
    if (x > hi) hi = x
  }
  if (!Number.isFinite(lo)) return [0, 1]
  return hi > lo ? [lo, hi] : [lo - 0.5, hi + 0.5]
}

/**
 * Value range of a track row: symmetric around 0 when the data has both
 * signs (z-scores, diverging colours), else [0, max] (or [min, 0]).
 */
export function trackRange(values: Iterable<unknown>): { lo: number; hi: number; diverging: boolean } {
  const [mn, mx] = extent(values)
  if (mn < 0 && mx > 0) {
    const m = Math.max(-mn, mx)
    return { lo: -m, hi: m, diverging: true }
  }
  if (mx <= 0) return { lo: mn, hi: 0, diverging: false }
  return { lo: Math.min(0, mn), hi: mx, diverging: false }
}

/** Compact number for axes: 1.2k, 3.4M, 0.012. */
export function fmtAxis(v: number): string {
  const a = Math.abs(v)
  if (a === 0) return '0'
  if (a >= 1e6) return `${+(v / 1e6).toFixed(2)}M`
  if (a >= 1e3) return `${+(v / 1e3).toFixed(2)}k`
  if (a >= 1) return `${+v.toFixed(2)}`
  return `${+v.toPrecision(2)}`
}

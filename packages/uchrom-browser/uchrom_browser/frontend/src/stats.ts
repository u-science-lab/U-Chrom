/** Small numeric helpers for the stats / tracks panes (no DOM). */

import { GENOME, type Locus } from './genome'
import type { RgStats } from './types'

export type StatsChromScope = 'all' | 'locus' | 'window'

/** API chromosome parameter for chromosome-scoped stats; null means all chromosomes. */
export function statsChrom(scope: StatsChromScope | undefined, locus: Locus | null | undefined): string | null {
  return (scope === 'locus' || scope === 'window') && locus?.chrom && locus.chrom !== GENOME ? locus.chrom : null
}

/** API region parameters (chrom, start, end) for all / locus / window stats scopes. */
export function statsRegion(
  scope: StatsChromScope | undefined,
  locus: Locus | null | undefined,
): { chrom: string | null; start: number | null; end: number | null } {
  const chrom = statsChrom(scope, locus)
  if (!chrom || scope !== 'window' || !locus) return { chrom, start: null, end: null }
  const start = Math.max(0, Math.round(locus.start))
  const end = Math.round(locus.end)
  if (!(end > start)) return { chrom, start: null, end: null }
  return { chrom, start, end }
}

/** Per-cell median Rg across finite traces belonging to each non-null cell_id. */
export function perCellMedians(rg: RgStats): number[] {
  const byCell = new Map<string, number[]>()
  for (let i = 0; i < rg.rg.length; i++) {
    const cid = rg.cell_ids[i]
    const v = rg.rg[i]
    if (!cid || typeof v !== 'number' || !Number.isFinite(v)) continue
    let list = byCell.get(cid)
    if (!list) {
      list = []
      byCell.set(cid, list)
    }
    list.push(v)
  }
  const out: number[] = []
  for (const vals of byCell.values()) {
    vals.sort((a, b) => a - b)
    const m = vals.length
    out.push(m % 2 ? vals[(m - 1) / 2] : (vals[m / 2 - 1] + vals[m / 2]) / 2)
  }
  return out
}

export interface MannWhitneyResult {
  u: number
  p: number
  rankBiserial: number
  exploratory: boolean
}

function erfcApprox(x: number): number {
  const z = Math.abs(x)
  const t = 1 / (1 + 0.3275911 * z)
  const poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
  const res = poly * Math.exp(-z * z)
  return x >= 0 ? res : 2 - res
}

/**
 * Exact U_a and two-sided tie- and continuity-corrected normal-approximation p-value.
 * Returns null if either sample has no finite values.
 */
export function mannWhitneyTwoSided(a: readonly number[], b: readonly number[]): MannWhitneyResult | null {
  const va = a.filter((x) => typeof x === 'number' && Number.isFinite(x))
  const vb = b.filter((x) => typeof x === 'number' && Number.isFinite(x))
  const nA = va.length
  const nB = vb.length
  if (!nA || !nB) return null

  const pooled = [
    ...va.map((v) => ({ v, grp: 0 as const })),
    ...vb.map((v) => ({ v, grp: 1 as const })),
  ].sort((x, y) => x.v - y.v)

  let rankSumA = 0
  let tieSum = 0
  let i = 0
  const N = pooled.length
  while (i < N) {
    let j = i + 1
    while (j < N && pooled[j].v === pooled[i].v) j++
    const t = j - i
    const avgRank = (i + 1 + j) / 2
    for (let k = i; k < j; k++) {
      if (pooled[k].grp === 0) rankSumA += avgRank
    }
    if (t > 1) tieSum += t * t * t - t
    i = j
  }

  const u = rankSumA - (nA * (nA + 1)) / 2
  const totalPairs = nA * nB
  const rankBiserial = (2 * u) / totalPairs - 1
  const exploratory = Math.min(nA, nB) < 5
  const tieCorr = N > 1 ? tieSum / (N * (N - 1)) : 0
  const varU = (totalPairs / 12) * (N + 1 - tieCorr)
  if (!(varU > 0)) return { u, p: 1, rankBiserial: 0, exploratory }

  const diff = Math.abs(u - totalPairs / 2)
  if (diff <= 0.5) return { u, p: 1, rankBiserial, exploratory }
  const z = (diff - 0.5) / Math.sqrt(varU)
  const p = Math.min(1, Math.max(0, erfcApprox(z / Math.SQRT2)))
  return { u, p, rankBiserial, exploratory }
}

/** True if two group cell-id lists share at least one non-null cell id. */
export function hasOverlappingCells(a: readonly (string | null)[], b: readonly (string | null)[]): boolean {
  const seen = new Set<string>()
  for (const x of a) if (x) seen.add(x)
  for (const x of b) if (x && seen.has(x)) return true
  return false
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

/** Bins of whole width centred on the integers when every value is one (counts, channel numbers): `nbins` equal
 * bins over [min, max] would put two integers into some bins and none into others.  Null for other values. */
export function integerBins(values: readonly number[], nbins: number): { nbins: number; range: [number, number] } | null {
  if (!values.length || !values.every(Number.isInteger)) return null
  const lo = Math.min(...values)
  const span = Math.max(...values) - lo + 1
  const w = Math.ceil(span / Math.max(1, Math.floor(nbins)))
  const n = Math.ceil(span / w)
  return { nbins: n, range: [lo - 0.5, lo - 0.5 + n * w] }
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

/** Compact number for axes: 1.2k, 3.4M, 0.012, 1e-5. */
export function fmtAxis(v: number): string {
  const a = Math.abs(v)
  if (a === 0) return '0'
  if (a >= 1e6) return `${+(v / 1e6).toFixed(2)}M`
  if (a >= 1e3) return `${+(v / 1e3).toFixed(2)}k`
  if (a >= 1) return `${+v.toFixed(2)}`
  if (a >= 1e-3) return `${+v.toPrecision(2)}`
  return v.toExponential(1).replace(/\.0e/, 'e')
}

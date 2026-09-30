/**
 * Genome-coordinate helpers shared by the tracks / matrix / stats panes:
 * the shared locus (chrom:start-end), parsing, zoom / pan math and axis
 * ticks.  Pure — no DOM.
 */

import { fmtBp, parseGenomicNumber, parseRange } from './filters'
import type { DatasetSummary } from './types'

export interface Locus {
  chrom: string
  start: number
  end: number
}

/** A chromosome the locus navigator can offer, with its valid extent. */
export interface ChromExtent {
  name: string
  start: number
  end: number
}

/** Smallest window the navigator zooms to (bp). */
export const MIN_SPAN = 1_000

/**
 * Chromosomes of a dataset for the locus navigator: those with 3-D spots
 * (their spot extent) plus those of every contact map (0 … length).
 */
export function datasetChroms(ds: Pick<DatasetSummary, 'chroms' | 'contact_maps'> | undefined): ChromExtent[] {
  if (!ds) return []
  const out = new Map<string, ChromExtent>()
  for (const c of ds.chroms ?? []) out.set(c.name, { name: c.name, start: c.start, end: c.end })
  for (const m of ds.contact_maps ?? []) {
    for (const c of m.chroms ?? []) {
      const prev = out.get(c.name)
      out.set(c.name, prev ? { name: c.name, start: Math.min(prev.start, 0), end: Math.max(prev.end, c.length) } : { name: c.name, start: 0, end: c.length })
    }
  }
  return [...out.values()]
}

/** Default locus: the whole first chromosome (spots first, else contact maps). */
export function defaultLocus(chroms: ChromExtent[]): Locus | null {
  const c = chroms[0]
  return c ? { chrom: c.name, start: c.start, end: c.end } : null
}

/** Clamp a window into the chromosome, keeping its span when possible. */
export function clampLocus(l: Locus, ext: ChromExtent | undefined): Locus {
  if (!ext) return { chrom: l.chrom, start: Math.round(l.start), end: Math.round(l.end) } // whole bp even without an extent
  const full = ext.end - ext.start
  let span = Math.max(Math.min(MIN_SPAN, full), Math.min(l.end - l.start, full))
  if (!Number.isFinite(span) || span <= 0) span = full
  let start = Math.round(l.start)
  if (start < ext.start) start = ext.start
  if (start + span > ext.end) start = ext.end - span
  return { chrom: l.chrom, start, end: Math.round(start + span) }
}

/**
 * Parse "chr7", "chr7:10.2M-12.5M", "chr7:10,200,000-12,500,000" or a bare
 * "10M-12M" (on `current`'s chromosome) into a clamped locus.
 */
export function parseLocus(text: string, chroms: ChromExtent[], current?: Locus | null): Locus {
  const t = text.trim()
  if (!t) throw new Error('empty locus')
  const byName = new Map(chroms.map((c) => [c.name.toLowerCase(), c]))
  const colon = t.indexOf(':')
  let chromName: string
  let rangeText: string | null
  if (colon >= 0) {
    chromName = t.slice(0, colon).trim()
    rangeText = t.slice(colon + 1).trim() || null
  } else if (byName.has(t.toLowerCase())) {
    chromName = t
    rangeText = null
  } else {
    if (!current) throw new Error(`unknown chromosome "${t}"`)
    chromName = current.chrom
    rangeText = t
  }
  const ext = byName.get(chromName.toLowerCase())
  if (!ext) throw new Error(`unknown chromosome "${chromName}"`)
  if (!rangeText) return { chrom: ext.name, start: ext.start, end: ext.end }
  let start: number
  let end: number
  if (/[-–]|\.\./.test(rangeText)) ({ start, end } = parseRange(rangeText))
  else {
    // a single position: centre a 1 Mb window on it
    const p = parseGenomicNumber(rangeText)
    start = p - 500_000
    end = p + 500_000
  }
  if (end <= ext.start || start >= ext.end) throw new Error(`${ext.name}:${fmtBp(start)}-${fmtBp(end)} is outside ${fmtBp(ext.start)}-${fmtBp(ext.end)}`)
  return clampLocus({ chrom: ext.name, start: Math.max(start, ext.start), end: Math.min(end, ext.end) }, ext)
}

export function fmtLocus(l: Locus): string {
  return `${l.chrom}:${fmtBp(l.start)}-${fmtBp(l.end)}`
}

/** Zoom by `factor` (< 1 zooms in) around genomic position `center` (default: middle). */
export function zoomLocus(l: Locus, factor: number, ext?: ChromExtent, center?: number): Locus {
  const span = l.end - l.start
  const c = center ?? (l.start + l.end) / 2
  const newSpan = Math.max(MIN_SPAN, span * factor)
  // keep `c` at the same relative position in the window
  const rel = span > 0 ? (c - l.start) / span : 0.5
  const start = c - rel * newSpan
  return clampLocus({ chrom: l.chrom, start, end: start + newSpan }, ext)
}

/** Shift by `delta` bp (positive → right). */
export function panLocus(l: Locus, delta: number, ext?: ChromExtent): Locus {
  return clampLocus({ chrom: l.chrom, start: l.start + delta, end: l.end + delta }, ext)
}

/** "Nice" tick positions (1, 2, 5 × 10^k) inside [lo, hi], about `n` of them. */
export function niceTicks(lo: number, hi: number, n = 5): number[] {
  if (!(hi > lo) || !Number.isFinite(lo) || !Number.isFinite(hi)) return []
  const raw = (hi - lo) / Math.max(1, n)
  const mag = Math.pow(10, Math.floor(Math.log10(raw)))
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Number(v.toPrecision(12)))
  return out
}

/** Decade ticks for a log axis over [lo, hi] (both > 0). */
export function logTicks(lo: number, hi: number): number[] {
  if (!(lo > 0) || !(hi > lo)) return []
  const out: number[] = []
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
    const v = Math.pow(10, e)
    if (v >= lo * (1 - 1e-9) && v <= hi * (1 + 1e-9)) out.push(v)
  }
  return out
}

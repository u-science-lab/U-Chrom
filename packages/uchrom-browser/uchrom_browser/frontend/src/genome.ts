/**
 * Genome-coordinate helpers shared by the tracks / matrix / stats panes:
 * the shared locus (chrom:start-end), parsing, zoom / pan math and axis
 * ticks.  Pure — no DOM.
 */

import { fmtBp, parseGenomicNumber, parseRange } from './filters'
import type { DatasetSummary, GenomeChrom } from './types'

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
  /** the whole genome (name GENOME): its chromosomes end to end */
  layout?: GenomeChrom[]
}

/** "Chromosome" of the whole-genome view: positions are genome coordinates (chromosomes end to end). */
export const GENOME = '*'
export const GENOME_LABEL = 'All'
export const isGenome = (l: { chrom: string } | null | undefined) => l?.chrom === GENOME

/** The whole-genome extent of a layout (only for several chromosomes). */
export function genomeExtent(layout: GenomeChrom[] | undefined): ChromExtent | null {
  if (!layout || layout.length < 2) return null
  const last = layout[layout.length - 1]
  return { name: GENOME, start: 0, end: last.offset + last.length, layout }
}

/** Genome coordinate → chromosome and position (null outside the layout). */
export function genomeToChrom(layout: GenomeChrom[], bp: number): { chrom: string; pos: number } | null {
  let lo = 0
  let hi = layout.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    const c = layout[mid]
    if (bp < c.offset) hi = mid - 1
    else if (bp >= c.offset + c.length) lo = mid + 1
    else return { chrom: c.name, pos: bp - c.offset }
  }
  const last = layout[layout.length - 1]
  return last && bp === last.offset + last.length ? { chrom: last.name, pos: last.length } : null
}

/** "chr3:12.5M" for a position on `chrom` (genome coordinates when chrom is GENOME). */
export function fmtPos(chrom: string, bp: number, layout?: GenomeChrom[]): string {
  if (chrom !== GENOME) return `${chrom}:${fmtBp(bp)}`
  const c = layout ? genomeToChrom(layout, bp) : null
  return c ? `${c.chrom}:${fmtBp(c.pos)}` : fmtBp(bp)
}

/** "chr3:10M-12M" for [start, end) on `chrom` (genome coordinates when chrom is GENOME). */
export function fmtSpan(chrom: string, start: number, end: number, layout?: GenomeChrom[]): string {
  if (chrom !== GENOME) return `${chrom}:${fmtBp(start)}-${fmtBp(end)}`
  const c = layout ? genomeToChrom(layout, start) : null
  return c ? `${c.chrom}:${fmtBp(c.pos)}-${fmtBp(c.pos + end - start)}` : `${fmtBp(start)}-${fmtBp(end)}`
}

/** The region a view requests: the whole genome at once in the whole-genome view (its data
 *  do not change with the window), else the window. */
export function queryRegion(l: Locus): { chrom: string; start?: number; end?: number } {
  return l.chrom === GENOME ? { chrom: GENOME } : l
}

/** Key of `queryRegion` (effects re-request when it changes). */
export const regionKey = (l: Locus | null | undefined) => (!l ? '' : l.chrom === GENOME ? GENOME : `${l.chrom}|${l.start}|${l.end}`)

/** Smallest window the navigator zooms to (bp). */
export const MIN_SPAN = 1_000

/**
 * Chromosomes of a dataset for the locus navigator: those with 3-D spots
 * (their spot extent) plus those of every contact map (0 … length).
 */
export function datasetChroms(ds: Pick<DatasetSummary, 'chroms' | 'contact_maps' | 'genome'> | undefined): ChromExtent[] {
  if (!ds) return []
  const all = genomeExtent(ds.genome)
  const out = new Map<string, ChromExtent>()
  for (const c of ds.chroms ?? []) out.set(c.name, { name: c.name, start: c.start, end: c.end })
  for (const m of ds.contact_maps ?? []) {
    for (const c of m.chroms ?? []) {
      const prev = out.get(c.name)
      out.set(c.name, prev ? { name: c.name, start: Math.min(prev.start, 0), end: Math.max(prev.end, c.length) } : { name: c.name, start: 0, end: c.length })
    }
  }
  return all ? [all, ...out.values()] : [...out.values()]
}

/** Default locus: the whole first chromosome (spots first, else contact maps). */
export function defaultLocus(chroms: ChromExtent[]): Locus | null {
  const c = chroms.find((x) => x.name !== GENOME)
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
 * "10M-12M" (on `current`'s chromosome) into a clamped locus; "All" (or
 * "genome", "*") is the whole genome and "chr3:10M-chr5:20M" a window of it.
 */
export function parseLocus(text: string, chroms: ChromExtent[], current?: Locus | null): Locus {
  const t = text.trim()
  if (!t) throw new Error('empty locus')
  const byName = new Map(chroms.map((c) => [c.name.toLowerCase(), c]))
  const all = byName.get(GENOME)
  if (all) {
    if (['all', 'genome', GENOME].includes(t.toLowerCase())) return { chrom: GENOME, start: all.start, end: all.end }
    const span = /^(\S+?):(\S+?)\s*(?:-|–|\.\.)\s*(\S+?):(\S+)$/.exec(t)
    if (span && span[1].toLowerCase() !== span[3].toLowerCase()) {
      const at = (name: string, pos: string) => {
        const c = all.layout?.find((x) => x.name.toLowerCase() === name.toLowerCase())
        if (!c) throw new Error(`unknown chromosome "${name}"`)
        return c.offset + Math.min(c.length, Math.max(0, parseGenomicNumber(pos)))
      }
      const a = at(span[1], span[2])
      const b = at(span[3], span[4])
      return clampLocus({ chrom: GENOME, start: Math.min(a, b), end: Math.max(a, b) }, all)
    }
  }
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

/** "chr7:10.2M-12.5M"; in the whole genome "All", or "chr3:10M-chr5:20M" for a window of it. */
export function fmtLocus(l: Locus, chroms?: ChromExtent[]): string {
  if (l.chrom !== GENOME) return `${l.chrom}:${fmtBp(l.start)}-${fmtBp(l.end)}`
  const all = chroms?.find((c) => c.name === GENOME)
  if (!all?.layout || (l.start <= all.start && l.end >= all.end)) return GENOME_LABEL
  return `${fmtPos(GENOME, l.start, all.layout)}-${fmtPos(GENOME, l.end, all.layout)}`
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

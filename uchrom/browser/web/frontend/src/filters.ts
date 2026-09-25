import type { ChromInfo, LayerFilter, Region } from './types'

const SUFFIX: Record<string, number> = { '': 1, b: 1, bp: 1, k: 1e3, kb: 1e3, m: 1e6, mb: 1e6, g: 1e9, gb: 1e9 }

/** "10,000,000" | "10M" | "1.5kb" | "2_000" → integer base pairs. */
export function parseGenomicNumber(text: string): number {
  const t = text.trim().toLowerCase().replace(/[,_\s]/g, '')
  const m = /^(\d+(?:\.\d+)?)([a-z]*)$/.exec(t)
  if (!m || !(m[2] in SUFFIX)) throw new Error(`not a genomic position: "${text}"`)
  return Math.round(parseFloat(m[1]) * SUFFIX[m[2]])
}

/** "10,000,000-20,000,000" | "10M-20M" | "10M..20M" → [start, end). */
export function parseRange(text: string): { start: number; end: number } {
  const parts = text.trim().split(/\s*(?:-|–|\.\.|:)\s*/)
  if (parts.length !== 2 || !parts[0] || !parts[1]) throw new Error(`expected "start-end", got "${text}"`)
  const start = parseGenomicNumber(parts[0])
  const end = parseGenomicNumber(parts[1])
  if (end <= start) throw new Error('end must be greater than start')
  return { start, end }
}

/** Parse a region for `chrom`, validating against the chromosome's extent. */
export function parseRegion(chrom: ChromInfo, text: string): Region {
  const { start, end } = parseRange(text)
  if (end <= chrom.start || start >= chrom.end) {
    throw new Error(`${chrom.name}:${fmtBp(start)}-${fmtBp(end)} is outside ${fmtBp(chrom.start)}-${fmtBp(chrom.end)}`)
  }
  return { chrom: chrom.name, start, end }
}

/**
 * Trace selection: a single id, a 1-based index range "1-50" over
 * `orderedIds`, or a comma-separated mix of ids and ranges.  Exact ids win
 * over range syntax, so numeric trace ids like "3" or "1-2" still work.
 */
export function parseTraceSelection(text: string, orderedIds: string[]): string[] {
  return parseIdSelection(text, orderedIds, 'trace')
}

/** Same syntax as {@link parseTraceSelection} for any id list (cells, …). */
export function parseIdSelection(text: string, orderedIds: string[], what: string): string[] {
  const known = new Set(orderedIds)
  const out: string[] = []
  const seen = new Set<string>()
  const push = (id: string) => {
    if (!seen.has(id)) {
      seen.add(id)
      out.push(id)
    }
  }
  const tokens = text.split(',').map((t) => t.trim()).filter(Boolean)
  if (tokens.length === 0) throw new Error(`empty ${what} selection`)
  for (const tok of tokens) {
    if (known.has(tok)) {
      push(tok)
      continue
    }
    const m = /^(\d+)\s*-\s*(\d+)$/.exec(tok)
    if (m) {
      const a = parseInt(m[1], 10)
      const b = parseInt(m[2], 10)
      if (a < 1 || b < a || b > orderedIds.length) {
        throw new Error(`range ${tok} is outside 1-${orderedIds.length}`)
      }
      for (let i = a; i <= b; i++) push(orderedIds[i - 1])
      continue
    }
    throw new Error(`unknown ${what} "${tok}"`)
  }
  return out
}

function intersect<T>(a: T[] | undefined, b: T[] | undefined): T[] | undefined {
  if (!a) return b ? [...b] : undefined
  if (!b) return [...a]
  const bs = new Set(b)
  return a.filter((x) => bs.has(x))
}

/**
 * AND a child's own filter onto its parent's (already composed) filter.
 * Returns `null` when the combination is provably empty.
 */
export function composeFilter(parent: LayerFilter, child: LayerFilter): LayerFilter | null {
  const out: LayerFilter = {}
  const chroms = intersect(parent.chroms, child.chroms)
  if (chroms) {
    if (chroms.length === 0) return null
    out.chroms = chroms
  }
  let region = parent.region
  if (child.region) {
    if (region) {
      if (region.chrom !== child.region.chrom) return null
      const start = Math.max(region.start, child.region.start)
      const end = Math.min(region.end, child.region.end)
      if (end <= start) return null
      region = { chrom: region.chrom, start, end }
    } else {
      region = { ...child.region }
    }
  }
  if (region) {
    if (out.chroms && !out.chroms.includes(region.chrom)) return null
    out.region = region
  }
  const traces = intersect(parent.trace_ids, child.trace_ids)
  if (traces) {
    if (traces.length === 0) return null
    out.trace_ids = traces
  }
  const cells = intersect(parent.cell_ids, child.cell_ids)
  if (cells) {
    if (cells.length === 0) return null
    out.cell_ids = cells
  }
  return out
}

/** Chromosomes a filter can cover, in dataset order. */
export function chromsOf(filter: LayerFilter, all: ChromInfo[]): ChromInfo[] {
  if (filter.region) return all.filter((c) => c.name === filter.region!.chrom)
  if (filter.chroms) {
    const s = new Set(filter.chroms)
    return all.filter((c) => s.has(c.name))
  }
  return all
}

/** 136550000 → "136.55M", 135875000 → "135.875M", 25000 → "25k"; exact otherwise. */
export function fmtBp(bp: number): string {
  if (bp >= 1e6 && bp % 1e3 === 0) return `${+(bp / 1e6).toFixed(3)}M`
  if (bp >= 1e3 && bp % 1 === 0 && bp % 10 === 0) return `${+(bp / 1e3).toFixed(2)}k`
  return bp.toLocaleString('en-US')
}

/** Short human label for a subset created from `child`. */
export function describeFilter(child: LayerFilter): string {
  if (child.region) return `${child.region.chrom}:${fmtBp(child.region.start)}-${fmtBp(child.region.end)}`
  if (child.cell_ids) {
    const ids = child.cell_ids
    return ids.length <= 3 ? `cell ${ids.join(', ')}` : `${ids.length} cells`
  }
  if (child.trace_ids) {
    const ids = child.trace_ids
    return ids.length <= 3 ? `trace ${ids.join(', ')}` : `${ids.length} traces`
  }
  if (child.chroms) {
    const cs = child.chroms
    return cs.length <= 3 ? cs.join(', ') : `${cs.length} chroms`
  }
  return 'all'
}

/** Pure helpers for the genome-track pane. */

/** Well-known chromatin marks shown by default (in this order) when present. */
export const PREFERRED_TRACKS = ['H3K27ac', 'H3K4me3', 'H3K27me3', 'H3K9me3', 'LaminB1', 'H3K36me3', 'H3K4me1', 'H3K9ac', 'CTCF', 'ATAC']

/**
 * Default selection: up to `max` preferred marks that exist (case-insensitive),
 * else the first `max` tracks.
 */
export function defaultTrackSelection(names: string[], max = 6): string[] {
  const byLower = new Map(names.map((n) => [n.toLowerCase(), n]))
  const picked = PREFERRED_TRACKS.map((p) => byLower.get(p.toLowerCase())).filter((x): x is string => !!x).slice(0, max)
  return picked.length ? picked : names.slice(0, max)
}

/** Selected tracks that the dataset actually has (keeps order); default when empty. */
export function resolveTracks(selected: string[] | null | undefined, names: string[], max = 6): string[] {
  const have = new Set(names)
  const s = (selected ?? []).filter((t) => have.has(t))
  return s.length ? s : defaultTrackSelection(names, max)
}

/** Index of the bin containing `pos` among sorted, non-overlapping bins (or nearest within `slack` bp), -1 if none. */
export function binIndexAt(starts: number[], ends: number[], pos: number, slack = 0): number {
  let lo = 0
  let hi = starts.length - 1
  if (hi < 0) return -1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (starts[mid] <= pos) lo = mid
    else hi = mid - 1
  }
  if (pos >= starts[lo] - slack && pos < ends[lo] + slack) return lo
  if (lo + 1 < starts.length && pos >= starts[lo + 1] - slack) return lo + 1
  return -1
}

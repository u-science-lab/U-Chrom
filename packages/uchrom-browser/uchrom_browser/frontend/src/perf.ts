/**
 * Performance marks for benchmarks (uchrom-reproducibility `benchmarks/browser`).  Read them in the page with
 * `performance.getEntriesByType('mark')`; names are prefixed `uchrom:`.
 */
export function mark(name: string, detail?: Record<string, unknown>) {
  try {
    performance.mark(`uchrom:${name}`, detail ? { detail } : undefined)
  } catch {
    // marks are best-effort; never break the page for a benchmark hook
  }
}

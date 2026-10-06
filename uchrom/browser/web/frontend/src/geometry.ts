/**
 * A layer's geometry may hold only part of its cells: a large store's overview is a sample of whole cells
 * (`header.sample`), and any selection beyond `max_points` is truncated.  A cell drawn in full (the focus, a
 * view's own cell or group) that the overview left out is fetched on its own and merged in, so it is drawn
 * like the others.
 */
import type { Geometry } from './types'

/** Whether the geometry may lack some of the layer's cells. */
export function isPartial(g: Geometry): boolean {
  return !!g.header.sample || g.header.truncated
}

/** Cells of the geometry (segments with a cell). */
export function geometryCells(g: Geometry): Set<string> {
  const out = new Set<string>()
  for (const s of g.header.segments) if (s.cell_id !== null) out.add(s.cell_id)
  return out
}

/** The wanted cells that the geometry does not hold, in the order given. */
export function missingCells(g: Geometry, wanted: Iterable<string>): string[] {
  const have = geometryCells(g)
  const out: string[] = []
  for (const c of wanted) if (!have.has(c)) out.push(c)
  return out
}

type Box = { min: [number, number, number]; max: [number, number, number] }

function unionBox(a: Box | null, b: Box | null): Box | null {
  if (!a) return b
  if (!b) return a
  return {
    min: [Math.min(a.min[0], b.min[0]), Math.min(a.min[1], b.min[1]), Math.min(a.min[2], b.min[2])],
    max: [Math.max(a.max[0], b.max[0]), Math.max(a.max[1], b.max[1]), Math.max(a.max[2], b.max[2])],
  }
}

/** `a` with the segments of `b` appended (segments of a cell already in `a` are skipped). */
export function mergeGeometry(a: Geometry, b: Geometry): Geometry {
  const have = geometryCells(a)
  const keep: number[] = []
  b.header.segments.forEach((s, i) => {
    if (s.cell_id === null || !have.has(s.cell_id)) keep.push(i)
  })
  if (!keep.length) return a
  let added = 0
  for (const i of keep) added += b.offsets[i + 1] - b.offsets[i]
  const n = a.header.n_points
  const positions = new Float32Array(3 * (n + added))
  positions.set(a.positions)
  const starts = new Uint32Array(n + added)
  starts.set(a.starts)
  const offsets = new Uint32Array(a.offsets.length + keep.length)
  offsets.set(a.offsets)
  let at = n
  keep.forEach((i, k) => {
    const lo = b.offsets[i]
    const hi = b.offsets[i + 1]
    positions.set(b.positions.subarray(3 * lo, 3 * hi), 3 * at)
    starts.set(b.starts.subarray(lo, hi), at)
    at += hi - lo
    offsets[a.offsets.length + k] = at
  })
  const chromExtent = { ...a.header.chrom_extent }
  for (const [c, [lo, hi]] of Object.entries(b.header.chrom_extent)) {
    const cur = chromExtent[c]
    chromExtent[c] = cur ? [Math.min(cur[0], lo), Math.max(cur[1], hi)] : [lo, hi]
  }
  return {
    header: {
      ...a.header,
      n_points: n + added,
      n_segments: a.header.n_segments + keep.length,
      segments: [...a.header.segments, ...keep.map((i) => b.header.segments[i])],
      bbox: unionBox(a.header.bbox, b.header.bbox),
      chrom_extent: chromExtent,
    },
    positions,
    starts,
    offsets,
  }
}

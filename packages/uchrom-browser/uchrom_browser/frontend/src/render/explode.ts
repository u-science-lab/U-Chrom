/**
 * Separated chromosomes ("exploded view", as in Tan et al. 2018, Dip-C):
 * every chromosome copy is moved away from its cell's centre along the line
 * from that centre to its own centroid, by `factor` times that distance.
 * A rigid translation per copy — the shape of each chromosome is kept, and
 * so is where it lies in the nucleus.  factor 0 is the original structure.
 *
 * The directions come from a dataset's whole (root) geometry, so subset
 * layers (a region, some traces) move with their parent, and hiding
 * chromosomes does not move the others.
 */

import type { Geometry, SegmentInfo } from '../types'

/** Largest separation offered in the view (× each centroid's distance from the cell centre). */
export const MAX_EXPLODE = 3

/** One chromosome copy: its cell, trace and chromosome. */
export function copyKey(s: Pick<SegmentInfo, 'cell_id' | 'trace_id' | 'chrom'>): string {
  return `${s.cell_id ?? ''}\u0000${s.trace_id}\u0000${s.chrom}`
}

/** centroid of each copy − centroid of its cell (spots weighted equally; non-finite spots skipped). */
export type ExplodeOffsets = Map<string, [number, number, number]>

const cache = new WeakMap<Geometry, ExplodeOffsets>()

/** The separation direction (unscaled) of every chromosome copy in `geom` (cached per geometry). */
export function explodeOffsets(geom: Geometry): ExplodeOffsets {
  const hit = cache.get(geom)
  if (hit) return hit
  const { header, positions: P, offsets } = geom
  // sums per copy and per cell: x, y, z, n
  const copies = new Map<string, { cell: string; s: [number, number, number, number] }>()
  const cells = new Map<string, [number, number, number, number]>()
  header.segments.forEach((seg, i) => {
    const key = copyKey(seg)
    const cell = seg.cell_id ?? ''
    let c = copies.get(key)
    if (!c) copies.set(key, (c = { cell, s: [0, 0, 0, 0] }))
    let cs = cells.get(cell)
    if (!cs) cells.set(cell, (cs = [0, 0, 0, 0]))
    for (let p = offsets[i]; p < offsets[i + 1]; p++) {
      const x = P[3 * p]
      const y = P[3 * p + 1]
      const z = P[3 * p + 2]
      if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue
      c.s[0] += x
      c.s[1] += y
      c.s[2] += z
      c.s[3]++
      cs[0] += x
      cs[1] += y
      cs[2] += z
      cs[3]++
    }
  })
  const out: ExplodeOffsets = new Map()
  for (const [key, { cell, s }] of copies) {
    const cs = cells.get(cell)!
    if (!s[3] || !cs[3]) continue
    out.set(key, [s[0] / s[3] - cs[0] / cs[3], s[1] / s[3] - cs[1] / cs[3], s[2] / s[3] - cs[2] / cs[3]])
  }
  cache.set(geom, out)
  return out
}

/**
 * `geom` with each segment moved by `factor` × its copy's offset (copies
 * missing from `offsets` stay put).  factor 0 returns `geom` itself.
 */
export function explodeGeometry(geom: Geometry, offsets: ExplodeOffsets, factor: number): Geometry {
  if (!(factor > 0)) return geom
  const { header, positions: P, offsets: off } = geom
  const pos = new Float32Array(P.length)
  const min: [number, number, number] = [Infinity, Infinity, Infinity]
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity]
  header.segments.forEach((seg, i) => {
    const o = offsets.get(copyKey(seg))
    const dx = o ? o[0] * factor : 0
    const dy = o ? o[1] * factor : 0
    const dz = o ? o[2] * factor : 0
    for (let p = off[i]; p < off[i + 1]; p++) {
      const x = (pos[3 * p] = P[3 * p] + dx)
      const y = (pos[3 * p + 1] = P[3 * p + 1] + dy)
      const z = (pos[3 * p + 2] = P[3 * p + 2] + dz)
      if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) {
        if (x < min[0]) min[0] = x
        if (y < min[1]) min[1] = y
        if (z < min[2]) min[2] = z
        if (x > max[0]) max[0] = x
        if (y > max[1]) max[1] = y
        if (z > max[2]) max[2] = z
      }
    }
  })
  const bbox = Number.isFinite(min[0]) ? { min, max } : header.bbox
  return { ...geom, header: { ...header, bbox }, positions: pos }
}

/** Grid slot shift of each cell (by cell id, else trace id), computed from a dataset's whole geometry. */
export type TileShifts = Map<string, [number, number, number]>

const tileCache = new WeakMap<Geometry, TileShifts>()

/**
 * Cells laid side by side: the rigid shift that moves each cell's centroid onto a square grid in the x-y plane
 * (cells in the order of the geometry, row by row), spaced by the size of the larger cells.  For data whose cells
 * share one frame — single-cell models centred on the origin, or traces in crops of their own (DatasetSummary.
 * cells_overlap) — where the cells otherwise sit on top of each other.  From the dataset's whole (root) geometry,
 * so subset layers move with their cells; cached per geometry.
 */
export function tileShifts(root: Geometry): TileShifts {
  const hit = tileCache.get(root)
  if (hit) return hit
  const { header, positions: P, offsets: off } = root
  const order: string[] = []
  const sums = new Map<string, number[]>() // x, y, z, n, min x, min y, max x, max y
  header.segments.forEach((seg, i) => {
    const cell = seg.cell_id ?? seg.trace_id
    let s = sums.get(cell)
    if (!s) {
      sums.set(cell, (s = [0, 0, 0, 0, Infinity, Infinity, -Infinity, -Infinity]))
      order.push(cell)
    }
    for (let p = off[i]; p < off[i + 1]; p++) {
      const x = P[3 * p]
      const y = P[3 * p + 1]
      const z = P[3 * p + 2]
      if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue
      s[0] += x
      s[1] += y
      s[2] += z
      s[3]++
      s[4] = Math.min(s[4], x)
      s[5] = Math.min(s[5], y)
      s[6] = Math.max(s[6], x)
      s[7] = Math.max(s[7], y)
    }
  })
  const out: TileShifts = new Map()
  const sizes = order.map((c) => sums.get(c)!).filter((s) => s[3] > 0).map((s) => Math.max(s[6] - s[4], s[7] - s[5]))
  if (sizes.length >= 2) {
    sizes.sort((a, b) => a - b)
    const step = 1.15 * sizes[Math.min(sizes.length - 1, Math.floor(0.9 * sizes.length))] || 1
    const cols = Math.ceil(Math.sqrt(order.length))
    order.forEach((c, k) => {
      const s = sums.get(c)!
      if (s[3]) out.set(c, [(k % cols) * step - s[0] / s[3], -Math.floor(k / cols) * step - s[1] / s[3], -s[2] / s[3]])
    })
  }
  tileCache.set(root, out)
  return out
}

/** `geom` with every segment moved by its cell's grid shift (cells missing from `shifts` stay put). */
export function tileGeometry(geom: Geometry, shifts: TileShifts): Geometry {
  if (!shifts.size) return geom
  const { header, positions: P, offsets: off } = geom
  const pos = new Float32Array(P.length)
  const min: [number, number, number] = [Infinity, Infinity, Infinity]
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity]
  header.segments.forEach((seg, i) => {
    const d = shifts.get(seg.cell_id ?? seg.trace_id) ?? [0, 0, 0]
    for (let p = off[i]; p < off[i + 1]; p++) {
      for (let a = 0; a < 3; a++) {
        const v = (pos[3 * p + a] = P[3 * p + a] + d[a])
        if (Number.isFinite(v)) {
          if (v < min[a]) min[a] = v
          if (v > max[a]) max[a] = v
        }
      }
    }
  })
  return { ...geom, header: { ...header, bbox: Number.isFinite(min[0]) ? { min, max } : header.bbox }, positions: pos }
}

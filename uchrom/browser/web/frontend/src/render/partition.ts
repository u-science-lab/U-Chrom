import type { Geometry, GeometryHeader, SegmentInfo } from '../types'

/**
 * Copy the segments of `geom` for which `keep(segment, index)` is true into a
 * new, self-contained Geometry (offsets rebased, bbox recomputed).  Used for
 * client-side display filters — hidden chromosomes, the focused cell vs its
 * context — so toggling them never refetches from the server.
 */
export function subsetGeometry(geom: Geometry, keep: (seg: SegmentInfo, index: number) => boolean): Geometry {
  const { header, positions, starts, offsets } = geom
  const kept: number[] = []
  let n = 0
  header.segments.forEach((seg, i) => {
    if (keep(seg, i)) {
      kept.push(i)
      n += offsets[i + 1] - offsets[i]
    }
  })
  if (kept.length === header.segments.length) return geom

  const pos = new Float32Array(3 * n)
  const st = new Uint32Array(n)
  const off = new Uint32Array(kept.length + 1)
  const min: [number, number, number] = [Infinity, Infinity, Infinity]
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity]
  let w = 0
  kept.forEach((i, k) => {
    const a = offsets[i]
    const b = offsets[i + 1]
    pos.set(positions.subarray(3 * a, 3 * b), 3 * w)
    st.set(starts.subarray(a, b), w)
    for (let p = a; p < b; p++) {
      for (let c = 0; c < 3; c++) {
        const v = positions[3 * p + c]
        if (v < min[c]) min[c] = v
        if (v > max[c]) max[c] = v
      }
    }
    w += b - a
    off[k + 1] = w
  })
  const out: GeometryHeader = {
    ...header,
    n_points: n,
    n_segments: kept.length,
    segments: kept.map((i) => header.segments[i]),
    bbox: n ? { min, max } : header.bbox,
  }
  return { header: out, positions: pos, starts: st, offsets: off }
}

/** Distinct cell ids in segment order (null-free). */
export function cellsOf(geom: Geometry): string[] {
  const seen = new Set<string>()
  for (const s of geom.header.segments) if (s.cell_id !== null) seen.add(s.cell_id)
  return [...seen]
}

export interface DisplayParts {
  /** drawn with the layer style; null when nothing is left to draw */
  main: Geometry | null
  /** other cells, drawn faint around the focused one */
  context: Geometry | null
}

/** The cells drawn in full: one focused cell, a group of cells, or everything (null). */
export type FocusSet = string | ReadonlySet<string> | null

/** Membership test of a focus (null = no focus: everything is main). */
export function inFocus(focus: FocusSet, cell: string | null): boolean {
  if (focus === null) return true
  if (cell === null) return false
  return typeof focus === 'string' ? cell === focus : focus.has(cell)
}

/**
 * Split a layer's geometry for display: drop hidden chromosomes, and when a
 * cell (or a group of cells) is in focus put it in `main` and every other
 * cell in `context`.
 */
export function displayParts(geom: Geometry, hiddenChroms: ReadonlySet<string>, focus: FocusSet): DisplayParts {
  const shown = (s: SegmentInfo) => !hiddenChroms.has(s.chrom)
  if (focus === null) {
    const main = subsetGeometry(geom, shown)
    return { main: main.header.n_points ? main : null, context: null }
  }
  const main = subsetGeometry(geom, (s) => shown(s) && inFocus(focus, s.cell_id))
  const context = subsetGeometry(geom, (s) => shown(s) && !inFocus(focus, s.cell_id))
  return {
    main: main.header.n_points ? main : null,
    context: context.header.n_points ? context : null,
  }
}

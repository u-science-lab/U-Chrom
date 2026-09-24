import type { Geometry, GeometryHeader } from '../types'

/** Index pairs (i, i+1) for consecutive points inside each segment. */
export function buildLineIndex(offsets: Uint32Array): Uint32Array {
  let pairs = 0
  for (let s = 0; s + 1 < offsets.length; s++) pairs += Math.max(0, offsets[s + 1] - offsets[s] - 1)
  const idx = new Uint32Array(2 * pairs)
  let k = 0
  for (let s = 0; s + 1 < offsets.length; s++) {
    for (let i = offsets[s]; i + 1 < offsets[s + 1]; i++) {
      idx[k++] = i
      idx[k++] = i + 1
    }
  }
  return idx
}

/** Segment containing point `pointIndex` (binary search over offsets), or -1. */
export function findSegment(offsets: Uint32Array, pointIndex: number): number {
  const nSeg = offsets.length - 1
  if (nSeg <= 0 || pointIndex < offsets[0] || pointIndex >= offsets[nSeg]) return -1
  let lo = 0
  let hi = nSeg - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (offsets[mid] <= pointIndex) lo = mid
    else hi = mid - 1
  }
  return lo
}

export function bboxDiagonal(bbox: GeometryHeader['bbox']): number {
  const d = [0, 1, 2].map((i) => bbox.max[i] - bbox.min[i])
  return Math.hypot(d[0], d[1], d[2])
}

/**
 * Default tube radius: 0.35 × the median distance between consecutive
 * spots, so tubes look the same whether one trace or a whole field of view
 * (hundreds of µm across) is loaded.  Falls back to 0.3% of the bbox
 * diagonal when there are no bonds (only single-spot segments).
 */
export function autoTubeRadius(geom: Pick<Geometry, 'positions' | 'offsets' | 'header'>): number {
  const { positions: p, offsets } = geom
  const bonds: number[] = []
  const stride = Math.max(1, Math.floor(p.length / 3 / 20000)) // sample ≤ ~20k bonds
  for (let s = 0; s + 1 < offsets.length; s++) {
    for (let i = offsets[s]; i + 1 < offsets[s + 1]; i += stride) {
      const a = 3 * i
      const b = a + 3
      bonds.push(Math.hypot(p[b] - p[a], p[b + 1] - p[a + 1], p[b + 2] - p[a + 2]))
    }
  }
  const positive = bonds.filter((d) => d > 0).sort((x, y) => x - y)
  if (positive.length) return positive[Math.floor(positive.length / 2)] * 0.35
  return Math.max(bboxDiagonal(geom.header.bbox) * 0.003, 1e-6)
}

/** Tube rendering limits: beyond these we fall back to lines. */
export const TUBE_MAX_SEGMENTS = 3000
export const TUBE_MAX_POINTS = 500_000
/** ~6M mesh vertices ≈ 220 MB of GPU buffers */
export const TUBE_MAX_VERTICES = 6_000_000

/** Tube mesh vertex count: per segment (n-1)·interp+1 rings × (radial+1). */
export function tubeVertexEstimate(header: GeometryHeader, highQuality: boolean): number {
  const interp = highQuality ? 10 : 2
  const radial = highQuality ? 20 : 8
  return header.segments.reduce((acc, s) => acc + (Math.max(1, s.n_points - 1) * interp + 1) * (radial + 1), 0)
}

export function tubeAllowed(header: GeometryHeader, highQuality = false): boolean {
  return (
    header.n_segments <= TUBE_MAX_SEGMENTS &&
    header.n_points <= TUBE_MAX_POINTS &&
    tubeVertexEstimate(header, highQuality) <= TUBE_MAX_VERTICES
  )
}

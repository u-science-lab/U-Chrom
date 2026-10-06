import type { Geometry, SegmentInfo } from '../types'

type BondGeom = Pick<Geometry, 'positions' | 'offsets'>

/** Length of the bond from point i to point i+1. */
function bondLength(p: Float32Array, i: number): number {
  const a = 3 * i
  const b = a + 3
  return Math.hypot(p[b] - p[a], p[b + 1] - p[a + 1], p[b + 2] - p[a + 2])
}

/**
 * Median distance between consecutive spots of the same segment (positive
 * bonds only), sampling at most ~20k bonds.  null when there are no bonds.
 */
export function medianBond(geom: BondGeom): number | null {
  const { positions: p, offsets } = geom
  const bonds: number[] = []
  const stride = Math.max(1, Math.floor(p.length / 3 / 20000))
  for (let s = 0; s + 1 < offsets.length; s++) {
    for (let i = offsets[s]; i + 1 < offsets[s + 1]; i += stride) {
      const d = bondLength(p, i)
      if (d > 0) bonds.push(d)
    }
  }
  if (!bonds.length) return null
  bonds.sort((x, y) => x - y)
  return bonds[Math.floor(bonds.length / 2)]
}

/** Default "max bond": 10 × the median bond length. */
export const AUTO_BOND_FACTOR = 10

export interface SplitResult {
  geometry: Geometry
  /** bonds longer than the threshold that were cut */
  broken: number
}

/**
 * Cut every bond longer than `maxBond` by starting a new segment there.
 * Points (positions, starts) and their order are untouched, so point
 * indices stay valid for picking; only `offsets` / `header.segments` gain
 * pieces, each piece carrying its parent's metadata with its own
 * n_points / start / end.  Returns the input unchanged when nothing is cut.
 */
export function splitLongBonds(geom: Geometry, maxBond: number | null): SplitResult {
  if (maxBond === null || !(maxBond > 0)) return { geometry: geom, broken: 0 }
  const { positions: p, starts, offsets, header } = geom
  const off: number[] = [0]
  const segs: SegmentInfo[] = []
  let broken = 0
  for (let s = 0; s + 1 < offsets.length; s++) {
    const a = offsets[s]
    const b = offsets[s + 1]
    const seg = header.segments[s]
    let lo = a
    const close = (hi: number) => {
      let st = Infinity
      let en = -Infinity
      for (let i = lo; i < hi; i++) {
        st = Math.min(st, starts[i])
        en = Math.max(en, starts[i])
      }
      // `end` of a piece: its last bin start + the original bin width guess
      const width = seg.n_points > 1 ? Math.max(0, (seg.end - seg.start) / seg.n_points) : seg.end - seg.start
      segs.push({ ...seg, n_points: hi - lo, start: hi > lo ? st : seg.start, end: hi > lo ? Math.round(en + width) : seg.end })
      off.push(hi)
      lo = hi
    }
    let cut = false
    for (let i = a; i + 1 < b; i++) {
      if (bondLength(p, i) > maxBond) {
        broken++
        cut = true
        close(i + 1)
      }
    }
    if (cut) close(b)
    else {
      segs.push(seg)
      off.push(b)
    }
  }
  if (!broken) return { geometry: geom, broken: 0 }
  return {
    geometry: {
      ...geom,
      offsets: Uint32Array.from(off),
      header: { ...header, n_segments: segs.length, segments: segs },
    },
    broken,
  }
}

const cache = new WeakMap<Geometry, Map<string, SplitResult>>()

/** Resolve the view setting ('auto' | number | null) for one geometry. */
export function resolveMaxBond(geom: Geometry, setting: 'auto' | number | null): number | null {
  if (setting === null) return null
  if (setting === 'auto') {
    const m = medianBond(geom)
    return m === null ? null : m * AUTO_BOND_FACTOR
  }
  return setting
}

/** Cached splitLongBonds for a geometry + view setting. */
export function splitForView(geom: Geometry, setting: 'auto' | number | null): SplitResult & { threshold: number | null } {
  const threshold = resolveMaxBond(geom, setting)
  let m = cache.get(geom)
  if (!m) cache.set(geom, (m = new Map()))
  const k = String(threshold)
  let r = m.get(k)
  if (!r) m.set(k, (r = splitLongBonds(geom, threshold)))
  return { ...r, threshold }
}

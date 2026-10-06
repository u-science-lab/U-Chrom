import * as THREE from 'three'
import type { Geometry } from '../types'

/**
 * Hit-testing of large line geometries without testing every segment: the traces are cut into
 * chunks of at most CHUNK consecutive points (within one segment) with a bounding box each; a
 * ray tests the boxes first and only the segments of the boxes it passes near.  Same answer as
 * three.js's LineSegments raycast (nearest bond within `threshold` of the ray), at a fraction
 * of the cost for millions of points.
 */
export interface ChunkIndex {
  /** first / last point (inclusive) of each chunk */
  lo: Uint32Array
  hi: Uint32Array
  /** chunk → segment */
  seg: Uint32Array
  /** chunk boxes: minX, minY, minZ, maxX, maxY, maxZ */
  box: Float32Array
}

export const CHUNK = 128

const cache = new WeakMap<Geometry, ChunkIndex>()

export function chunkIndex(geom: Geometry): ChunkIndex {
  let idx = cache.get(geom)
  if (idx) return idx
  const { offsets, positions: p } = geom
  const lo: number[] = []
  const hi: number[] = []
  const seg: number[] = []
  for (let s = 0; s + 1 < offsets.length; s++) {
    const a = offsets[s]
    const b = offsets[s + 1]
    // chunks share their boundary point, so every bond lies inside one chunk
    for (let i = a; i < b; i += CHUNK) {
      lo.push(i)
      hi.push(Math.min(b - 1, i + CHUNK))
      seg.push(s)
      if (i + CHUNK >= b - 1) break
    }
  }
  const box = new Float32Array(6 * lo.length)
  for (let c = 0; c < lo.length; c++) {
    let x0 = Infinity, y0 = Infinity, z0 = Infinity, x1 = -Infinity, y1 = -Infinity, z1 = -Infinity
    for (let i = lo[c]; i <= hi[c]; i++) {
      const x = p[3 * i], y = p[3 * i + 1], z = p[3 * i + 2]
      if (x < x0) x0 = x
      if (x > x1) x1 = x
      if (y < y0) y0 = y
      if (y > y1) y1 = y
      if (z < z0) z0 = z
      if (z > z1) z1 = z
    }
    box.set([x0, y0, z0, x1, y1, z1], 6 * c)
  }
  idx = { lo: Uint32Array.from(lo), hi: Uint32Array.from(hi), seg: Uint32Array.from(seg), box }
  cache.set(geom, idx)
  return idx
}

/** Ray vs box grown by `pad` (slab test). */
function hitsBox(o: THREE.Vector3, inv: THREE.Vector3, b: Float32Array, k: number, pad: number): boolean {
  let tmin = -Infinity
  let tmax = Infinity
  for (let a = 0; a < 3; a++) {
    const oa = a === 0 ? o.x : a === 1 ? o.y : o.z
    const ia = a === 0 ? inv.x : a === 1 ? inv.y : inv.z
    const lo = b[k + a] - pad
    const hi = b[k + 3 + a] + pad
    if (!Number.isFinite(ia)) {
      if (oa < lo || oa > hi) return false
      continue
    }
    let t0 = (lo - oa) * ia
    let t1 = (hi - oa) * ia
    if (t0 > t1) [t0, t1] = [t1, t0]
    if (t0 > tmin) tmin = t0
    if (t1 < tmax) tmax = t1
    if (tmin > tmax) return false
  }
  return tmax >= 0
}

export interface ChunkHit {
  /** first point of the bond (or the lone point) */
  pointIndex: number
  segment: number
  /** distance from the ray origin, along the ray */
  distance: number
  /** distance of the bond from the ray */
  distanceToRay: number
}

/**
 * Bonds (and lone points) of `geom` within `threshold` of `ray`, best first by
 * distanceToRay / distance (what the 3-D view ranks by) — at most `limit`.
 */
export function raycastChunks(geom: Geometry, ray: THREE.Ray, threshold: number, limit = 8): ChunkHit[] {
  const idx = chunkIndex(geom)
  const p = geom.positions
  const inv = new THREE.Vector3(1 / ray.direction.x, 1 / ray.direction.y, 1 / ray.direction.z)
  const t2 = threshold * threshold
  const va = new THREE.Vector3()
  const vb = new THREE.Vector3()
  const onRay = new THREE.Vector3()
  const onSeg = new THREE.Vector3()
  const out: ChunkHit[] = []
  for (let c = 0; c < idx.lo.length; c++) {
    if (!hitsBox(ray.origin, inv, idx.box, 6 * c, threshold)) continue
    const lo = idx.lo[c]
    const hi = idx.hi[c]
    if (lo === hi) {
      va.fromArray(p, 3 * lo)
      const d2 = ray.distanceSqToPoint(va)
      if (d2 > t2) continue
      ray.closestPointToPoint(va, onRay)
      const distance = ray.origin.distanceTo(onRay)
      out.push({ pointIndex: lo, segment: idx.seg[c], distance, distanceToRay: Math.sqrt(d2) })
      continue
    }
    for (let i = lo; i < hi; i++) {
      va.fromArray(p, 3 * i)
      vb.fromArray(p, 3 * i + 3)
      const d2 = ray.distanceSqToSegment(va, vb, onRay, onSeg)
      if (d2 > t2) continue
      const distance = ray.origin.distanceTo(onRay)
      if (distance <= 0) continue
      out.push({ pointIndex: i, segment: idx.seg[c], distance, distanceToRay: Math.sqrt(d2) })
    }
  }
  out.sort((a, b) => a.distanceToRay / a.distance - b.distanceToRay / b.distance)
  return out.slice(0, limit)
}

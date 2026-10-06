import * as THREE from 'three'
import { describe, expect, it } from 'vitest'
import type { Geometry } from '../types'
import { CHUNK, chunkIndex, raycastChunks } from './raypick'
import { buildLineIndex } from './segments'

function walks(nSeg: number, len: number, seed = 1): Geometry {
  let s = seed
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647)
  const n = nSeg * len
  const pos = new Float32Array(3 * n)
  for (let t = 0; t < nSeg; t++) {
    let x = rnd() * 20, y = rnd() * 20, z = rnd() * 5
    for (let i = 0; i < len; i++) {
      x += rnd() - 0.5
      y += rnd() - 0.5
      z += rnd() - 0.5
      pos.set([x, y, z], 3 * (t * len + i))
    }
  }
  const offsets = Uint32Array.from({ length: nSeg + 1 }, (_, i) => i * len)
  return { header: { n_points: n, n_segments: nSeg, total_points: n, truncated: false, segments: [], bbox: null, chrom_extent: {} }, positions: pos, starts: new Uint32Array(n), offsets }
}

describe('chunked ray picking', () => {
  it('covers every bond exactly once, never across segments', () => {
    const g = walks(3, 300)
    const idx = chunkIndex(g)
    let bonds = 0
    for (let c = 0; c < idx.lo.length; c++) {
      expect(idx.hi[c] - idx.lo[c]).toBeLessThanOrEqual(CHUNK)
      const s = idx.seg[c]
      expect(idx.lo[c]).toBeGreaterThanOrEqual(g.offsets[s])
      expect(idx.hi[c]).toBeLessThan(g.offsets[s + 1])
      bonds += idx.hi[c] - idx.lo[c]
    }
    expect(bonds).toBe(3 * 299)
  })
  it('finds what three.js finds', () => {
    const g = walks(40, 200, 7)
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(g.positions, 3))
    const index = buildLineIndex(g.offsets)
    geo.setIndex(new THREE.BufferAttribute(index, 1))
    const obj = new THREE.LineSegments(geo)
    const cam = new THREE.PerspectiveCamera(45, 1, 0.1, 1000)
    cam.position.set(10, 10, 60)
    cam.lookAt(10, 10, 0)
    cam.updateMatrixWorld()
    const rc = new THREE.Raycaster()
    rc.params.Line = { threshold: 0.3 }
    let compared = 0
    for (let k = 0; k < 25; k++) {
      rc.setFromCamera(new THREE.Vector2(-0.6 + (k % 5) * 0.3, -0.6 + Math.floor(k / 5) * 0.3), cam)
      const three = rc.intersectObject(obj)
      const mine = raycastChunks(g, rc.ray, 0.3, 1e9)
      expect(mine.length).toBe(three.length)
      const bonds = (hits: number[]) => new Set(hits)
      expect(bonds(mine.map((h) => h.pointIndex))).toEqual(bonds(three.map((h) => index[h.index!])))
      compared += three.length
    }
    expect(compared).toBeGreaterThan(0)
  })
})

import * as THREE from 'three'
import { describe, expect, it } from 'vitest'
import { decodeGeometry } from '../api'
import { DEFAULT_STYLE } from '../layers'
import { encodeGeometry, sampleHeader } from '../testing'
import { buildLayerObject, pointIndexOfHit } from './objects'

// segment t1 = points 0..2 at x=0,1,2 ; segment t2 = points 3..4 at x=10,11
const geom = () =>
  decodeGeometry(encodeGeometry(sampleHeader(), [0, 0, 0, 1, 0, 0, 2, 0, 0, 10, 0, 0, 11, 0, 0], [0, 100, 200, 100, 200], [0, 3, 5]))

describe('picking thin lines', () => {
  it('maps a raycast hit back to the real point, not the index-buffer slot', () => {
    const built = buildLayerObject(geom(), { ...DEFAULT_STYLE, mode: 'line', lineWidth: 1 })
    const ray = new THREE.Raycaster(new THREE.Vector3(10.5, 0, 5), new THREE.Vector3(0, 0, -1))
    ray.params.Line = { threshold: 0.1 }
    const hits = ray.intersectObject(built.object)
    expect(hits.length).toBe(1)
    // the hit lies on the t2 bond (points 3–4); its raw hit.index is the
    // index-buffer slot 4, which would wrongly point into t1
    expect(hits[0].index).toBe(4)
    expect(pointIndexOfHit(built.pick, hits[0])).toBe(3)
  })
})

describe('singleton spots in line mode', () => {
  it('are drawn as a Points child and picked back to their point', () => {
    // t1 = points 0..2, t2 = a single point 3, t3 = points 4..5
    const header = {
      ...sampleHeader(),
      total_points: 6,
      segments: [
        { trace_id: 't1', chrom: 'chr1', cell_id: null, n_points: 3, start: 0, end: 300 },
        { trace_id: 't2', chrom: 'chr1', cell_id: null, n_points: 1, start: 0, end: 100 },
        { trace_id: 't3', chrom: 'chr1', cell_id: null, n_points: 2, start: 0, end: 200 },
      ],
    }
    const g = decodeGeometry(encodeGeometry(header, [0, 0, 0, 1, 0, 0, 2, 0, 0, 50, 0, 0, 80, 0, 0, 81, 0, 0], [0, 100, 200, 0, 0, 100], [0, 3, 4, 6]))
    const built = buildLayerObject(g, { ...DEFAULT_STYLE, mode: 'line', lineWidth: 1 })
    const child = built.object.children[0] as THREE.Points
    expect(child.isPoints).toBe(true)
    expect(Array.from(child.userData.singletons as Uint32Array)).toEqual([3])
    const ray = new THREE.Raycaster(new THREE.Vector3(50, 0, 5), new THREE.Vector3(0, 0, -1))
    ray.params.Points = { threshold: 0.1 }
    ray.params.Line = { threshold: 0.1 }
    const hits = ray.intersectObject(built.object, true)
    expect(hits.length).toBe(1)
    expect(pointIndexOfHit(built.pick, hits[0])).toBe(3)
    built.dispose()
  })
})

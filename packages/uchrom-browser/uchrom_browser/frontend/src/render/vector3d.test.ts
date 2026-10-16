import * as THREE from 'three'
import { describe, expect, it } from 'vitest'
import { decodeGeometry } from '../api'
import { DEFAULT_STYLE } from '../layers'
import { encodeGeometry, sampleHeader } from '../testing'
import { buildLayerObject } from './objects'
import { sceneToSvg } from './vector3d'

// segment t1 = points 0..2 at x=0,1,2 ; segment t2 = points 3..4 at x=10,11
const geom = () =>
  decodeGeometry(encodeGeometry(sampleHeader(), [0, 0, 0, 1, 0, 0, 2, 0, 0, 10, 0, 0, 11, 0, 0], [0, 100, 200, 100, 200], [0, 3, 5]))

/** A camera on +z looking at the origin, 100 × 100 px. */
function view() {
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000)
  camera.position.set(5, 0, 20)
  camera.lookAt(5, 0, 0)
  camera.updateProjectionMatrix()
  return camera
}

describe('3-D vector export', () => {
  it('projects lines onto the screen: one polyline per run of connected bonds of one colour', () => {
    const scene = new THREE.Scene()
    scene.add(buildLayerObject(geom(), { ...DEFAULT_STYLE, mode: 'line', lineWidth: 1, colorMode: 'custom', color: '#ff0000' }).object)
    const camera = view()
    const res = sceneToSvg(scene, camera, 100, 100)
    const paths = res.elements.filter((e) => e.tag === 'path')
    expect(paths.length).toBe(2) // t1 (3 spots) and t2 (2 spots): bonds never join across traces
    for (const l of paths) {
      expect(l.style.stroke).toBe('#ff0000')
      expect(l.style['stroke-width']).toBe('1')
      expect(l.style.fill).toBe('none')
    }
    const vertices = paths.map((l) => (l.geom.match(/[ML]/g) ?? []).length).sort()
    expect(vertices).toEqual([2, 3])
    // x=0 projects left of the centre; every spot has y=0 → the middle row
    const p = new THREE.Vector3(0, 0, 0).project(camera)
    const t1 = paths.find((l) => (l.geom.match(/L/g) ?? []).length === 2)!
    const [, x, y] = /M(-?[\d.]+) (-?[\d.]+)/.exec(t1.geom)!
    expect(+x).toBeCloseTo(((p.x + 1) / 2) * 100, 1)
    expect(+y).toBeCloseTo(50, 1)
  })

  it('tube data survives the view tagging its objects (userData merged, not replaced)', () => {
    const scene = new THREE.Scene()
    const built = buildLayerObject(geom(), { ...DEFAULT_STYLE, mode: 'tube', tubeRadius: 0.5 })
    Object.assign(built.object.userData, { layerId: 'L1', role: 'main' })
    scene.add(built.object)
    expect(sceneToSvg(scene, view(), 100, 100).elements.filter((e) => e.tag === 'line').length).toBe(3)
  })

  it('tubes: round-capped strokes as wide as the projected diameter; farther bonds first', () => {
    const scene = new THREE.Scene()
    const radius = 0.5
    const built = buildLayerObject(geom(), { ...DEFAULT_STYLE, mode: 'tube', tubeRadius: radius, colorMode: 'custom', color: '#00ff00' })
    scene.add(built.object)
    const camera = view()
    const res = sceneToSvg(scene, camera, 100, 100)
    const lines = res.elements.filter((e) => e.tag === 'line')
    expect(lines.length).toBe(3)
    expect(lines.every((l) => l.style['stroke-linecap'] === 'round')).toBe(true)
    // at depth 20, 1 world unit = (100/2) / (20 · tan 22.5°) px
    const px = 50 / (20 * Math.tan(THREE.MathUtils.degToRad(22.5)))
    for (const l of lines) expect(+l.style['stroke-width']).toBeCloseTo(2 * radius * px, 0)
    expect(res.notes.join(' ')).toMatch(/round-capped strokes/)
  })

  it('points are circles of the drawn size; hidden objects are skipped', () => {
    const scene = new THREE.Scene()
    const pts = buildLayerObject(geom(), { ...DEFAULT_STYLE, mode: 'points', pointSize: 6, pointScale: false })
    const hidden = buildLayerObject(geom(), { ...DEFAULT_STYLE, mode: 'line' })
    hidden.object.visible = false
    scene.add(pts.object, hidden.object)
    const res = sceneToSvg(scene, view(), 100, 100)
    // square points without a DOM sprite → rects of the point size
    expect(res.elements.length).toBe(5)
    for (const e of res.elements) expect(e.geom).toMatch(/width="6" height="6"|r="3"/)
  })

  it('paints far primitives before near ones', () => {
    const scene = new THREE.Scene()
    const near = new THREE.Points(new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute([5, 0, 5], 3)), new THREE.PointsMaterial({ size: 4, sizeAttenuation: false, color: 0x0000ff }))
    const far = new THREE.Points(new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute([5, 0, -5], 3)), new THREE.PointsMaterial({ size: 4, sizeAttenuation: false, color: 0xff0000 }))
    scene.add(near, far)
    const res = sceneToSvg(scene, view(), 100, 100)
    expect(res.elements.map((e) => e.style.fill)).toEqual(['#ff0000', '#0000ff'])
  })

  it('leaves out what is behind the camera', () => {
    const scene = new THREE.Scene()
    scene.add(new THREE.Points(new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute([5, 0, 30], 3)), new THREE.PointsMaterial({ size: 4, sizeAttenuation: false })))
    expect(sceneToSvg(scene, view(), 100, 100).elements.length).toBe(0)
  })
})

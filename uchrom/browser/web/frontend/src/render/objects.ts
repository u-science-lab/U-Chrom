import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js'
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'
import { vertexColors, type ColorOptions } from '../colors'
import type { Geometry, LayerStyle } from '../types'
import { autoTubeRadius, buildLineIndex, tubeAllowed } from './segments'

/**
 * How to map a raycast hit back to a point index of the layer geometry.
 * - 'vertex': hit.index is the point index (Points)
 * - 'indexed': hit.index is a position in the index buffer of an indexed
 *   LineSegments (three.js reports that, not the vertex); `index[i]` is the point
 * - 'pair': hit.faceIndex is a line-pair index into `pairIndex`
 * - 'tube': hit.face.a is a mesh vertex; `pointOfVertex` maps it to a point
 */
export type PickMap =
  | { kind: 'vertex' }
  | { kind: 'indexed'; index: Uint32Array }
  | { kind: 'pair'; pairIndex: Uint32Array }
  | { kind: 'tube'; pointOfVertex: Uint32Array }

export interface BuiltLayer {
  object: THREE.Object3D
  pick: PickMap
  /** set when the requested style could not be honoured */
  warning: string | null
  dispose(): void
  /** fat lines need the viewport size */
  setResolution(width: number, height: number): void
}

function applyOpacity(mat: THREE.Material, opacity: number) {
  mat.transparent = opacity < 1
  mat.opacity = opacity
  mat.depthWrite = opacity >= 1
}

export function buildLayerObject(geom: Geometry, style: LayerStyle, opts: ColorOptions = {}): BuiltLayer {
  const colors = vertexColors(geom, style.colorMode, style.color, opts)
  let mode = style.mode
  let warning: string | null = null
  if (mode === 'tube' && !tubeAllowed(geom.header, style.highQuality)) {
    mode = 'line'
    warning = `${geom.header.n_segments.toLocaleString('en-US')} polyline segments exceed the tube budget — drawing lines (select a cell to see tubes)`
  }
  if (mode === 'points') return buildPoints(geom, colors, style, warning)
  if (mode === 'tube') return buildTubes(geom, colors, style, warning)
  return buildLines(geom, colors, style, warning)
}

function buildPoints(geom: Geometry, colors: Float32Array, style: LayerStyle, warning: string | null): BuiltLayer {
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(geom.positions, 3))
  g.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  g.computeBoundingSphere()
  const mat = new THREE.PointsMaterial({ size: style.pointSize, sizeAttenuation: false, vertexColors: true })
  applyOpacity(mat, style.opacity)
  const obj = new THREE.Points(g, mat)
  return {
    object: obj,
    pick: { kind: 'vertex' },
    warning,
    dispose: () => {
      g.dispose()
      mat.dispose()
    },
    setResolution: () => {},
  }
}

/**
 * Lines cannot show a one-spot segment (e.g. an unassigned spot, or a spot
 * isolated by bond breaking), so line layers get a small Points child for
 * them.  `userData.singletons[i]` is the layer point index of marker i.
 */
function singletonMarkers(geom: Geometry, colors: Float32Array, opacity: number): THREE.Points | null {
  const { offsets, positions } = geom
  const idx: number[] = []
  for (let s = 0; s + 1 < offsets.length; s++) if (offsets[s + 1] - offsets[s] === 1) idx.push(offsets[s])
  if (!idx.length) return null
  const pos = new Float32Array(3 * idx.length)
  const col = new Float32Array(3 * idx.length)
  idx.forEach((pi, k) => {
    pos.set(positions.subarray(3 * pi, 3 * pi + 3), 3 * k)
    col.set(colors.subarray(3 * pi, 3 * pi + 3), 3 * k)
  })
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  g.setAttribute('color', new THREE.BufferAttribute(col, 3))
  g.computeBoundingSphere()
  const mat = new THREE.PointsMaterial({ size: 4, sizeAttenuation: false, vertexColors: true })
  applyOpacity(mat, opacity)
  const pts = new THREE.Points(g, mat)
  pts.userData.singletons = Uint32Array.from(idx)
  return pts
}

function withSingletons(built: BuiltLayer, geom: Geometry, colors: Float32Array, opacity: number): BuiltLayer {
  const pts = singletonMarkers(geom, colors, opacity)
  if (!pts) return built
  built.object.add(pts)
  const dispose = built.dispose
  return {
    ...built,
    dispose: () => {
      dispose()
      pts.geometry.dispose()
      ;(pts.material as THREE.Material).dispose()
    },
  }
}

function buildLines(geom: Geometry, colors: Float32Array, style: LayerStyle, warning: string | null): BuiltLayer {
  return withSingletons(buildLinesOnly(geom, colors, style, warning), geom, colors, style.opacity)
}

function buildLinesOnly(geom: Geometry, colors: Float32Array, style: LayerStyle, warning: string | null): BuiltLayer {
  const index = buildLineIndex(geom.offsets)
  if (style.lineWidth <= 1) {
    // One draw call; WebGL line width is always 1px.
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(geom.positions, 3))
    g.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    g.setIndex(new THREE.BufferAttribute(index, 1))
    g.computeBoundingSphere()
    const mat = new THREE.LineBasicMaterial({ vertexColors: true })
    applyOpacity(mat, style.opacity)
    return {
      object: new THREE.LineSegments(g, mat),
      pick: { kind: 'indexed', index },
      warning,
      dispose: () => {
        g.dispose()
        mat.dispose()
      },
      setResolution: () => {},
    }
  }
  // Wide lines: screen-space quads (LineSegments2), expanded per pair.
  const nPairs = index.length / 2
  const pos = new Float32Array(nPairs * 6)
  const col = new Float32Array(nPairs * 6)
  for (let p = 0; p < nPairs; p++) {
    for (let e = 0; e < 2; e++) {
      const v = index[2 * p + e]
      for (let c = 0; c < 3; c++) {
        pos[6 * p + 3 * e + c] = geom.positions[3 * v + c]
        col[6 * p + 3 * e + c] = colors[3 * v + c]
      }
    }
  }
  const g = new LineSegmentsGeometry()
  g.setPositions(pos)
  g.setColors(col)
  const mat = new LineMaterial({ linewidth: style.lineWidth, vertexColors: true, worldUnits: false })
  applyOpacity(mat, style.opacity)
  const obj = new LineSegments2(g, mat)
  return {
    object: obj,
    pick: { kind: 'pair', pairIndex: index },
    warning,
    dispose: () => {
      g.dispose()
      mat.dispose()
    },
    setResolution: (w, h) => mat.resolution.set(w, h),
  }
}

function buildTubes(geom: Geometry, colors: Float32Array, style: LayerStyle, warning: string | null): BuiltLayer {
  const radius = style.tubeRadius ?? autoTubeRadius(geom)
  const interp = style.highQuality ? 10 : 2
  const radial = style.highQuality ? 20 : 8
  const parts: THREE.BufferGeometry[] = []
  // mesh vertex → spot index, for picking (parts stay indexed, so mesh
  // vertices map 1:1 onto this array after merging)
  const vertexPoint: number[] = []
  const { offsets, positions } = geom
  for (let s = 0; s + 1 < offsets.length; s++) {
    const a = offsets[s]
    const b = offsets[s + 1]
    const n = b - a
    if (n < 2) {
      // Lone spot: a small sphere so it isn't lost.
      const sg = new THREE.SphereGeometry(radius * 1.5, radial, Math.max(4, radial / 2))
      sg.translate(positions[3 * a], positions[3 * a + 1], positions[3 * a + 2])
      const cnt = sg.attributes.position.count
      const c = new Float32Array(3 * cnt)
      for (let v = 0; v < cnt; v++) {
        c.set(colors.subarray(3 * a, 3 * a + 3), 3 * v)
        vertexPoint.push(a)
      }
      sg.setAttribute('color', new THREE.BufferAttribute(c, 3))
      parts.push(sg)
      continue
    }
    const pts: THREE.Vector3[] = []
    for (let i = a; i < b; i++) pts.push(new THREE.Vector3(positions[3 * i], positions[3 * i + 1], positions[3 * i + 2]))
    const curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal')
    const tubular = (n - 1) * interp
    const tg = new THREE.TubeGeometry(curve, tubular, radius, radial, false)
    // TubeGeometry vertices: (tubular+1) rings × (radial+1) vertices; colour
    // each ring by interpolating between the two spots it lies between.
    const cnt = tg.attributes.position.count
    const c = new Float32Array(3 * cnt)
    for (let ring = 0; ring <= tubular; ring++) {
      const u = (ring / tubular) * (n - 1)
      const i0 = Math.floor(u)
      const i1 = Math.min(n - 1, i0 + 1)
      const f = u - i0
      const p0 = a + i0
      const p1 = a + i1
      for (let r = 0; r <= radial; r++) {
        const v = ring * (radial + 1) + r
        for (let k = 0; k < 3; k++) c[3 * v + k] = colors[3 * p0 + k] * (1 - f) + colors[3 * p1 + k] * f
        vertexPoint.push(f < 0.5 ? p0 : p1)
      }
    }
    tg.setAttribute('color', new THREE.BufferAttribute(c, 3))
    parts.push(tg)
  }
  for (const p of parts) {
    for (const name of Object.keys(p.attributes)) if (!['position', 'normal', 'color'].includes(name)) p.deleteAttribute(name)
  }
  const merged = parts.length ? mergeGeometries(parts, false) : new THREE.BufferGeometry()
  parts.forEach((p) => p.dispose())
  merged.computeBoundingSphere()
  const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.55, metalness: 0.05 })
  applyOpacity(mat, style.opacity)
  return {
    object: new THREE.Mesh(merged, mat),
    pick: { kind: 'tube', pointOfVertex: Uint32Array.from(vertexPoint) },
    warning,
    dispose: () => {
      merged.dispose()
      mat.dispose()
    },
    setResolution: () => {},
  }
}

/** Point index for a raycast hit on a built layer, or -1. */
export function pointIndexOfHit(pick: PickMap, hit: THREE.Intersection): number {
  const single = hit.object.userData.singletons as Uint32Array | undefined
  if (single) return hit.index === undefined || hit.index === null ? -1 : single[hit.index]
  if (pick.kind === 'vertex') return hit.index ?? -1
  if (pick.kind === 'indexed') {
    const i = hit.index
    return i === undefined || i === null ? -1 : pick.index[i]
  }
  if (pick.kind === 'pair') {
    const f = hit.faceIndex
    return f === undefined || f === null ? -1 : pick.pairIndex[2 * f]
  }
  const a = hit.face?.a
  return a === undefined ? -1 : pick.pointOfVertex[a]
}

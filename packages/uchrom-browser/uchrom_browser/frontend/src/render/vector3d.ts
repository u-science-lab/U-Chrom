/**
 * Vector export of a 3-D view: the visible scene projected with its camera
 * into SVG primitives (painter's order, far to near).
 *
 * - lines (LineSegments, LineSegments2): runs of connected bonds of one
 *   colour (the mean of each bond's two spot colours) as one polyline, at
 *   the drawn width in px;
 * - tubes: the spot polyline (`userData.vector`, set by buildTubes) as
 *   round-capped strokes whose width is the tube's projected diameter at
 *   the bond's depth — an approximation: no lighting / shading, straight
 *   bonds instead of the Catmull-Rom curve;
 * - points (layers in point mode, one-spot markers, point sets): circles
 *   (squares for square points) of the drawn size.
 * Everything is painted far to near in one order (the screen's depth test);
 * objects drawn on top (subset layers, the pick highlight) come last.
 * Objects that are not visible (thinned copies, hidden layers, the hover
 * box) are skipped.
 */

import * as THREE from 'three'
import { hexColor, linearToSrgb, num, type SvgEl } from '../svg'

/** Tube source data kept on the tube mesh for the vector export. */
export interface TubeVectorData {
  kind: 'tube'
  positions: Float32Array
  offsets: Uint32Array | number[]
  /** linear-light vertex colours, 3 per spot */
  colors: Float32Array
  radius: number
}

interface Prim {
  order: number
  depth: number
  el: SvgEl
}

/** Bonds per polyline at most: longer runs could not be placed in depth order among other primitives. */
const RUN_BONDS = 12

/** Above this many primitives the export is refused (an SVG nobody can open). */
export const MAX_PRIMITIVES = 2_000_000

export interface Vector3dResult {
  elements: SvgEl[]
  primitives: number
  /** notes for the user (tube approximation, …) */
  notes: string[]
}

function visibleInScene(o: THREE.Object3D): boolean {
  for (let x: THREE.Object3D | null = o; x; x = x.parent) if (!x.visible) return false
  return true
}

function materialOf(o: THREE.Object3D): THREE.Material | null {
  const m = (o as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined
  return Array.isArray(m) ? m[0] ?? null : m ?? null
}

function opacityOf(m: THREE.Material | null): number {
  return m && m.transparent ? m.opacity : 1
}

const op = (v: number) => String(Math.round(v * 1000) / 1000)

/**
 * Project the scene seen by `camera` onto a `width` × `height` CSS-pixel
 * viewport and return SVG elements, far to near.
 */
export function sceneToSvg(scene: THREE.Scene, camera: THREE.PerspectiveCamera, width: number, height: number): Vector3dResult {
  scene.updateMatrixWorld(true)
  camera.updateMatrixWorld(true)
  const notes = new Set<string>()
  const prims: Prim[] = []
  const vp = new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse)
  const pxPerUnitAt = (w: number) => height / 2 / (w * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)))
  const margin = 50

  scene.traverse((o) => {
    if (prims.length > MAX_PRIMITIVES) return
    if (!visibleInScene(o)) return
    const mat = materialOf(o)
    if (!mat) return
    const order = o.renderOrder
    const m = new THREE.Matrix4().multiplyMatrices(vp, o.matrixWorld).elements
    // clip-space projection of a local point: screen x, y and w (= view depth)
    const proj = (x: number, y: number, z: number): [number, number, number] | null => {
      const cw = m[3] * x + m[7] * y + m[11] * z + m[15]
      if (cw <= 1e-9) return null
      const cz = (m[2] * x + m[6] * y + m[10] * z + m[14]) / cw
      if (cz < -1 || cz > 1) return null
      const sx = ((m[0] * x + m[4] * y + m[8] * z + m[12]) / cw + 1) * 0.5 * width
      const sy = (1 - (m[1] * x + m[5] * y + m[9] * z + m[13]) / cw) * 0.5 * height
      return [sx, sy, cw]
    }
    const inView = (x: number, y: number, r = 0) => x > -margin - r && x < width + margin + r && y > -margin - r && y < height + margin + r
    const base = (mat as THREE.MeshBasicMaterial).color ?? new THREE.Color(1, 1, 1)
    const alpha = opacityOf(mat)
    const colorAt = (attr: THREE.BufferAttribute | THREE.InterleavedBufferAttribute | undefined, i: number, j = -1): string => {
      let r = base.r, g = base.g, b = base.b
      if (attr && mat.vertexColors) {
        r *= j < 0 ? attr.getX(i) : (attr.getX(i) + attr.getX(j)) / 2
        g *= j < 0 ? attr.getY(i) : (attr.getY(i) + attr.getY(j)) / 2
        b *= j < 0 ? attr.getZ(i) : (attr.getZ(i) + attr.getZ(j)) / 2
      }
      return hexColor(linearToSrgb(r), linearToSrgb(g), linearToSrgb(b))
    }
    const line = (a: [number, number, number], b: [number, number, number], color: string, w: number, round: boolean) => {
      if (!inView(a[0], a[1], w) && !inView(b[0], b[1], w)) return
      const style: Record<string, string> = { stroke: color, 'stroke-width': num(w) }
      if (alpha < 1) style['stroke-opacity'] = op(alpha)
      if (round) style['stroke-linecap'] = 'round'
      prims.push({ order, depth: (a[2] + b[2]) / 2, el: { tag: 'line', geom: `x1="${num(a[0])}" y1="${num(a[1])}" x2="${num(b[0])}" y2="${num(b[1])}"`, style } })
    }
    const dot = (p: [number, number, number], r: number, color: string, square: boolean, rim: number) => {
      if (!inView(p[0], p[1], r)) return
      const style: Record<string, string> = { fill: color }
      if (alpha < 1) style['fill-opacity'] = op(alpha)
      if (rim > 0) Object.assign(style, { stroke: '#000000', 'stroke-opacity': op(0.65 * alpha), 'stroke-width': num(rim) })
      const geom = square ? `x="${num(p[0] - r)}" y="${num(p[1] - r)}" width="${num(2 * r)}" height="${num(2 * r)}"` : `cx="${num(p[0])}" cy="${num(p[1])}" r="${num(r)}"`
      prims.push({ order, depth: p[2], el: { tag: square ? 'rect' : 'circle', geom, style } })
    }

    // thin lines: runs of connected bonds of one colour → one polyline (bond j starts where bond i ended)
    let run: { color: string; w: number; pts: [number, number][]; depth: number; n: number; end: number } | null = null
    const flush = () => {
      if (run && run.pts.length > 1 && run.pts.some(([x, y]) => inView(x, y, run!.w))) {
        const style: Record<string, string> = { fill: 'none', stroke: run.color, 'stroke-width': num(run.w) }
        if (alpha < 1) style['stroke-opacity'] = op(alpha)
        if (run.w > 1) Object.assign(style, { 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })
        const d = run.pts.map(([x, y], k) => `${k ? 'L' : 'M'}${num(x)} ${num(y)}`).join('')
        prims.push({ order, depth: run.depth / run.n, el: { tag: 'path', geom: `d="${d}"`, style } })
      }
      run = null
    }
    const bond = (i: number, j: number, a: [number, number, number] | null, b: [number, number, number] | null, color: string, w: number) => {
      if (!a || !b) return flush()
      // short runs, so lines interleave with tubes and points in depth order
      if (!run || run.end !== i || run.color !== color || run.w !== w || run.n >= RUN_BONDS) {
        flush()
        run = { color, w, pts: [[a[0], a[1]]], depth: 0, n: 0, end: -1 }
      }
      run.pts.push([b[0], b[1]])
      run.depth += (a[2] + b[2]) / 2
      run.n++
      run.end = j
    }

    const vec = o.userData.vector as TubeVectorData | { kind: 'sphere' } | undefined
    if (vec?.kind === 'tube') {
      notes.add('Tubes are exported as round-capped strokes of the projected tube diameter (no lighting, straight bonds).')
      const { positions: P, offsets, colors: C, radius } = vec
      const cattr = new THREE.BufferAttribute(C, 3)
      const pt = (i: number) => proj(P[3 * i], P[3 * i + 1], P[3 * i + 2])
      for (let s = 0; s + 1 < offsets.length; s++) {
        const a = offsets[s]
        const b = offsets[s + 1]
        if (b - a === 1) {
          const p = pt(a)
          if (p) dot(p, 1.5 * radius * pxPerUnitAt(p[2]), colorAt(cattr, a), false, 0)
          continue
        }
        let prev = pt(a)
        for (let i = a + 1; i < b; i++) {
          const cur = pt(i)
          if (prev && cur) line(prev, cur, colorAt(cattr, i - 1, i), 2 * radius * pxPerUnitAt((prev[2] + cur[2]) / 2), true)
          prev = cur
        }
      }
      return
    }
    if (vec?.kind === 'sphere') {
      const mesh = o as THREE.Mesh
      mesh.geometry.computeBoundingSphere()
      const r = (mesh.geometry.boundingSphere?.radius ?? 1) * new THREE.Vector3().setFromMatrixScale(o.matrixWorld).x
      const p = proj(0, 0, 0)
      if (p) dot(p, r * pxPerUnitAt(p[2]), colorAt(undefined, 0), false, 0)
      return
    }
    const geom = (o as THREE.Mesh).geometry as THREE.BufferGeometry | undefined
    if (!geom) return
    const color = geom.getAttribute('color') as THREE.BufferAttribute | undefined

    if ((o as THREE.Points).isPoints) {
      const pm = mat as THREE.PointsMaterial
      const pos = geom.getAttribute('position')
      if (!pos) return
      const square = !pm.map
      const rim = o.userData.vectorRim ? Math.max(0.5, (pm.size * 5) / 64) : 0
      for (let i = 0; i < pos.count; i++) {
        const p = proj(pos.getX(i), pos.getY(i), pos.getZ(i))
        if (!p) continue
        // attenuated sizes are world-scaled: three draws size · (height / 2) / depth px
        const d = pm.sizeAttenuation ? (pm.size * height) / 2 / p[2] : pm.size
        dot(p, d / 2, colorAt(color, i), square, rim)
      }
      return
    }
    // LineSegments2 (wide lines): instanced start / end attributes
    const start = geom.getAttribute('instanceStart') as THREE.InterleavedBufferAttribute | undefined
    const end = geom.getAttribute('instanceEnd') as THREE.InterleavedBufferAttribute | undefined
    if (start && end) {
      const cs = geom.getAttribute('instanceColorStart') as THREE.InterleavedBufferAttribute | undefined
      const ce = geom.getAttribute('instanceColorEnd') as THREE.InterleavedBufferAttribute | undefined
      const w = (mat as unknown as { linewidth: number }).linewidth ?? 1
      const n = Math.min((geom as THREE.InstancedBufferGeometry).instanceCount ?? start.count, start.count)
      for (let i = 0; i < n; i++) {
        const a = proj(start.getX(i), start.getY(i), start.getZ(i))
        const b = proj(end.getX(i), end.getY(i), end.getZ(i))
        // bond i continues bond i-1 when it starts where that one ended
        const joined = i > 0 && start.getX(i) === end.getX(i - 1) && start.getY(i) === end.getY(i - 1) && start.getZ(i) === end.getZ(i - 1)
        let c: string
        if (cs && ce && mat.vertexColors) {
          const r = (cs.getX(i) + ce.getX(i)) / 2, g = (cs.getY(i) + ce.getY(i)) / 2, bl = (cs.getZ(i) + ce.getZ(i)) / 2
          c = hexColor(linearToSrgb(base.r * r), linearToSrgb(base.g * g), linearToSrgb(base.b * bl))
        } else c = colorAt(undefined, 0)
        bond(joined ? i - 1 : -1, i, a, b, c, w)
      }
      flush()
      return
    }
    if ((o as THREE.LineSegments).isLineSegments) {
      const pos = geom.getAttribute('position')
      if (!pos) return
      const idx = geom.getIndex()
      const n = idx ? idx.count : pos.count
      for (let k = 0; k + 1 < n; k += 2) {
        const i = idx ? idx.getX(k) : k
        const j = idx ? idx.getX(k + 1) : k + 1
        const a = proj(pos.getX(i), pos.getY(i), pos.getZ(i))
        const b = proj(pos.getX(j), pos.getY(j), pos.getZ(j))
        bond(i, j, a, b, colorAt(color, i, j), 1)
      }
      flush()
    }
    // other meshes (lit tubes without vector data, helpers) are not exported
  })
  if (prims.length > MAX_PRIMITIVES)
    throw new Error(`${prims.length.toLocaleString('en-US')}+ primitives: too many for a vector file — focus a cell or a region (a subset), or save a PNG`)
  // painter's order, far → near.  On screen the depth test decides what covers what (the faint
  // context lines are drawn after the opaque layers but stay hidden behind them), so the scene
  // is one depth order; only objects drawn on top (subset layers, the pick highlight: render
  // order > 0) come after it.
  const layer = (p: Prim) => Math.max(0, p.order)
  const order = prims.map((_, i) => i)
  order.sort((a, b) => layer(prims[a]) - layer(prims[b]) || prims[b].depth - prims[a].depth || a - b)
  return { elements: order.map((i) => prims[i].el), primitives: prims.length, notes: [...notes] }
}

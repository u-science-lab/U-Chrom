import * as THREE from 'three'
import { labelColorMap } from '../colors'
import type { PointSet } from '../types'

export interface PointSplit {
  /** indices drawn at full opacity (focused cell, or everything in the overview) */
  main: Uint32Array
  /** indices drawn faint (other cells while one is focused) */
  context: Uint32Array
}

/**
 * Which points of a set to draw, and how.  Points with a hidden label or a
 * non-finite position are dropped; with a focused cell its points are
 * `main` and every other point is `context`.
 */
export function splitPoints(ps: PointSet, hiddenLabels: ReadonlySet<string>, focusCell: string | null): PointSplit {
  const main: number[] = []
  const context: number[] = []
  const p = ps.positions
  for (let i = 0; i < ps.n; i++) {
    if (hiddenLabels.has(ps.labels[i])) continue
    if (!Number.isFinite(p[3 * i]) || !Number.isFinite(p[3 * i + 1]) || !Number.isFinite(p[3 * i + 2])) continue
    if (focusCell === null || ps.cellIds[i] === focusCell) main.push(i)
    else context.push(i)
  }
  return { main: Uint32Array.from(main), context: Uint32Array.from(context) }
}

/** Label counts of a point set, sorted by count (desc) then label. */
export function labelCounts(ps: PointSet): { value: string; count: number }[] {
  const m = new Map<string, number>()
  for (const l of ps.labels) m.set(l, (m.get(l) ?? 0) + 1)
  return [...m].map(([value, count]) => ({ value, count })).sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
}

let disc: THREE.Texture | null = null
/** Round sprite for point markers (created once, needs a DOM canvas). */
function discTexture(): THREE.Texture {
  if (disc) return disc
  const c = document.createElement('canvas')
  c.width = c.height = 64
  const g = c.getContext('2d')!
  g.beginPath()
  g.arc(32, 32, 28, 0, Math.PI * 2)
  g.fillStyle = '#ffffff'
  g.fill()
  g.lineWidth = 5
  g.strokeStyle = 'rgba(0,0,0,0.65)'
  g.stroke()
  disc = new THREE.CanvasTexture(c)
  return disc
}

export interface BuiltPoints {
  object: THREE.Points
  /** point-set index of each drawn vertex */
  indices: Uint32Array
  dispose(): void
}

/** Screen-space round markers coloured by label. */
export function buildPointMarkers(ps: PointSet, indices: Uint32Array, sizePx: number, opacity: number): BuiltPoints {
  const pos = new Float32Array(3 * indices.length)
  const col = new Float32Array(3 * indices.length)
  const colorOf = labelColorMap(labelCounts(ps).map((l) => l.value))
  const cache = new Map<string, [number, number, number]>()
  indices.forEach((src, k) => {
    pos.set(ps.positions.subarray(3 * src, 3 * src + 3), 3 * k)
    const label = ps.labels[src]
    let c = cache.get(label)
    if (!c) cache.set(label, (c = colorOf(label)))
    col.set(c, 3 * k)
  })
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  g.setAttribute('color', new THREE.BufferAttribute(col, 3))
  g.computeBoundingSphere()
  const mat = new THREE.PointsMaterial({
    size: sizePx,
    sizeAttenuation: false,
    vertexColors: true,
    map: discTexture(),
    alphaTest: 0.5,
    transparent: opacity < 1,
    opacity,
    depthWrite: opacity >= 1,
  })
  const object = new THREE.Points(g, mat)
  object.renderOrder = 1 // after chromatin
  return {
    object,
    indices,
    dispose: () => {
      g.dispose()
      mat.dispose()
    },
  }
}

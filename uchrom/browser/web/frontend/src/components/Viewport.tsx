import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { TrackballControls } from 'three/examples/jsm/controls/TrackballControls.js'
import { buildLayerObject, pointIndexOfHit, type BuiltLayer } from '../render/objects'
import { displayParts, subsetGeometry } from '../render/partition'
import { buildPointMarkers, splitPoints, type BuiltPoints } from '../render/points'
import { bboxDiagonal, findSegment } from '../render/segments'
import { DEFAULT_STYLE } from '../layers'
import { activeFieldValues, activeView, useStore } from '../store'
import { fieldRange } from '../colors'
import { isPointPick, type ColorMode, type Geometry, type LayerStyle, type PointSet, type SegmentInfo } from '../types'
import { ColorBar } from './ColorBar'
import { FocusBar } from './FocusBar'
import { PickLabel } from './PickLabel'

type Role = 'main' | 'context'

interface Part {
  role: Role
  built: BuiltLayer
  geometry: Geometry
}

interface Entry {
  /** inputs the parts were built from; rebuilt when any changes */
  key: { geometry: Geometry; style: LayerStyle; focus: string | null; hidden: string; ctx: number; overview: ColorMode; nCells: number; values: Map<string, number | null> | null }
  parts: Part[]
}

interface Fly {
  from: { pos: THREE.Vector3; target: THREE.Vector3 }
  to: { pos: THREE.Vector3; target: THREE.Vector3 }
  t0: number
}

interface Three {
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  controls: TrackballControls
  group: THREE.Group
  entries: Map<string, Entry>
  highlight: THREE.Mesh
  hoverBox: THREE.Box3Helper
  /** white overlay of the hovered cell's traces (drawn on top) */
  hover: { cell: string; geometry: Geometry; built: BuiltLayer } | null
  /** point-set markers: one main and one faint (context) object per set */
  points: Map<string, { set: PointSet; key: string; parts: { role: Role; built: BuiltPoints }[] }>
  fly: Fly | null
}

const FLY_MS = 450

function unionBox(geoms: (Geometry | null)[]): THREE.Box3 | null {
  const box = new THREE.Box3()
  let any = false
  for (const g of geoms) {
    if (!g || g.header.n_points === 0) continue
    box.expandByPoint(new THREE.Vector3(...g.header.bbox.min))
    box.expandByPoint(new THREE.Vector3(...g.header.bbox.max))
    any = true
  }
  return any ? box : null
}

/** Camera pose that frames `box`, keeping the current viewing direction. */
function framing(t: Three, box: THREE.Box3) {
  const center = box.getCenter(new THREE.Vector3())
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 1e-6)
  const dist = (radius / Math.sin(THREE.MathUtils.degToRad(t.camera.fov / 2))) * 1.1
  const dir = t.camera.position.clone().sub(t.controls.target)
  if (dir.lengthSq() < 1e-12) dir.set(0, 0, 1)
  dir.normalize()
  return { target: center, pos: center.clone().add(dir.multiplyScalar(dist)), dist }
}

function setClip(t: Three, dist: number) {
  t.camera.near = Math.max(dist / 1000, 1e-6)
  t.camera.far = dist * 100
  t.camera.updateProjectionMatrix()
}

function jumpTo(t: Three, box: THREE.Box3) {
  const f = framing(t, box)
  t.fly = null
  setClip(t, f.dist)
  t.camera.position.copy(f.pos)
  t.controls.target.copy(f.target)
  t.controls.update()
}

function flyTo(t: Three, box: THREE.Box3) {
  const f = framing(t, box)
  // far plane must cover the start and the end of the flight
  t.camera.far = Math.max(t.camera.far, f.dist * 100)
  t.camera.near = Math.min(t.camera.near, Math.max(f.dist / 1000, 1e-6))
  t.camera.updateProjectionMatrix()
  t.fly = {
    from: { pos: t.camera.position.clone(), target: t.controls.target.clone() },
    to: { pos: f.pos, target: f.target },
    t0: performance.now(),
  }
}

const hiddenKey = (h: string[]) => [...h].sort().join('\u0000')

/** Geometry parts currently drawn for the active dataset. */
function drawnGeometries(t: Three): Geometry[] {
  const out: Geometry[] = []
  for (const e of t.entries.values()) for (const p of e.parts) out.push(p.geometry)
  return out
}

export function Viewport() {
  const hostRef = useRef<HTMLDivElement>(null)
  const tipRef = useRef<HTMLDivElement>(null)
  const threeRef = useRef<Three | null>(null)
  const fittedRef = useRef(false)
  const layers = useStore((s) => s.layers)
  const activeDatasetId = useStore((s) => s.activeDatasetId)
  const view = useStore(activeView)
  const resetViewToken = useStore((s) => s.resetViewToken)
  const flyToken = useStore((s) => s.flyToken)
  const cells = useStore((s) => s.cells)
  const fieldValues = useStore(activeFieldValues)
  const pointSets = useStore((s) => (s.activeDatasetId ? s.pointSets[s.activeDatasetId] : undefined))
  const setPick = useStore((s) => s.setPick)
  const setStatus = useStore((s) => s.setStatus)

  // One-time renderer / scene setup.
  useEffect(() => {
    const host = hostRef.current!
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setClearColor(new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue('--viewport-bg').trim() || '#1b1d21'))
    host.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1e6)
    camera.position.set(0, 0, 10)
    scene.add(camera)
    scene.add(new THREE.AmbientLight(0xffffff, 0.55))
    const key = new THREE.DirectionalLight(0xffffff, 1.6)
    key.position.set(1, 1.5, 2)
    camera.add(key) // headlight: lighting follows the view
    const group = new THREE.Group()
    scene.add(group)
    const highlight = new THREE.Mesh(
      new THREE.SphereGeometry(1, 16, 12),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.85, depthTest: false }),
    )
    highlight.visible = false
    highlight.renderOrder = 999
    scene.add(highlight)

    const hoverBox = new THREE.Box3Helper(new THREE.Box3(), new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#5c9ded'))
    hoverBox.visible = false
    scene.add(hoverBox)

    const controls = new TrackballControls(camera, renderer.domElement)
    controls.rotateSpeed = 3
    controls.zoomSpeed = 3 // ~7.5% per wheel notch
    controls.panSpeed = 0.8
    controls.staticMoving = true

    const t: Three = { renderer, scene, camera, controls, group, entries: new Map(), highlight, hoverBox, hover: null, points: new Map(), fly: null }
    threeRef.current = t

    const resize = () => {
      const w = host.clientWidth
      const h = host.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      controls.handleResize()
      for (const e of t.entries.values()) for (const p of e.parts) p.built.setResolution(w, h)
    }
    const ro = new ResizeObserver(resize)
    ro.observe(host)
    resize()

    let raf = 0
    const loop = () => {
      if (t.fly) {
        const u = Math.min(1, (performance.now() - t.fly.t0) / FLY_MS)
        const e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2 // easeInOutCubic
        camera.position.lerpVectors(t.fly.from.pos, t.fly.to.pos, e)
        controls.target.lerpVectors(t.fly.from.target, t.fly.to.target, e)
        if (u >= 1) {
          setClip(t, t.fly.to.pos.distanceTo(t.fly.to.target))
          t.fly = null
        }
      }
      controls.update()
      renderer.render(scene, camera)
      raf = requestAnimationFrame(loop)
    }
    loop()

    // Click (not drag) → pick / focus.
    let down: { x: number; y: number } | null = null
    const onDown = (e: PointerEvent) => {
      down = { x: e.clientX, y: e.clientY }
      t.fly = null // user takes over the camera
    }
    const onUp = (e: PointerEvent) => {
      if (!down || e.button !== 0) return
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y)
      down = null
      if (moved > 5) return
      pickAt(t, e)
      hideHover()
    }
    // Hover: at most one raycast per frame, none while dragging.
    const tip = tipRef.current!
    let hoverEvt: PointerEvent | null = null
    let hoverRaf = 0
    const hideHover = () => {
      setHoverCell(t, null)
      hoverBox.visible = false
      tip.style.display = 'none'
      renderer.domElement.style.cursor = ''
    }
    const onMove = (e: PointerEvent) => {
      if (e.buttons) return hideHover()
      hoverEvt = e
      if (!hoverRaf)
        hoverRaf = requestAnimationFrame(() => {
          hoverRaf = 0
          if (hoverEvt) hoverAt(t, hoverEvt, tip)
        })
    }
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      const st = useStore.getState()
      if (e.key === 'Escape') {
        if (st.pick) st.setPick(null)
        else st.focusCell(null)
      } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        st.stepCell(1)
        e.preventDefault()
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        st.stepCell(-1)
        e.preventDefault()
      }
    }
    renderer.domElement.addEventListener('pointerdown', onDown)
    renderer.domElement.addEventListener('pointerup', onUp)
    renderer.domElement.addEventListener('pointermove', onMove)
    renderer.domElement.addEventListener('pointerleave', hideHover)
    window.addEventListener('keydown', onKey)

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onDown)
      renderer.domElement.removeEventListener('pointerup', onUp)
      renderer.domElement.removeEventListener('pointermove', onMove)
      renderer.domElement.removeEventListener('pointerleave', hideHover)
      cancelAnimationFrame(hoverRaf)
      window.removeEventListener('keydown', onKey)
      for (const e of t.entries.values()) for (const p of e.parts) p.built.dispose()
      for (const e of t.points.values()) for (const p of e.parts) p.built.dispose()
      controls.dispose()
      renderer.dispose()
      host.removeChild(renderer.domElement)
      threeRef.current = null
    }
  }, [])

  // Sync scene objects with layers + view state (only the active dataset).
  useEffect(() => {
    const t = threeRef.current
    if (!t) return
    const shown = layers.filter((l) => l.datasetId === activeDatasetId && l.visible && l.geometry)
    const keep = new Set(shown.map((l) => l.id))
    const drop = (id: string, e: Entry) => {
      for (const p of e.parts) {
        t.group.remove(p.built.object)
        p.built.dispose()
      }
      t.entries.delete(id)
    }
    for (const [id, e] of t.entries) if (!keep.has(id)) drop(id, e)

    const hidden = new Set(view.hiddenChroms)
    const cellList = (activeDatasetId && cells[activeDatasetId]) || []
    const cellIndex = new Map(cellList.map((c, i) => [c.cell_id, i]))
    const warnings: string[] = []
    const w = t.renderer.domElement.clientWidth
    const h = t.renderer.domElement.clientHeight
    for (const l of shown) {
      const key = {
        geometry: l.geometry!,
        style: l.style,
        focus: view.focusCell,
        hidden: hiddenKey(view.hiddenChroms),
        ctx: view.contextOpacity,
        overview: view.overviewColor,
        nCells: cellList.length,
        values: view.overviewColor === 'field' ? fieldValues : null,
      }
      const prev = t.entries.get(l.id)
      if (
        prev &&
        prev.key.geometry === key.geometry &&
        prev.key.style === key.style &&
        prev.key.focus === key.focus &&
        prev.key.hidden === key.hidden &&
        prev.key.ctx === key.ctx &&
        prev.key.overview === key.overview &&
        prev.key.nCells === key.nCells &&
        prev.key.values === key.values
      ) {
        for (const p of prev.parts) if (p.built.warning) warnings.push(`${l.name}: ${p.built.warning}`)
        continue
      }
      if (prev) drop(l.id, prev)
      const { main, context } = displayParts(l.geometry!, hidden, view.focusCell)
      // colour by chromosome whenever the layer itself has several, so hiding
      // chromosomes never switches the colour scheme away from the legend
      const colorOpts = {
        chromColors: new Set(l.geometry!.header.segments.map((s) => s.chrom)).size > 1,
        cellIndex,
        cellValues: key.values ?? undefined,
        fieldRange: key.values ? fieldRange(key.values.values()) : undefined,
      }
      // Multi-cell data: the overview (and the faint context around a
      // focused cell) uses the overview colouring — per cell by default.
      const overviewStyle: LayerStyle = cellIndex.size > 1 ? { ...l.style, colorMode: view.overviewColor } : l.style
      const mainStyle = view.focusCell === null ? overviewStyle : l.style
      const parts: Part[] = []
      if (main) parts.push({ role: 'main', geometry: main, built: buildLayerObject(main, mainStyle, colorOpts) })
      if (context && view.contextOpacity > 0) {
        const ctxStyle: LayerStyle = { ...overviewStyle, mode: 'line', lineWidth: 1, opacity: view.contextOpacity }
        parts.push({ role: 'context', geometry: context, built: buildLayerObject(context, ctxStyle, colorOpts) })
      }
      for (const p of parts) {
        p.built.object.userData = { layerId: l.id, role: p.role }
        p.built.setResolution(w, h)
        if (p.role === 'context') p.built.object.renderOrder = -1
        t.group.add(p.built.object)
        if (p.role === 'main' && p.built.warning) warnings.push(`${l.name}: ${p.built.warning}`)
      }
      t.entries.set(l.id, { key, parts })
    }
    setStatus(warnings.length ? warnings.join(' · ') : null)

    if (!fittedRef.current) {
      const box = unionBox(drawnGeometries(t))
      if (box) {
        jumpTo(t, box)
        fittedRef.current = true
      }
    }
    const pick = useStore.getState().pick
    if (pick && !isPointPick(pick) && !keep.has(pick.layerId)) setPick(null)
  }, [layers, activeDatasetId, view, cells, fieldValues, setPick, setStatus])

  // Point sets (e.g. RNA spots): focused cell's points full, others faint.
  useEffect(() => {
    const t = threeRef.current
    if (!t) return
    const sets = pointSets ?? {}
    const hiddenSets = new Set(view.hiddenPointSets)
    for (const [name, e] of t.points) {
      if (sets[name] && !hiddenSets.has(name)) continue
      for (const p of e.parts) {
        t.group.remove(p.built.object)
        p.built.dispose()
      }
      t.points.delete(name)
    }
    for (const ps of Object.values(sets)) {
      if (hiddenSets.has(ps.name)) continue
      const hiddenLabels = view.hiddenLabels[ps.name] ?? []
      const key = [view.focusCell, view.contextOpacity, view.pointSize, [...hiddenLabels].sort().join('\u0000')].join('|')
      const prev = t.points.get(ps.name)
      if (prev && prev.set === ps && prev.key === key) continue
      if (prev)
        for (const p of prev.parts) {
          t.group.remove(p.built.object)
          p.built.dispose()
        }
      const split = splitPoints(ps, new Set(hiddenLabels), view.focusCell)
      const parts: { role: Role; built: BuiltPoints }[] = []
      // all-cells overview: half-size markers so the chromatin stays visible
      const overview = view.focusCell === null
      if (split.main.length)
        parts.push({
          role: 'main',
          built: buildPointMarkers(ps, split.main, overview ? Math.max(2, view.pointSize * 0.5) : view.pointSize, overview ? 0.85 : 1),
        })
      if (split.context.length && view.contextOpacity > 0)
        parts.push({ role: 'context', built: buildPointMarkers(ps, split.context, Math.max(2, view.pointSize * 0.6), view.contextOpacity) })
      for (const p of parts) {
        p.built.object.userData = { kind: 'points', set: ps.name, role: p.role }
        t.group.add(p.built.object)
      }
      t.points.set(ps.name, { set: ps, key, parts })
    }
  }, [pointSets, view])

  // Explicit reset / dataset switch → refit on everything drawn.
  useEffect(() => {
    fittedRef.current = false
    const t = threeRef.current
    if (!t) return
    const box = unionBox(drawnGeometries(t))
    if (box) {
      jumpTo(t, box)
      fittedRef.current = true
    }
  }, [resetViewToken, activeDatasetId])

  // Focus change → fly to the focused cell (or back to everything).
  useEffect(() => {
    const t = threeRef.current
    if (!t || flyToken === 0) return
    const mains: Geometry[] = []
    for (const e of t.entries.values()) for (const p of e.parts) if (p.role === 'main') mains.push(p.geometry)
    const box = unionBox(view.focusCell ? mains : drawnGeometries(t))
    if (box) flyTo(t, box)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyToken])

  // Highlight the picked spot.
  const pick = useStore((s) => s.pick)
  useEffect(() => {
    const t = threeRef.current
    if (!t) return
    t.highlight.visible = false
    if (!pick) return
    if (isPointPick(pick)) {
      t.highlight.position.set(...pick.position)
      t.highlight.scale.setScalar(Math.max(t.camera.position.distanceTo(t.controls.target) * 0.01, 1e-6))
      t.highlight.visible = true
      return
    }
    const main = t.entries.get(pick.layerId)?.parts.find((p) => p.role === 'main')
    if (!main) return
    const p = main.geometry.positions
    const i = pick.pointIndex
    t.highlight.position.set(p[3 * i], p[3 * i + 1], p[3 * i + 2])
    t.highlight.scale.setScalar(Math.max(bboxDiagonal(main.geometry.header.bbox) * 0.006, 1e-6))
    t.highlight.visible = true
  }, [pick])

  return (
    <div className="viewport" ref={hostRef}>
      <FocusBar />
      <ColorBar />
      <PickLabel />
      <div className="hover-tip" ref={tipRef} />
      <div className="viewport-tools">
        <button onClick={() => useStore.getState().resetView()} title="Fit everything drawn">
          Reset view
        </button>
      </div>
    </div>
  )
}

interface TraceHit {
  kind: 'trace'
  layerId: string
  role: Role
  part: Part
  pointIndex: number
  segment: SegmentInfo
  cell: string | null
}

interface PointHit {
  kind: 'point'
  set: PointSet
  role: Role
  index: number
  cell: string | null
}

type Hit = TraceHit | PointHit

/**
 * What is under the cursor: among raycast hits within a few pixels — traces
 * and point markers alike — the one closest to the cursor *on screen*
 * (distance to the ray / depth), not the one closest to the camera, which in
 * a crowded field is often a neighbouring cell.  The focused cell wins over
 * its faint context, and a point marker over a trace at the same spot.
 */
function hitAt(t: Three, clientX: number, clientY: number): Hit | null {
  const rect = t.renderer.domElement.getBoundingClientRect()
  const ndc = new THREE.Vector2(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1)
  const ray = new THREE.Raycaster()
  // a fraction of the camera distance ≈ a few pixels on screen, at any unit
  const threshold = t.camera.position.distanceTo(t.controls.target) * 0.006
  ray.params.Line = { threshold }
  ray.params.Points = { threshold }
  ray.setFromCamera(ndc, t.camera)
  let best: Hit | null = null
  let bestScore = Infinity
  for (const h of ray.intersectObjects(t.group.children, false)) {
    const ud = h.object.userData as { kind?: string; layerId?: string; set?: string; role: Role }
    const off = (h as { distanceToRay?: number }).distanceToRay ?? ray.ray.distanceToPoint(h.point)
    let score = off / Math.max(h.distance, 1e-9) + (ud.role === 'context' ? 1 : 0)
    let hit: Hit | null = null
    if (ud.kind === 'points') {
      const e = t.points.get(ud.set!)
      const part = e?.parts.find((p) => p.role === ud.role)
      if (!e || !part || h.index === undefined || h.index === null) continue
      const index = part.built.indices[h.index]
      hit = { kind: 'point', set: e.set, role: ud.role, index, cell: e.set.cellIds[index] }
      score -= 1e-4 // markers sit on the chromatin: prefer them on ties
    } else {
      const part = t.entries.get(ud.layerId!)?.parts.find((p) => p.role === ud.role)
      if (!part) continue
      const pi = pointIndexOfHit(part.built.pick, h)
      if (pi < 0) continue
      const si = findSegment(part.geometry.offsets, pi)
      if (si < 0) continue
      const segment = part.geometry.header.segments[si]
      hit = { kind: 'trace', layerId: ud.layerId!, role: ud.role, part, pointIndex: pi, segment, cell: segment.cell_id }
    }
    if (score < bestScore) {
      bestScore = score
      best = hit
    }
  }
  return best
}

const hasManyCells = (store: ReturnType<typeof useStore.getState>) =>
  ((store.activeDatasetId && store.cells[store.activeDatasetId]) || []).length > 1

/**
 * Click behaviour: anything belonging to another cell (context, or the
 * overview of a multi-cell dataset) focuses that cell; a trace or point of
 * the focused cell — or of data without cells — shows its details.
 */
function pickAt(t: Three, e: PointerEvent) {
  const store = useStore.getState()
  const view = activeView(store)
  const hit = hitAt(t, e.clientX, e.clientY)
  if (!hit) {
    store.setPick(null)
    return
  }
  if (hasManyCells(store) && hit.cell !== null && hit.cell !== view.focusCell) {
    store.focusCell(hit.cell)
    return
  }
  const rect = t.renderer.domElement.getBoundingClientRect()
  const screen = { x: e.clientX - rect.left, y: e.clientY - rect.top }
  if (hit.kind === 'point') {
    const ps = hit.set
    const values: Record<string, number | null> = {}
    for (const [k, arr] of Object.entries(ps.values)) values[k] = arr[hit.index] ?? null
    const p = ps.positions
    store.setPick({
      kind: 'point',
      set: ps.name,
      index: hit.index,
      label: ps.labels[hit.index],
      cellId: hit.cell,
      position: [p[3 * hit.index], p[3 * hit.index + 1], p[3 * hit.index + 2]],
      values,
      screen,
    })
    return
  }
  store.setPick({
    kind: 'trace',
    layerId: hit.layerId,
    pointIndex: hit.pointIndex,
    segment: hit.segment,
    binStart: hit.part.geometry.starts[hit.pointIndex],
    screen,
  })
}

/** Per-cell bounding boxes of a geometry (cached; geometries are immutable). */
const cellBoxCache = new WeakMap<Geometry, Map<string, THREE.Box3>>()
function cellBoxes(g: Geometry): Map<string, THREE.Box3> {
  let boxes = cellBoxCache.get(g)
  if (boxes) return boxes
  boxes = new Map()
  const v = new THREE.Vector3()
  g.header.segments.forEach((seg, s) => {
    if (seg.cell_id === null) return
    let b = boxes!.get(seg.cell_id)
    if (!b) boxes!.set(seg.cell_id, (b = new THREE.Box3()))
    for (let i = g.offsets[s]; i < g.offsets[s + 1]; i++) b.expandByPoint(v.fromArray(g.positions, 3 * i))
  })
  cellBoxCache.set(g, boxes)
  return boxes
}

/**
 * Hover feedback for multi-cell data: outline the cell under the cursor and
 * say what a click will do.  Updates the DOM directly (no React renders).
 */
function hoverAt(t: Three, e: PointerEvent, tip: HTMLDivElement) {
  const store = useStore.getState()
  const view = activeView(store)
  const hit = hitAt(t, e.clientX, e.clientY)
  const rect = t.renderer.domElement.getBoundingClientRect()
  const showTip = (text: string) => {
    tip.textContent = text
    tip.style.left = `${e.clientX - rect.left + 14}px`
    tip.style.top = `${e.clientY - rect.top + 14}px`
    tip.style.display = 'block'
  }
  const clear = () => {
    setHoverCell(t, null)
    t.hoverBox.visible = false
    tip.style.display = 'none'
    t.renderer.domElement.style.cursor = ''
  }
  const cell = hit?.cell ?? null
  const otherCell = hasManyCells(store) && cell !== null && cell !== view.focusCell
  const pointText = hit?.kind === 'point' ? `${hit.set.labels[hit.index]}${cell !== null ? ` · cell ${cell}` : ''}` : null
  if (!hit || !otherCell) {
    clear()
    if (pointText) showTip(pointText) // a marker of the focused cell (or cell-less data)
    return
  }
  // anything of another cell: outline that cell and say a click focuses it
  const layerGeom = store.layers.find((l) => l.datasetId === store.activeDatasetId && l.visible && l.geometry)?.geometry
  const traceGeom = hit.kind === 'trace' ? store.layers.find((l) => l.id === hit.layerId)?.geometry : layerGeom
  if (traceGeom) setHoverCell(t, cell!, traceGeom, new Set(view.hiddenChroms))
  const box = traceGeom ? cellBoxes(traceGeom).get(cell!) : undefined
  if (box) {
    t.hoverBox.box.copy(box)
    t.hoverBox.visible = true
  }
  const info = (store.activeDatasetId ? store.cells[store.activeDatasetId] : undefined)?.find((c) => c.cell_id === cell)
  showTip(`${pointText ? `${pointText} — ` : `cell ${cell}${info ? ` · ${info.n_traces} traces` : ''} — `}click to focus`)
  t.renderer.domElement.style.cursor = 'pointer'
}

/** Swap the hover overlay to `cell` (built once per hovered cell). */
function setHoverCell(t: Three, cell: string | null, layerGeom?: Geometry, hidden?: ReadonlySet<string>) {
  if (t.hover && t.hover.cell === cell && t.hover.geometry === layerGeom) return
  if (t.hover) {
    t.scene.remove(t.hover.built.object)
    t.hover.built.dispose()
    t.hover = null
  }
  if (cell === null || !layerGeom) return
  const g = subsetGeometry(layerGeom, (s) => s.cell_id === cell && !hidden?.has(s.chrom))
  if (!g.header.n_points) return
  const built = buildLayerObject(g, { ...DEFAULT_STYLE, mode: 'line', colorMode: 'custom', color: '#ffffff', lineWidth: 2.5, opacity: 1 })
  const el = t.renderer.domElement
  built.setResolution(el.clientWidth, el.clientHeight)
  built.object.renderOrder = 998
  built.object.traverse((o) => {
    const m = (o as THREE.Mesh).material as THREE.Material | undefined
    if (m) m.depthTest = false
  })
  t.scene.add(built.object)
  t.hover = { cell, geometry: layerGeom, built }
}

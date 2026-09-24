import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { TrackballControls } from 'three/examples/jsm/controls/TrackballControls.js'
import { buildLayerObject, pointIndexOfHit, type BuiltLayer } from '../render/objects'
import { displayParts } from '../render/partition'
import { bboxDiagonal, findSegment } from '../render/segments'
import { activeView, useStore } from '../store'
import type { ColorMode, Geometry, LayerStyle } from '../types'
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
  key: { geometry: Geometry; style: LayerStyle; focus: string | null; hidden: string; ctx: number; overview: ColorMode; nCells: number }
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
  const threeRef = useRef<Three | null>(null)
  const fittedRef = useRef(false)
  const layers = useStore((s) => s.layers)
  const activeDatasetId = useStore((s) => s.activeDatasetId)
  const view = useStore(activeView)
  const resetViewToken = useStore((s) => s.resetViewToken)
  const flyToken = useStore((s) => s.flyToken)
  const cells = useStore((s) => s.cells)
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

    const controls = new TrackballControls(camera, renderer.domElement)
    controls.rotateSpeed = 3
    controls.zoomSpeed = 3 // ~7.5% per wheel notch
    controls.panSpeed = 0.8
    controls.staticMoving = true

    const t: Three = { renderer, scene, camera, controls, group, entries: new Map(), highlight, fly: null }
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
    window.addEventListener('keydown', onKey)

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onDown)
      renderer.domElement.removeEventListener('pointerup', onUp)
      window.removeEventListener('keydown', onKey)
      for (const e of t.entries.values()) for (const p of e.parts) p.built.dispose()
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
        prev.key.nCells === key.nCells
      ) {
        for (const p of prev.parts) if (p.built.warning) warnings.push(`${l.name}: ${p.built.warning}`)
        continue
      }
      if (prev) drop(l.id, prev)
      const { main, context } = displayParts(l.geometry!, hidden, view.focusCell)
      // colour by chromosome whenever the layer itself has several, so hiding
      // chromosomes never switches the colour scheme away from the legend
      const colorOpts = { chromColors: new Set(l.geometry!.header.segments.map((s) => s.chrom)).size > 1, cellIndex }
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
    if (pick && !keep.has(pick.layerId)) setPick(null)
  }, [layers, activeDatasetId, view, cells, setPick, setStatus])

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
      <PickLabel />
      <div className="viewport-tools">
        <button onClick={() => useStore.getState().resetView()} title="Fit everything drawn">
          Reset view
        </button>
      </div>
    </div>
  )
}

/**
 * Click behaviour: a trace of another cell (context, or the overview of a
 * multi-cell dataset) focuses that cell; a trace of the focused cell — or of
 * data without cells — shows its details.
 */
function pickAt(t: Three, e: PointerEvent) {
  const rect = t.renderer.domElement.getBoundingClientRect()
  const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1)
  const ray = new THREE.Raycaster()
  // a fraction of the camera distance ≈ a few pixels on screen, at any unit
  const threshold = t.camera.position.distanceTo(t.controls.target) * 0.006
  ray.params.Line = { threshold }
  ray.params.Points = { threshold }
  ray.setFromCamera(ndc, t.camera)
  const hits = ray.intersectObjects(t.group.children, false)
  const store = useStore.getState()
  const view = activeView(store)
  const hasCells = ((store.activeDatasetId && store.cells[store.activeDatasetId]) || []).length > 1
  // Prefer the focused cell when both it and its context are under the cursor.
  hits.sort((a, b) => Number(a.object.userData.role === 'context') - Number(b.object.userData.role === 'context') || a.distance - b.distance)
  for (const hit of hits) {
    const { layerId, role } = hit.object.userData as { layerId: string; role: Role }
    const part = t.entries.get(layerId)?.parts.find((p) => p.role === role)
    if (!part) continue
    const pi = pointIndexOfHit(part.built.pick, hit)
    if (pi < 0) continue
    const s = findSegment(part.geometry.offsets, pi)
    if (s < 0) continue
    const segment = part.geometry.header.segments[s]
    if (hasCells && segment.cell_id !== null && segment.cell_id !== view.focusCell) {
      store.focusCell(segment.cell_id)
      return
    }
    store.setPick({
      layerId,
      pointIndex: pi,
      segment,
      binStart: part.geometry.starts[pi],
      screen: { x: e.clientX - rect.left, y: e.clientY - rect.top },
    })
    return
  }
  store.setPick(null)
}

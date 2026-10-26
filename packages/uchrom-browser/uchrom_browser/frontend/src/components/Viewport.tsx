import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { TrackballControls } from 'three/examples/jsm/controls/TrackballControls.js'
import { buildLayerObject, pointIndexOfHit, type BuiltLayer } from '../render/objects'
import { splitForView } from '../render/bonds'
import { explodeGeometry, explodeOffsets } from '../render/explode'
import { displayParts, subsetGeometry, thinGeometry, type FocusSet } from '../render/partition'
import { buildPointMarkers, splitPoints, type BuiltPoints } from '../render/points'
import { raycastChunks } from '../render/raypick'
import { autoTubeRadius, bboxDiagonal, findSegment } from '../render/segments'
import { DEFAULT_STYLE } from '../layers'
import { mark } from '../perf'
import { activeView, useStore } from '../store'
import { useFieldColors, type FieldColors } from '../useFieldColors'
import { usePaneScope, useScopeCells } from '../useGroups'
import type { ScopeSpec } from '../groups'
import { isPointPick, type ColorMode, type Geometry, type Layer, type LayerStyle, type PointSet, type SegmentInfo } from '../types'
import { registerRenderHook, registerVectorHook } from '../capture'
import { sceneToSvg } from '../render/vector3d'
import { palette } from '../theme'
import { effectiveStyle, layerShownIn } from '../workspace'
import { useTheme } from '../useTheme'
import { PickLabel } from './PickLabel'

type Role = 'main' | 'context'

interface Part {
  role: Role
  built: BuiltLayer
  geometry: Geometry
  /** large parts: a thinned copy drawn while the camera moves */
  lod?: { built: BuiltLayer; geometry: Geometry }
}

interface Entry {
  /** inputs the parts were built from; rebuilt when any changes */
  key: { geometry: Geometry; style: string; focus: FocusSet; hidden: string; ctx: number; overview: ColorMode; nCells: number; values: FieldColors | null; maxBond: 'auto' | number | null; theme: string; trace: string | null; explode: number; root: Geometry | null }
  parts: Part[]
  /** the layer's geometry as drawn: long bonds cut, chromosomes separated (all cells and chromosomes) */
  placed: Geometry
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
  /** the scene changed: draw it on the next frame (frames are drawn on demand) */
  dirty: boolean
  /** last camera motion (ms): the thinned copies are shown until it has been still for LOD_IDLE_MS */
  lastMotion: number
  /** thinned copies and pixel ratio 1 in use */
  moving: boolean
  /** the axis key's SVG (bottom-left), redrawn with each frame */
  axisKey: SVGSVGElement | null
}

const FLY_MS = 450
/** Points of the thinned copy of a large part (drawn while the camera moves). */
const LOD_POINTS = 300_000
/** Stillness (ms) after which the full geometry is drawn again. */
const LOD_IDLE_MS = 220

/** Show the thinned copies (and draw at pixel ratio 1) while moving; the full scene when still. */
function setMoving(t: Three, moving: boolean) {
  if (t.moving === moving) return
  t.moving = moving
  let any = false
  for (const e of t.entries.values())
    for (const p of e.parts) {
      if (!p.lod) continue
      any = true
      p.built.object.visible = !moving
      p.lod.built.object.visible = moving
    }
  const ratio = moving && any ? 1 : window.devicePixelRatio
  if (t.renderer.getPixelRatio() !== ratio) t.renderer.setPixelRatio(ratio)
  t.dirty = true
}

/** Draw after the other layers and win depth ties with coincident geometry (subset layers). */
function highlightOnTop(o: THREE.Object3D) {
  o.renderOrder = 1
  o.traverse((x) => {
    const m = (x as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined
    for (const mat of Array.isArray(m) ? m : m ? [m] : []) {
      mat.polygonOffset = true
      mat.polygonOffsetFactor = -2
      mat.polygonOffsetUnits = -2
      mat.depthFunc = THREE.LessEqualDepth
    }
  })
}

/** World axes as seen from the camera: arrows from one origin, named at their tips. */
function drawAxisKey(t: Three) {
  const svg = t.axisKey
  if (!svg) return
  const inv = t.camera.quaternion.clone().invert()
  const L = 22
  const c = 30
  const axes = (['x', 'y', 'z'] as const).map((name, i) => {
    const v = new THREE.Vector3(i === 0 ? 1 : 0, i === 1 ? 1 : 0, i === 2 ? 1 : 0).applyQuaternion(inv)
    return { name, x: c + v.x * L, y: c - v.y * L, depth: v.z }
  })
  // farther axes first (drawn under, fainter)
  axes.sort((a, b) => a.depth - b.depth)
  svg.innerHTML = axes
    .map((a) => {
      const op = a.depth < -0.2 ? 0.45 : 1
      const dx = a.x - c
      const dy = a.y - c
      const len = Math.hypot(dx, dy) || 1
      const lx = c + (dx / len) * (Math.hypot(dx, dy) + 8)
      const ly = c + (dy / len) * (Math.hypot(dx, dy) + 8)
      return `<g opacity="${op}"><line x1="${c}" y1="${c}" x2="${a.x.toFixed(1)}" y2="${a.y.toFixed(1)}" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="${a.x.toFixed(1)}" cy="${a.y.toFixed(1)}" r="1.6" fill="currentColor"/><text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle" dominant-baseline="central">${a.name}</text></g>`
    })
    .join('')
}

function unionBox(geoms: (Geometry | null)[]): THREE.Box3 | null {
  const box = new THREE.Box3()
  let any = false
  for (const g of geoms) {
    const bb = g?.header.bbox
    if (!g || g.header.n_points === 0 || !bb) continue
    box.expandByPoint(new THREE.Vector3(...bb.min))
    box.expandByPoint(new THREE.Vector3(...bb.max))
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

/** The geometry of a layer's root (the dataset layer its subsets were cut from). */
function rootGeometry(layers: Layer[], l: Layer): Geometry | null {
  let cur: Layer | undefined = l
  for (let k = 0; cur && cur.parentId !== null && k < 64; k++) cur = layers.find((x) => x.id === cur!.parentId)
  return cur?.geometry ?? l.geometry ?? null
}

/** Geometry of the fully drawn (focused / pinned) parts. */
function mainGeometries(t: Three): Geometry[] {
  const out: Geometry[] = []
  for (const e of t.entries.values()) for (const p of e.parts) if (p.role === 'main') out.push(p.geometry)
  return out
}

/** Geometry parts currently drawn for the active dataset. */
function drawnGeometries(t: Three): Geometry[] {
  const out: Geometry[] = []
  for (const e of t.entries.values()) for (const p of e.parts) out.push(p.geometry)
  return out
}

/**
 * 3-D view of the active dataset — one instance per workspace pane.  Several
 * 3-D panes share the store (layers, focus, colours) but each has its own
 * renderer and camera.  `resetKey` refits this pane only.  `pinned`: draw
 * only that cell (no context), ignoring the global focus.  `scope`: the
 * pane's cells setting — all cells in full, one pinned cell alone, a group
 * in full with the others as grey context, or follow the focus (default).
 */
export function Viewport({ paneId = 'P1', resetKey = 0, scope: spec }: { paneId?: string; resetKey?: number; scope?: ScopeSpec }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const paneRef = useRef(paneId)
  paneRef.current = paneId
  const tipRef = useRef<HTMLDivElement>(null)
  const axisKeyRef = useRef<SVGSVGElement>(null)
  const threeRef = useRef<Three | null>(null)
  const fittedRef = useRef(false)
  const layers = useStore((s) => s.layers)
  const activeDatasetId = useStore((s) => s.activeDatasetId)
  const view = useStore(activeView)
  const resetViewToken = useStore((s) => s.resetViewToken)
  const flyToken = useStore((s) => s.flyToken)
  const cells = useStore((s) => s.cells)
  const fieldColors = useFieldColors()
  const pal = useTheme()
  const pointSets = useStore((s) => (s.activeDatasetId ? s.pointSets[s.activeDatasetId] : undefined))
  const setPick = useStore((s) => s.setPick)
  const setStatus = useStore((s) => s.setStatus)
  // this view's own style changes (each 3-D view is styled on its own)
  const paneStyles = useStore((s) => s.workspace.panes.find((p) => p.id === paneId)?.layerStyles)
  // layers drawn here: shared ones and this view's subsets, minus what this view hides
  const paneHidden = useStore((s) => s.workspace.panes.find((p) => p.id === paneId)?.hiddenLayers)
  // a trace view: only this trace
  const paneTrace = useStore((s) => s.workspace.panes.find((p) => p.id === paneId)?.trace ?? null)
  // separated chromosomes (0 = the structure as it is)
  const paneExplode = useStore((s) => s.workspace.panes.find((p) => p.id === paneId)?.explode ?? 0)
  // drawn in full here: the pane's group, its pinned cell, else the global
  // focus (a cell or a group)
  const scope = usePaneScope({ scope: spec })
  const pinned = spec?.kind === 'cell' ? spec.cell : null
  // fixed settings (all / cell / group) don't follow focus changes
  const fixed = spec && spec.kind !== 'focus' ? JSON.stringify(spec) : null
  const scopeCells = useScopeCells(scope)
  const focus: FocusSet = scope.kind === 'all' ? null : scope.kind === 'cell' ? scope.cell : scopeCells
  const ctxOpacity = pinned ? 0 : view.contextOpacity
  // clicking a trace of another cell focuses it; within a single focused cell it picks
  const focusRef = useRef<string | null>(null)
  focusRef.current = scope.kind === 'cell' ? scope.cell : null
  const noCoords = useStore((s) => {
    const d = s.datasets.find((x) => x.id === s.activeDatasetId)
    return !!d && (d.has_coords === false || d.n_spots === 0)
  })

  // One-time renderer / scene setup.
  useEffect(() => {
    const host = hostRef.current!
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setClearColor(new THREE.Color(palette().viewportBg))
    host.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1e6)
    camera.position.set(0, 0, 10)
    scene.add(camera)
    // Lighting that follows the view, so no side of a tube stays dark: a soft sky/ground fill
    // from everywhere, a key light from just above-right of the camera and a weaker fill from
    // below-left — both aimed along the view (their targets ride with the camera too; a
    // target left at the world origin made the light swing as the camera orbited).
    scene.add(new THREE.HemisphereLight(0xffffff, 0x9aa0a8, 1.1))
    scene.add(new THREE.AmbientLight(0xffffff, 0.35))
    const aim = new THREE.Object3D()
    aim.position.set(0, 0, -1)
    camera.add(aim)
    const key = new THREE.DirectionalLight(0xffffff, 1.3)
    key.position.set(0.45, 0.6, 1)
    key.target = aim
    camera.add(key)
    const fill = new THREE.DirectionalLight(0xffffff, 0.55)
    fill.position.set(-0.7, -0.5, 0.6)
    fill.target = aim
    camera.add(fill)
    const group = new THREE.Group()
    scene.add(group)
    const highlight = new THREE.Mesh(
      new THREE.SphereGeometry(1, 16, 12),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(palette().strong), transparent: true, opacity: 0.85, depthTest: false }),
    )
    highlight.visible = false
    highlight.renderOrder = 999
    highlight.userData.vector = { kind: 'sphere' }
    scene.add(highlight)

    const hoverBox = new THREE.Box3Helper(new THREE.Box3(), new THREE.Color(palette().accent))
    hoverBox.visible = false
    scene.add(hoverBox)

    const controls = new TrackballControls(camera, renderer.domElement)
    controls.rotateSpeed = 3
    controls.zoomSpeed = 3 // ~7.5% per wheel notch
    controls.panSpeed = 0.8
    controls.staticMoving = true

    const t: Three = {
      renderer, scene, camera, controls, group, entries: new Map(), highlight, hoverBox, hover: null, points: new Map(), fly: null,
      dirty: true, lastMotion: 0, moving: false, axisKey: axisKeyRef.current,
    }
    threeRef.current = t
    // camera moved (drag, wheel, programmatic): draw, thinned until it has been still
    controls.addEventListener('change', () => {
      t.lastMotion = performance.now()
      t.dirty = true
    })

    const resize = () => {
      const w = host.clientWidth
      const h = host.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      controls.handleResize()
      for (const e of t.entries.values()) for (const p of e.parts) (p.built.setResolution(w, h), p.lod?.built.setResolution(w, h))
      t.dirty = true
    }
    const ro = new ResizeObserver(resize)
    ro.observe(host)
    resize()

    // Frames on demand: the loop keeps the controls going but draws only when something
    // changed (several 3-D panes of millions of points would otherwise redraw every frame).
    let raf = 0
    const loop = () => {
      const now = performance.now()
      if (t.fly) {
        t.lastMotion = now
        t.dirty = true
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
      setMoving(t, now - t.lastMotion < LOD_IDLE_MS)
      if (t.dirty) {
        t.dirty = false
        renderer.render(scene, camera)
        drawAxisKey(t)
      }
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
      pickAt(t, e, paneRef.current, focusRef.current)
      hideHover()
    }
    // Hover: at most one raycast per frame, none while dragging.
    const tip = tipRef.current!
    let hoverEvt: PointerEvent | null = null
    let hoverRaf = 0
    const hideHover = () => {
      setHoverCell(t, null)
      if (hoverBox.visible) t.dirty = true
      hoverBox.visible = false
      tip.style.display = 'none'
      renderer.domElement.style.cursor = ''
    }
    const onMove = (e: PointerEvent) => {
      if (e.buttons) return hideHover()
      // no hit-testing while the camera moves (wheel, fly)
      if (t.moving) return
      hoverEvt = e
      if (!hoverRaf)
        hoverRaf = requestAnimationFrame(() => {
          hoverRaf = 0
          if (hoverEvt) hoverAt(t, hoverEvt, tip, focusRef.current)
        })
    }
    renderer.domElement.addEventListener('pointerdown', onDown)
    renderer.domElement.addEventListener('pointerup', onUp)
    renderer.domElement.addEventListener('pointermove', onMove)
    renderer.domElement.addEventListener('pointerleave', hideHover)

    // "Save image": draw the current view now (the loop may be paused)
    registerRenderHook(paneRef.current, () => {
      controls.update()
      renderer.render(scene, camera)
      t.dirty = true
    })
    // "Save image" as SVG / PDF: the scene projected with this camera (full geometry, not the thinned copies)
    registerVectorHook(paneRef.current, {
      canvas: renderer.domElement,
      build: (w, h) => {
        controls.update()
        setMoving(t, false)
        return sceneToSvg(scene, camera, w, h)
      },
    })

    return () => {
      registerRenderHook(paneRef.current, null)
      registerVectorHook(paneRef.current, null)
      cancelAnimationFrame(raf)
      ro.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onDown)
      renderer.domElement.removeEventListener('pointerup', onUp)
      renderer.domElement.removeEventListener('pointermove', onMove)
      renderer.domElement.removeEventListener('pointerleave', hideHover)
      cancelAnimationFrame(hoverRaf)
      for (const e of t.entries.values()) for (const p of e.parts) (p.built.dispose(), p.lod?.built.dispose())
      for (const e of t.points.values()) for (const p of e.parts) p.built.dispose()
      controls.dispose()
      renderer.dispose()
      host.removeChild(renderer.domElement)
      threeRef.current = null
    }
  }, [])

  // Theme switch: background, highlight and hover-box colours (lines re-colour via the sync below).
  useEffect(() => {
    const t = threeRef.current
    if (!t) return
    t.renderer.setClearColor(new THREE.Color(pal.viewportBg))
    ;(t.highlight.material as THREE.MeshBasicMaterial).color.set(pal.strong)
    ;(t.hoverBox.material as THREE.LineBasicMaterial).color.set(pal.accent)
    t.dirty = true
  }, [pal])

  // A new pin / group → fit the camera to it once it is drawn.
  useEffect(() => {
    fittedRef.current = false
  }, [fixed])

  // Sync scene objects with layers + view state (only the active dataset).
  useEffect(() => {
    const t = threeRef.current
    if (!t) return
    const shown = layers.filter((l) => l.datasetId === activeDatasetId && l.geometry && layerShownIn(l, { id: paneId, hiddenLayers: paneHidden }))
    const keep = new Set(shown.map((l) => l.id))
    const drop = (id: string, e: Entry) => {
      for (const p of e.parts) {
        t.group.remove(p.built.object)
        p.built.dispose()
        if (p.lod) {
          t.group.remove(p.lod.built.object)
          p.lod.built.dispose()
        }
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
    const newGeometry: number[] = []
    for (const l of shown) {
      let style = effectiveStyle(l, { layerStyles: paneStyles })
      const key = {
        geometry: l.geometry!,
        style: JSON.stringify(style),
        focus,
        hidden: hiddenKey(view.hiddenChroms),
        ctx: ctxOpacity,
        overview: view.overviewColor,
        nCells: cellList.length,
        values: view.overviewColor === 'field' ? fieldColors : null,
        maxBond: view.maxBond,
        theme: pal.name,
        trace: paneTrace,
        explode: paneExplode,
        // separation directions come from the dataset's whole geometry (a subset moves with it)
        root: paneExplode > 0 ? rootGeometry(layers, l) : null,
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
        prev.key.values === key.values &&
        prev.key.maxBond === key.maxBond &&
        prev.key.theme === key.theme &&
        prev.key.trace === key.trace &&
        prev.key.explode === key.explode &&
        prev.key.root === key.root
      ) {
        for (const p of prev.parts) if (p.built.warning) warnings.push(`${l.name}: ${p.built.warning}`)
        continue
      }
      if (prev) drop(l.id, prev)
      if (!prev || prev.key.geometry !== key.geometry) newGeometry.push(l.geometry!.header.n_points)
      // cut over-long bonds (unassigned spots, duplicate loci) before drawing
      const cut = splitForView(l.geometry!, view.maxBond).geometry
      const placed = key.root ? explodeGeometry(cut, explodeOffsets(key.root), paneExplode) : cut
      const base = paneTrace ? subsetGeometry(placed, (s) => s.trace_id === paneTrace) : placed
      const { main, context } = displayParts(base, hidden, focus)
      // a subset layer (a region / traces) is a highlight: its own style everywhere, and no
      // faint context of its own (its parent draws that)
      const isSubset = l.parentId !== null
      // …and its tubes a little thicker than the parent's, so they show around them
      if (isSubset && style.mode === 'tube' && style.tubeRadius === null) {
        const parentGeom = layers.find((x) => x.id === l.parentId)?.geometry
        if (parentGeom) style = { ...style, tubeRadius: autoTubeRadius(parentGeom) * 1.2 }
      }
      // colour by chromosome whenever the layer itself has several, so hiding
      // chromosomes never switches the colour scheme away from the legend
      const colorOpts = {
        chromColors: new Set(l.geometry!.header.segments.map((s) => s.chrom)).size > 1,
        cellIndex,
        cellValues: key.values?.cellValues,
        fieldRange: key.values?.fieldRange,
        fieldLog: key.values?.fieldLog,
        categories: key.values?.categories,
      }
      // Multi-cell data: the overview (and the faint context around a
      // focused cell) uses the overview colouring — per cell by default.
      // (a trace view shows one cell's trace: its own style, not the overview colouring)
      const overviewStyle: LayerStyle = cellIndex.size > 1 && !isSubset && !paneTrace ? { ...style, colorMode: view.overviewColor } : style
      // one cell: the layer style (tubes); a group reads like a small overview
      const mainStyle = typeof focus === 'string' ? style : overviewStyle
      const parts: Part[] = []
      // large line / point parts also get a thinned copy (tubes are built for one cell)
      const withLod = (geometry: Geometry, style: LayerStyle): Part['lod'] => {
        if (style.mode === 'tube') return undefined
        const thin = thinGeometry(geometry, LOD_POINTS)
        return thin ? { built: buildLayerObject(thin.geometry, style, colorOpts), geometry: thin.geometry } : undefined
      }
      if (main) parts.push({ role: 'main', geometry: main, built: buildLayerObject(main, mainStyle, colorOpts), lod: withLod(main, mainStyle) })
      if (context && ctxOpacity > 0 && !isSubset) {
        // around a group, members share colours with the rest: grey context keeps them apart
        // (thousands of overlapping faint lines saturate otherwise)
        const groupCtx = focus !== null && typeof focus !== 'string'
        const ctxStyle: LayerStyle = groupCtx
          ? { ...overviewStyle, mode: 'line', lineWidth: 1, opacity: ctxOpacity, colorMode: 'custom', color: pal.context }
          : { ...overviewStyle, mode: 'line', lineWidth: 1, opacity: ctxOpacity }
        parts.push({ role: 'context', geometry: context, built: buildLayerObject(context, ctxStyle, colorOpts), lod: withLod(context, ctxStyle) })
      }
      for (const p of parts) {
        // merged: the builders keep vector-export data there (render/vector3d.ts)
        Object.assign(p.built.object.userData, { layerId: l.id, role: p.role })
        p.built.setResolution(w, h)
        if (p.role === 'context') p.built.object.renderOrder = -1
        // a subset lies exactly on its parent: draw it last and let it win the depth ties
        if (isSubset) for (const o of [p.built.object, p.lod?.built.object]) if (o) highlightOnTop(o)
        t.group.add(p.built.object)
        if (p.lod) {
          const o = p.lod.built.object
          Object.assign(o.userData, { layerId: l.id, role: p.role })
          p.lod.built.setResolution(w, h)
          if (p.role === 'context') o.renderOrder = -1
          o.visible = t.moving
          p.built.object.visible = !t.moving
          t.group.add(o)
        }
        if (p.role === 'main' && p.built.warning) warnings.push(`${l.name}: ${p.built.warning}`)
      }
      t.entries.set(l.id, { key, parts, placed })
    }
    setStatus(warnings.length ? warnings.join(' · ') : null)
    // the render loop's callback for this frame was queued first, so this runs after the frame is drawn
    if (newGeometry.length) requestAnimationFrame(() => mark('geometry-drawn', { points: newGeometry }))

    if (!fittedRef.current) {
      const box = unionBox(fixed && focus !== null ? mainGeometries(t) : drawnGeometries(t))
      if (box) {
        jumpTo(t, box)
        fittedRef.current = true
      }
    }
    const pick = useStore.getState().pick
    if (pick && !isPointPick(pick) && !keep.has(pick.layerId)) setPick(null)
    t.dirty = true
  }, [layers, activeDatasetId, view, cells, fieldColors, setPick, setStatus, focus, ctxOpacity, fixed, pal, paneStyles, paneTrace, paneHidden, paneExplode])

  // Point sets (e.g. RNA spots): focused cell's points full, others faint.
  useEffect(() => {
    const t = threeRef.current
    if (!t) return
    // point sets have no chromosome to move with: hidden while chromosomes are separated
    const sets = paneExplode > 0 ? {} : (pointSets ?? {})
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
      const key = [typeof focus === 'string' || focus === null ? focus : `set:${[...focus].join(',')}`, ctxOpacity, view.pointSize, [...hiddenLabels].sort().join('\u0000')].join('|')
      const prev = t.points.get(ps.name)
      if (prev && prev.set === ps && prev.key === key) continue
      if (prev)
        for (const p of prev.parts) {
          t.group.remove(p.built.object)
          p.built.dispose()
        }
      const split = splitPoints(ps, new Set(hiddenLabels), focus)
      const parts: { role: Role; built: BuiltPoints }[] = []
      // all-cells overview: half-size markers so the chromatin stays visible
      const overview = typeof focus !== 'string'
      if (split.main.length)
        parts.push({
          role: 'main',
          built: buildPointMarkers(ps, split.main, overview ? Math.max(2, view.pointSize * 0.5) : view.pointSize, overview ? 0.85 : 1),
        })
      if (split.context.length && ctxOpacity > 0)
        parts.push({ role: 'context', built: buildPointMarkers(ps, split.context, Math.max(2, view.pointSize * 0.6), ctxOpacity) })
      for (const p of parts) {
        Object.assign(p.built.object.userData, { kind: 'points', set: ps.name, role: p.role })
        t.group.add(p.built.object)
      }
      t.points.set(ps.name, { set: ps, key, parts })
    }
    t.dirty = true
  }, [pointSets, view, focus, ctxOpacity, paneExplode])

  // Separation changed → once the slider rests, fly to what is drawn (it grows / shrinks).
  const explodeRef = useRef(paneExplode)
  useEffect(() => {
    if (explodeRef.current === paneExplode) return
    explodeRef.current = paneExplode
    const timer = setTimeout(() => {
      const t = threeRef.current
      if (!t) return
      const box = unionBox(hasFocusRef.current ? mainGeometries(t) : drawnGeometries(t))
      if (box) flyTo(t, box)
    }, 250)
    return () => clearTimeout(timer)
  }, [paneExplode])

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
    t.dirty = true
  }, [resetViewToken, activeDatasetId, resetKey])

  // Global focus changes don't move a pinned / group-scoped view.
  const pinnedRef = useRef(fixed)
  pinnedRef.current = fixed
  const hasFocusRef = useRef(false)
  hasFocusRef.current = focus !== null

  // Focus change → fly to the focused cell (or back to everything).
  useEffect(() => {
    const t = threeRef.current
    if (!t || flyToken === 0 || pinnedRef.current) return
    const box = unionBox(hasFocusRef.current ? mainGeometries(t) : drawnGeometries(t))
    if (box) flyTo(t, box)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyToken])

  // Highlight the picked spot.
  const pick = useStore((s) => s.pick)
  useEffect(() => {
    const t = threeRef.current
    if (!t) return
    t.dirty = true
    t.highlight.visible = false
    if (!pick || (pick.paneId && pick.paneId !== paneId)) return
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
  }, [pick, paneId])

  return (
    <div className="viewport" ref={hostRef}>
      {noCoords && <div className="muted pane-empty">No 3-D coordinates in this dataset — use Matrix / Tracks / Embedding views</div>}
      <PickLabel paneId={paneId} />
      <div className="hover-tip" ref={tipRef} />
      {!noCoords && <svg ref={axisKeyRef} className="axis-key-3d" width={60} height={60} viewBox="0 0 60 60" aria-hidden />}
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
  const consider = (hit: Hit, score: number) => {
    if (score < bestScore) {
      bestScore = score
      best = hit
    }
  }
  // Line parts (up to millions of points): chunked boxes → only the bonds near the ray
  // (render/raypick; same answer as three's raycast, milliseconds instead of ~150 ms).
  // Tubes and point markers: three.js.
  const targets: THREE.Object3D[] = []
  for (const [layerId, e] of t.entries)
    for (const part of e.parts) {
      const kind = part.built.pick.kind
      if (kind !== 'indexed' && kind !== 'pair') {
        targets.push(part.built.object)
        continue
      }
      for (const h of raycastChunks(part.geometry, ray.ray, threshold, 1)) {
        const segment = part.geometry.header.segments[h.segment]
        const score = h.distanceToRay / Math.max(h.distance, 1e-9) + (part.role === 'context' ? 1 : 0)
        consider({ kind: 'trace', layerId, role: part.role, part, pointIndex: h.pointIndex, segment, cell: segment.cell_id }, score)
      }
    }
  for (const e of t.points.values()) for (const p of e.parts) targets.push(p.built.object)
  // recursive: line layers carry a Points child for one-spot segments
  for (const h of ray.intersectObjects(targets, true)) {
    const owner = h.object.userData.singletons && h.object.parent ? h.object.parent : h.object
    const ud = owner.userData as { kind?: string; layerId?: string; set?: string; role: Role }
    const off = (h as { distanceToRay?: number }).distanceToRay ?? ray.ray.distanceToPoint(h.point)
    const score = off / Math.max(h.distance, 1e-9) + (ud.role === 'context' ? 1 : 0)
    if (ud.kind === 'points') {
      const e = t.points.get(ud.set!)
      const part = e?.parts.find((p) => p.role === ud.role)
      if (!e || !part || h.index === undefined || h.index === null) continue
      const index = part.built.indices[h.index]
      // markers sit on the chromatin: prefer them on ties
      consider({ kind: 'point', set: e.set, role: ud.role, index, cell: e.set.cellIds[index] }, score - 1e-4)
    } else {
      const part = t.entries.get(ud.layerId!)?.parts.find((p) => p.role === ud.role)
      if (!part) continue
      const pi = pointIndexOfHit(part.built.pick, h)
      if (pi < 0) continue
      const si = findSegment(part.geometry.offsets, pi)
      if (si < 0) continue
      const segment = part.geometry.header.segments[si]
      consider({ kind: 'trace', layerId: ud.layerId!, role: ud.role, part, pointIndex: pi, segment, cell: segment.cell_id }, score)
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
function pickAt(t: Three, e: PointerEvent, paneId: string, focus: string | null) {
  const store = useStore.getState()
  const hit = hitAt(t, e.clientX, e.clientY)
  if (!hit) {
    store.setPick(null)
    return
  }
  if (hasManyCells(store) && hit.cell !== null && hit.cell !== focus) {
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
      paneId,
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
    paneId,
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
function hoverAt(t: Three, e: PointerEvent, tip: HTMLDivElement, focus: string | null) {
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
    if (t.hoverBox.visible) t.dirty = true
    t.hoverBox.visible = false
    tip.style.display = 'none'
    t.renderer.domElement.style.cursor = ''
  }
  const cell = hit?.cell ?? null
  const otherCell = hasManyCells(store) && cell !== null && cell !== focus
  const pointText = hit?.kind === 'point' ? `${hit.set.labels[hit.index]}${cell !== null ? ` · cell ${cell}` : ''}` : null
  if (!hit || !otherCell) {
    clear()
    if (pointText) showTip(pointText) // a marker of the focused cell (or cell-less data)
    return
  }
  // anything of another cell: outline that cell and say a click focuses it
  // the geometry as drawn in this view (bonds cut, chromosomes separated)
  const layerId = hit.kind === 'trace' ? hit.layerId : store.layers.find((l) => l.datasetId === store.activeDatasetId && l.visible && l.geometry)?.id
  const traceGeom = layerId ? t.entries.get(layerId)?.placed : undefined
  if (traceGeom) setHoverCell(t, cell!, traceGeom, new Set(view.hiddenChroms))
  const box = traceGeom ? cellBoxes(traceGeom).get(cell!) : undefined
  if (box) {
    t.hoverBox.box.copy(box)
    t.hoverBox.visible = true
    t.dirty = true
  }
  const info = (store.activeDatasetId ? store.cells[store.activeDatasetId] : undefined)?.find((c) => c.cell_id === cell)
  showTip(`${pointText ? `${pointText} — ` : `cell ${cell}${info ? ` · ${info.n_traces} traces` : ''} — `}click to focus`)
  t.renderer.domElement.style.cursor = 'pointer'
}

/** Swap the hover overlay to `cell` (built once per hovered cell). */
function setHoverCell(t: Three, cell: string | null, layerGeom?: Geometry, hidden?: ReadonlySet<string>) {
  if (t.hover && t.hover.cell === cell && t.hover.geometry === layerGeom) return
  t.dirty = true
  if (t.hover) {
    t.scene.remove(t.hover.built.object)
    t.hover.built.dispose()
    t.hover = null
  }
  if (cell === null || !layerGeom) return
  const g = subsetGeometry(layerGeom, (s) => s.cell_id === cell && !hidden?.has(s.chrom))
  if (!g.header.n_points) return
  const built = buildLayerObject(g, { ...DEFAULT_STYLE, mode: 'line', colorMode: 'custom', color: palette().strong, lineWidth: 2.5, opacity: 1 })
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

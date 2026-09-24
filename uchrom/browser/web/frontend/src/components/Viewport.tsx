import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { TrackballControls } from 'three/examples/jsm/controls/TrackballControls.js'
import { buildLayerObject, pointIndexOfHit, type BuiltLayer } from '../render/objects'
import { bboxDiagonal, findSegment } from '../render/segments'
import { useStore } from '../store'
import type { Geometry, Layer, LayerStyle } from '../types'
import { PickLabel } from './PickLabel'

interface Entry {
  built: BuiltLayer
  geometry: Geometry
  style: LayerStyle
}

interface Three {
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  controls: TrackballControls
  group: THREE.Group
  entries: Map<string, Entry>
  highlight: THREE.Mesh
}

/** Union bbox of all visible layers with geometry. */
function sceneBox(layers: Layer[]): THREE.Box3 | null {
  const box = new THREE.Box3()
  let any = false
  for (const l of layers) {
    if (!l.visible || !l.geometry || l.geometry.header.n_points === 0) continue
    const b = l.geometry.header.bbox
    box.expandByPoint(new THREE.Vector3(...b.min))
    box.expandByPoint(new THREE.Vector3(...b.max))
    any = true
  }
  return any ? box : null
}

function fitCamera(t: Three, box: THREE.Box3) {
  const center = box.getCenter(new THREE.Vector3())
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 1e-6)
  const dist = radius / Math.sin(THREE.MathUtils.degToRad(t.camera.fov / 2))
  t.camera.near = Math.max(dist / 1000, 1e-6)
  t.camera.far = dist * 100
  t.camera.position.copy(center).add(new THREE.Vector3(0, 0, dist * 1.1))
  t.camera.up.set(0, 1, 0)
  t.camera.updateProjectionMatrix()
  t.controls.target.copy(center)
  t.controls.update()
}

export function Viewport() {
  const hostRef = useRef<HTMLDivElement>(null)
  const threeRef = useRef<Three | null>(null)
  const fittedRef = useRef(false)
  const layers = useStore((s) => s.layers)
  const activeDatasetId = useStore((s) => s.activeDatasetId)
  const resetViewToken = useStore((s) => s.resetViewToken)
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

    const t: Three = { renderer, scene, camera, controls, group, entries: new Map(), highlight }
    threeRef.current = t

    const resize = () => {
      const w = host.clientWidth
      const h = host.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      controls.handleResize()
      for (const e of t.entries.values()) e.built.setResolution(w, h)
    }
    const ro = new ResizeObserver(resize)
    ro.observe(host)
    resize()

    let raf = 0
    const loop = () => {
      controls.update()
      renderer.render(scene, camera)
      raf = requestAnimationFrame(loop)
    }
    loop()

    // Click (not drag) → pick.
    let down: { x: number; y: number } | null = null
    const onDown = (e: PointerEvent) => {
      down = { x: e.clientX, y: e.clientY }
    }
    const onUp = (e: PointerEvent) => {
      if (!down || e.button !== 0) return
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y)
      down = null
      if (moved > 4) return
      pickAt(t, e)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        useStore.getState().setPick(null)
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
      for (const e of t.entries.values()) e.built.dispose()
      controls.dispose()
      renderer.dispose()
      host.removeChild(renderer.domElement)
      threeRef.current = null
    }
  }, [])

  // Sync scene objects with layers (only the active dataset is shown).
  useEffect(() => {
    const t = threeRef.current
    if (!t) return
    const shown = layers.filter((l) => l.datasetId === activeDatasetId && l.visible && l.geometry)
    const keep = new Set(shown.map((l) => l.id))
    for (const [id, e] of t.entries) {
      if (!keep.has(id)) {
        t.group.remove(e.built.object)
        e.built.dispose()
        t.entries.delete(id)
      }
    }
    const warnings: string[] = []
    for (const l of shown) {
      const prev = t.entries.get(l.id)
      if (prev && prev.geometry === l.geometry && prev.style === l.style) {
        if (prev.built.warning) warnings.push(`${l.name}: ${prev.built.warning}`)
        continue
      }
      if (prev) {
        t.group.remove(prev.built.object)
        prev.built.dispose()
      }
      const built = buildLayerObject(l.geometry!, l.style)
      built.object.userData.layerId = l.id
      built.setResolution(t.renderer.domElement.clientWidth, t.renderer.domElement.clientHeight)
      t.group.add(built.object)
      t.entries.set(l.id, { built, geometry: l.geometry!, style: l.style })
      if (built.warning) warnings.push(`${l.name}: ${built.warning}`)
    }
    setStatus(warnings.length ? warnings.join(' · ') : null)

    const box = sceneBox(shown)
    if (box && !fittedRef.current) {
      fitCamera(t, box)
      fittedRef.current = true
    }
    const pick = useStore.getState().pick
    if (pick && !keep.has(pick.layerId)) setPick(null)
  }, [layers, activeDatasetId, setPick, setStatus])

  // Explicit reset / dataset switch → refit.
  useEffect(() => {
    fittedRef.current = false
    const t = threeRef.current
    if (!t) return
    const box = sceneBox(useStore.getState().layers.filter((l) => l.datasetId === activeDatasetId))
    if (box) {
      fitCamera(t, box)
      fittedRef.current = true
    }
  }, [resetViewToken, activeDatasetId])

  // Highlight the picked spot.
  const pick = useStore((s) => s.pick)
  useEffect(() => {
    const t = threeRef.current
    if (!t) return
    if (!pick) {
      t.highlight.visible = false
      return
    }
    const entry = t.entries.get(pick.layerId)
    if (!entry) return
    const p = entry.geometry.positions
    const i = pick.pointIndex
    t.highlight.position.set(p[3 * i], p[3 * i + 1], p[3 * i + 2])
    t.highlight.scale.setScalar(Math.max(bboxDiagonal(entry.geometry.header.bbox) * 0.006, 1e-6))
    t.highlight.visible = true
  }, [pick])

  return (
    <div className="viewport" ref={hostRef}>
      <PickLabel />
      <div className="viewport-tools">
        <button onClick={() => useStore.getState().resetView()} title="Fit all visible layers">
          Reset view
        </button>
      </div>
    </div>
  )
}

function pickAt(t: Three, e: PointerEvent) {
  const rect = t.renderer.domElement.getBoundingClientRect()
  const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1)
  const ray = new THREE.Raycaster()
  // Thresholds scale with the view so picking works at any unit
  // (a fraction of the camera distance ≈ a few pixels on screen).
  const threshold = t.camera.position.distanceTo(t.controls.target) * 0.006
  ray.params.Line = { threshold }
  ray.params.Points = { threshold }
  ray.setFromCamera(ndc, t.camera)
  const hits = ray.intersectObjects(t.group.children, false)
  const store = useStore.getState()
  for (const hit of hits) {
    const layerId = hit.object.userData.layerId as string
    const entry = t.entries.get(layerId)
    if (!entry) continue
    const pi = pointIndexOfHit(entry.built.pick, hit)
    if (pi < 0) continue
    const s = findSegment(entry.geometry.offsets, pi)
    if (s < 0) continue
    store.setPick({
      layerId,
      pointIndex: pi,
      segment: entry.geometry.header.segments[s],
      binStart: entry.geometry.starts[pi],
      screen: { x: e.clientX - rect.left, y: e.clientY - rect.top },
    })
    return
  }
  store.setPick(null)
}

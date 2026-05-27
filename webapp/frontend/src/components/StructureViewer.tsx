import { useEffect, useRef, useCallback, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { useAppStore, CameraState } from '../store'
import PanelContainer from './PanelContainer'

const PALETTE: [number, number, number][] = [
  [137, 180, 250], [166, 227, 161], [243, 139, 168], [250, 179, 135],
  [203, 166, 247], [148, 226, 213], [249, 226, 175], [180, 190, 254],
  [116, 199, 236], [245, 194, 231],
]

type RenderMode = 'points' | 'lines' | 'tubes'

interface SpotInfo { cellId: string; spotIdx: number; x: number; y: number; z: number }

interface Props { onExport?: () => void }

export default function StructureViewer({ onExport }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
  const sceneRef = useRef<THREE.Scene | null>(null)
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
  const controlsRef = useRef<OrbitControls | null>(null)
  const objectsRef = useRef<THREE.Object3D[]>([])
  const frameRef = useRef<number>(0)
  const spotMapRef = useRef<SpotInfo[]>([])  // instanceId → spot info
  const raycasterRef = useRef(new THREE.Raycaster())
  const mouseRef = useRef(new THREE.Vector2())
  const suppressCameraSync = useRef(false)
  const lodEnabledRef = useRef(true)  // LOD optimization toggle

  const [renderMode, setRenderMode] = useState<RenderMode>('points')
  const [tooltip, setTooltip] = useState<{ x: number; y: number; info: SpotInfo } | null>(null)
  const [lodEnabled, setLodEnabled] = useState(true)

  const instancedMeshRef = useRef<THREE.InstancedMesh | null>(null)
  const spotMapRef2 = useRef<{chrom: string; start: number; end: number}[]>([])  // bin info per instance

  const { cellSelection, cameraState, linkedCameras, setCameraState, highlightRegions, colormapConfig, viewport } = useAppStore()

  // Initialize Three.js
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setSize(container.clientWidth, container.clientHeight)
    renderer.setClearColor(0x1e1e2e)
    container.appendChild(renderer.domElement)
    rendererRef.current = renderer

    const scene = new THREE.Scene()
    sceneRef.current = scene

    const camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.01, 1000)
    camera.position.set(0, 0, 5)
    cameraRef.current = camera

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.addEventListener('change', () => {
      if (suppressCameraSync.current) return
      setCameraState({
        position: camera.position.toArray() as [number,number,number],
        target: controls.target.toArray() as [number,number,number],
      })
    })
    controlsRef.current = controls

    const animate = () => {
      frameRef.current = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    const ro = new ResizeObserver(() => {
      renderer.setSize(container.clientWidth, container.clientHeight)
      camera.aspect = container.clientWidth / container.clientHeight
      camera.updateProjectionMatrix()
    })
    ro.observe(container)

    return () => {
      cancelAnimationFrame(frameRef.current)
      ro.disconnect()
      controls.dispose()
      renderer.dispose()
      container.removeChild(renderer.domElement)
    }
  }, [setCameraState])

  // Sync camera from store when linked
  useEffect(() => {
    if (!linkedCameras || !cameraState || !cameraRef.current || !controlsRef.current) return
    suppressCameraSync.current = true
    cameraRef.current.position.set(...cameraState.position)
    controlsRef.current.target.set(...cameraState.target)
    controlsRef.current.update()
    suppressCameraSync.current = false
  }, [cameraState, linkedCameras])

  // Clear scene objects
  function clearObjects() {
    const scene = sceneRef.current
    if (!scene) return
    for (const obj of objectsRef.current) {
      scene.remove(obj)
      if ((obj as any).geometry) (obj as any).geometry.dispose()
      if ((obj as any).material) (obj as any).material.dispose()
    }
    objectsRef.current = []
    spotMapRef.current = []
  }

  // Fetch and render
  useEffect(() => {
    async function load() {
      clearObjects()
      let ids: string[]
      if (cellSelection.mode === 'all') {
        try {
          const r = await fetch('/api/umap')
          if (r.ok) {
            const body = await r.json()
            ids = (body.points as {cell_id: string}[]).slice(0, 10).map(p => p.cell_id)
          } else { ids = [] }
        } catch { ids = [] }
      } else {
        ids = cellSelection.ids.slice(0, 10)
      }
      if (ids.length === 0) return

      const r = await fetch(`/api/coords/batch?ids=${ids.join(',')}`)
      if (!r.ok) return
      const arr = new Float32Array(await r.arrayBuffer())
      const count = arr.length / 4
      if (count === 0) return

      const scene = sceneRef.current!
      const color = new THREE.Color()

      // Build per-cell point arrays
      const cellPoints: Map<number, {pts: number[], spotInfos: SpotInfo[]}> = new Map()
      for (let i = 0; i < count; i++) {
        const cellIdx = Math.round(arr[i*4])
        const x = arr[i*4+1], y = arr[i*4+2], z = arr[i*4+3]
        if (!cellPoints.has(cellIdx)) cellPoints.set(cellIdx, {pts: [], spotInfos: []})
        const entry = cellPoints.get(cellIdx)!
        entry.pts.push(x, y, z)
        entry.spotInfos.push({ cellId: ids[cellIdx] ?? String(cellIdx), spotIdx: entry.spotInfos.length, x, y, z })
      }

      if (renderMode === 'points') {
        // Use LOD for better performance
        const useLOD = lodEnabled && count > 1000
        const sphereDetail = useLOD ? 4 : 8  // Lower detail for large datasets
        const geo = new THREE.SphereGeometry(0.05, sphereDetail, sphereDetail)
        const mat = new THREE.MeshBasicMaterial()
        const mesh = new THREE.InstancedMesh(geo, mat, count)

        // Enable frustum culling
        mesh.frustumCulled = true

        const dummy = new THREE.Object3D()
        const spotInfos: SpotInfo[] = []
        let idx = 0
        for (const [cellIdx, {pts, spotInfos: si}] of cellPoints) {
          const [rv, g, b] = PALETTE[cellIdx % PALETTE.length]
          color.setRGB(rv/255, g/255, b/255)
          for (let j = 0; j < pts.length; j += 3) {
            dummy.position.set(pts[j], pts[j+1], pts[j+2])
            dummy.updateMatrix()
            mesh.setMatrixAt(idx, dummy.matrix)
            mesh.setColorAt(idx, color)
            spotInfos.push(si[j/3])
            idx++
          }
        }
        mesh.instanceMatrix.needsUpdate = true
        mesh.instanceColor!.needsUpdate = true
        scene.add(mesh)
        objectsRef.current.push(mesh)
        spotMapRef.current = spotInfos
        instancedMeshRef.current = mesh

      } else if (renderMode === 'lines') {
        for (const [cellIdx, {pts}] of cellPoints) {
          const positions = new Float32Array(pts)
          const geo = new THREE.BufferGeometry()
          geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
          const [rv, g, b] = PALETTE[cellIdx % PALETTE.length]
          const mat = new THREE.LineBasicMaterial({ color: new THREE.Color(rv/255, g/255, b/255), linewidth: 2 })
          const line = new THREE.Line(geo, mat)
          scene.add(line)
          objectsRef.current.push(line)
        }

      } else { // tubes
        for (const [cellIdx, {pts}] of cellPoints) {
          if (pts.length < 6) continue
          const points3d = []
          for (let j = 0; j < pts.length; j += 3) points3d.push(new THREE.Vector3(pts[j], pts[j+1], pts[j+2]))
          const curve = new THREE.CatmullRomCurve3(points3d)
          const geo = new THREE.TubeGeometry(curve, Math.min(points3d.length * 3, 300), 0.03, 6, false)
          const [rv, g, b] = PALETTE[cellIdx % PALETTE.length]
          const mat = new THREE.MeshPhongMaterial({ color: new THREE.Color(rv/255, g/255, b/255) })
          const tube = new THREE.Mesh(geo, mat)
          scene.add(tube)
          objectsRef.current.push(tube)
        }
        // Add ambient light for tubes
        const light = new THREE.AmbientLight(0xffffff, 0.8)
        const dlight = new THREE.DirectionalLight(0xffffff, 0.5)
        dlight.position.set(5, 5, 5)
        scene.add(light, dlight)
        objectsRef.current.push(light, dlight)
      }
    }
    load().catch(() => {})
  }, [cellSelection, renderMode, lodEnabled])

  // Sync lodEnabledRef
  useEffect(() => {
    lodEnabledRef.current = lodEnabled
  }, [lodEnabled])

  // Render highlight regions
  useEffect(() => {
    if (!highlightRegions || highlightRegions.length === 0) return
    const scene = sceneRef.current
    if (!scene) return

    // Remove old highlights
    const oldHighlights = objectsRef.current.filter(obj => (obj as any).isHighlight)
    oldHighlights.forEach(obj => {
      scene.remove(obj)
      if ((obj as any).geometry) (obj as any).geometry.dispose()
      if ((obj as any).material) (obj as any).material.dispose()
    })
    objectsRef.current = objectsRef.current.filter(obj => !(obj as any).isHighlight)

    // Add new highlights
    for (const region of highlightRegions) {
      // Create a bounding box for the region
      const color = new THREE.Color(region.color || '#ff6b6b')
      const boxGeo = new THREE.BoxGeometry(0.5, 0.5, 0.5)
      const boxMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.3,
        wireframe: true
      })
      const box = new THREE.Mesh(boxGeo, boxMat)
      box.position.set(0, 0, 0) // TODO: map genomic coords to 3D position
      ;(box as any).isHighlight = true
      scene.add(box)
      objectsRef.current.push(box)

      // Add label if provided
      if (region.label) {
        // TODO: Add text sprite for label
      }
    }
  }, [highlightRegions])

  // Apply colormap
  useEffect(() => {
    if (!colormapConfig || !colormapConfig.scheme) return
    // TODO: Re-color points based on colormapConfig.property and colormapConfig.scheme
    // For now, just log the config
    console.log('Colormap config:', colormapConfig)
  }, [colormapConfig])

  // Viewport bin highlighting: color bins inside viewport range
  useEffect(() => {
    const mesh = instancedMeshRef.current
    if (!mesh) return

    const color = new THREE.Color()
    const HIGHLIGHT = new THREE.Color(1.0, 0.42, 0.42)   // #ff6b6b
    const DEFAULT  = new THREE.Color(0.4, 0.7,  1.0)     // base blue

    // No viewport chrom → reset all to default
    if (!viewport || !viewport.chrom) {
      for (let i = 0; i < mesh.count; i++) {
        mesh.setColorAt(i, DEFAULT)
      }
      mesh.instanceColor!.needsUpdate = true
      return
    }

    // Need bin metadata; if not loaded yet, fetch it
    async function applyHighlight() {
      const spotInfos = spotMapRef.current
      if (spotInfos.length === 0 || !mesh) return

      // Determine first cell id to fetch bins
      let cellId: string | null = null
      if (cellSelection.mode === 'all') {
        try {
          const r = await fetch('/api/umap')
          if (r.ok) {
            const body = await r.json()
            const pts = body.points as {cell_id: string}[]
            if (pts.length > 0) cellId = pts[0].cell_id
          }
        } catch { /* ignore */ }
      } else if (cellSelection.ids.length > 0) {
        cellId = cellSelection.ids[0]
      }
      if (!cellId) return

      let bins: {chrom: string; start: number; end: number; idx: number}[] = []
      // Use cached bins if available, otherwise fetch
      if (spotMapRef2.current.length > 0) {
        bins = spotMapRef2.current.map((b, i) => ({ ...b, idx: i }))
      } else {
        try {
          const r = await fetch(`/api/bins/${cellId}`)
          if (!r.ok) return
          const body = await r.json()
          bins = body.bins
          spotMapRef2.current = bins.map((b: {chrom: string; start: number; end: number}) => ({
            chrom: b.chrom, start: b.start, end: b.end
          }))
        } catch { return }
      }

      const { chrom, start, end } = viewport!
      // bins are indexed by instance order — use spotInfos order as fallback
      // The bins endpoint returns bins for a single cell ordered by chrom/start.
      // We match by position in spotInfos (same order as instancedMesh was built for first cell).
      for (let i = 0; i < mesh!.count; i++) {
        const bin = bins[i]
        if (bin && bin.chrom === chrom && bin.start >= start && bin.end <= end) {
          mesh!.setColorAt(i, HIGHLIGHT)
        } else {
          // Restore palette color based on cell index in spotInfos
          const si = spotInfos[i]
          if (si) {
            // find cellIdx from ids
            // DEFAULT fallback
            mesh!.setColorAt(i, DEFAULT)
          } else {
            mesh!.setColorAt(i, DEFAULT)
          }
        }
      }
      mesh!.instanceColor!.needsUpdate = true
    }

    applyHighlight().catch(() => {})
  }, [viewport, cellSelection])

  // Raycaster: hover/click on points mode
  function onMouseMove(e: React.MouseEvent) {
    if (renderMode !== 'points') return
    const container = containerRef.current
    const mesh = objectsRef.current[0] as THREE.InstancedMesh
    if (!container || !mesh || !cameraRef.current) return
    const rect = container.getBoundingClientRect()
    mouseRef.current.set(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1
    )
    raycasterRef.current.setFromCamera(mouseRef.current, cameraRef.current)
    const hits = raycasterRef.current.intersectObject(mesh)
    if (hits.length > 0 && hits[0].instanceId !== undefined) {
      const info = spotMapRef.current[hits[0].instanceId]
      if (info) setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, info })
    } else {
      setTooltip(null)
    }
  }

  const handleExport = useCallback(() => {
    const renderer = rendererRef.current
    if (!renderer) return
    const a = document.createElement('a')
    a.href = renderer.domElement.toDataURL('image/png')
    a.download = '3d_structure.png'
    a.click()
    onExport?.()
  }, [onExport])

  const linkedCamerasStore = useAppStore(s => s.linkedCameras)
  const setLinkedCameras = useAppStore(s => s.setLinkedCameras)

  return (
    <PanelContainer title="3D Structure">
      <div style={{ position: 'relative', width: '100%', height: '100%' }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }}
          onMouseMove={onMouseMove} onMouseLeave={() => setTooltip(null)} />

        {/* Controls bar */}
        <div style={{ position: 'absolute', top: 6, right: 6, display: 'flex', gap: 4 }}>
          {(['points','lines','tubes'] as RenderMode[]).map(m => (
            <button key={m} onClick={() => setRenderMode(m)}
              style={{ background: renderMode === m ? '#89b4fa' : 'rgba(24,24,37,0.85)',
                       color: renderMode === m ? '#1e1e2e' : '#cdd6f4',
                       border: '1px solid #313244', fontSize: 10, padding: '2px 6px',
                       borderRadius: 3, cursor: 'pointer', textTransform: 'capitalize' }}>
              {m}
            </button>
          ))}
          <button onClick={() => setLinkedCameras(!linkedCamerasStore)}
            style={{ background: linkedCamerasStore ? '#a6e3a1' : 'rgba(24,24,37,0.85)',
                     color: linkedCamerasStore ? '#1e1e2e' : '#cdd6f4',
                     border: '1px solid #313244', fontSize: 10, padding: '2px 6px',
                     borderRadius: 3, cursor: 'pointer' }}>
            🔗
          </button>
          <button onClick={() => setLodEnabled(!lodEnabled)}
            title="Toggle LOD optimization"
            style={{ background: lodEnabled ? '#a6e3a1' : 'rgba(24,24,37,0.85)',
                     color: lodEnabled ? '#1e1e2e' : '#cdd6f4',
                     border: '1px solid #313244', fontSize: 10, padding: '2px 6px',
                     borderRadius: 3, cursor: 'pointer' }}>
            ⚡
          </button>
          <button onClick={handleExport}
            style={{ background: 'rgba(24,24,37,0.85)', border: '1px solid #313244',
                     color: '#cdd6f4', fontSize: 10, padding: '2px 6px',
                     borderRadius: 3, cursor: 'pointer' }}>
            PNG
          </button>
        </div>

        {/* Tooltip */}
        {tooltip && (
          <div style={{
            position: 'absolute', left: tooltip.x + 12, top: tooltip.y - 8,
            background: 'rgba(24,24,37,0.95)', border: '1px solid #313244',
            color: '#cdd6f4', fontSize: 11, padding: '5px 8px', borderRadius: 4,
            pointerEvents: 'none', whiteSpace: 'nowrap',
          }}>
            <div>cell: <b>{tooltip.info.cellId}</b></div>
            <div>spot: {tooltip.info.spotIdx}</div>
            <div>x={tooltip.info.x.toFixed(1)} y={tooltip.info.y.toFixed(1)} z={tooltip.info.z.toFixed(1)}</div>
          </div>
        )}
      </div>
    </PanelContainer>
  )
}

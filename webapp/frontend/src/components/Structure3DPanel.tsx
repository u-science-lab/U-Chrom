import { useRef, useEffect, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { useAppStore } from '../store'

const PALETTE = [
  0x3b82f6, // blue
  0xf97316, // orange
  0x22c55e, // green
  0xa855f7, // purple
  0xec4899, // pink
  0x14b8a6, // teal
  0xeab308, // yellow
  0xef4444, // red
]

interface Trace {
  trace_id: string
  chrom: string
  points: [number, number, number][]
}

interface Structure3DData {
  traces: Trace[]
}

export default function Structure3DPanel() {
  const dataVersion = useAppStore(s => s.dataVersion)
  const highlightedCells = useAppStore(s => s.highlightedCells)
  const [data, setData] = useState<Structure3DData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
  const controlsRef = useRef<OrbitControls | null>(null)
  const animIdRef = useRef<number | null>(null)
  const sceneRef = useRef<THREE.Scene | null>(null)
  const observerRef = useRef<ResizeObserver | null>(null)
  // trace_id → its Line + base color, for highlight updates without a rebuild
  const lineMapRef = useRef<Map<string, { line: THREE.Line; baseColor: number }>>(new Map())

  // Fetch data on mount and when dataVersion changes
  useEffect(() => {
    let cancelled = false
    setError(null)

    // Step 1: Get cell list from UMAP
    fetch('/api/umap')
      .then(r => {
        if (!r.ok) throw new Error(`UMAP fetch failed: HTTP ${r.status}`)
        return r.json()
      })
      .then(umapData => {
        if (cancelled) return
        const cellIds = umapData.points.map((p: any) => p.cell_id)
        if (cellIds.length === 0) {
          setData({ traces: [] })
          return
        }

        // Step 2: Fetch 3D coords from /api/coords/batch (POST to avoid URL length limits)
        return fetch('/api/coords/batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cell_ids: cellIds })
        })
          .then(r => {
            if (!r.ok) throw new Error(`Coords fetch failed: HTTP ${r.status}`)
            return r.arrayBuffer()
          })
          .then(buffer => {
            if (cancelled) return

            // Step 3: Parse float32 binary data
            const float32 = new Float32Array(buffer)

            // Step 4: Group by cell_index to build traces
            // Each row: [cell_index, x, y, z]
            const tracesMap = new Map<number, { trace_id: string; chrom: string; points: [number, number, number][] }>()

            for (let i = 0; i < float32.length; i += 4) {
              const cellIndex = Math.round(float32[i])
              const x = float32[i + 1]
              const y = float32[i + 2]
              const z = float32[i + 3]

              if (!tracesMap.has(cellIndex)) {
                tracesMap.set(cellIndex, {
                  trace_id: cellIds[cellIndex] || `cell_${cellIndex}`,
                  chrom: cellIds[cellIndex] || `cell_${cellIndex}`,
                  points: []
                })
              }
              tracesMap.get(cellIndex)!.points.push([x, y, z])
            }

            // Convert to traces array
            const traces = Array.from(tracesMap.values())
            setData({ traces })
          })
      })
      .catch(e => { if (!cancelled) setError(String(e)) })

    return () => { cancelled = true }
  }, [dataVersion])

  // Three.js setup — runs when data changes
  useEffect(() => {
    if (!data || !canvasRef.current || !containerRef.current) return

    const canvas = canvasRef.current
    const container = containerRef.current

    // Cleanup helper
    const cleanup = () => {
      if (animIdRef.current !== null) {
        cancelAnimationFrame(animIdRef.current)
        animIdRef.current = null
      }
      if (observerRef.current) {
        observerRef.current.disconnect()
        observerRef.current = null
      }
      if (controlsRef.current) {
        controlsRef.current.dispose()
        controlsRef.current = null
      }
      if (sceneRef.current) {
        sceneRef.current.traverse(obj => {
          if ((obj as THREE.Mesh).geometry) (obj as THREE.Mesh).geometry.dispose()
          const mat = (obj as THREE.Mesh).material
          if (mat) {
            if (Array.isArray(mat)) mat.forEach(m => m.dispose())
            else (mat as THREE.Material).dispose()
          }
        })
        sceneRef.current = null
      }
      if (rendererRef.current) {
        rendererRef.current.dispose()
        rendererRef.current = null
      }
    }

    cleanup()

    const width = container.clientWidth || 400
    const height = container.clientHeight || 400

    // Scene
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0xffffff)
    sceneRef.current = scene

    // Camera
    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 100000)

    // Renderer — attach to existing canvas element
    const renderer = new THREE.WebGLRenderer({ antialias: true, canvas })
    renderer.setSize(width, height)
    renderer.setPixelRatio(window.devicePixelRatio)
    rendererRef.current = renderer

    // OrbitControls
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controlsRef.current = controls

    // Collect all points to compute centroid + range
    const allPoints: THREE.Vector3[] = []

    lineMapRef.current = new Map()
    data.traces.forEach((trace, i) => {
      if (trace.points.length < 2) return
      const color = PALETTE[i % PALETTE.length]
      const geometry = new THREE.BufferGeometry()
      const positions = new Float32Array(trace.points.flat())
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
      const material = new THREE.LineBasicMaterial({ color, linewidth: 1 })
      const line = new THREE.Line(geometry, material)
      scene.add(line)
      lineMapRef.current.set(trace.trace_id, { line, baseColor: color })

      trace.points.forEach(([x, y, z]) => allPoints.push(new THREE.Vector3(x, y, z)))
    })

    // Center camera on centroid
    if (allPoints.length > 0) {
      const centroid = allPoints
        .reduce((acc, p) => acc.add(p), new THREE.Vector3())
        .divideScalar(allPoints.length)

      let maxRange = 1
      allPoints.forEach(p => {
        maxRange = Math.max(maxRange, p.distanceTo(centroid))
      })

      controls.target.copy(centroid)
      camera.position.set(centroid.x, centroid.y, centroid.z + maxRange * 2.5)
      camera.near = maxRange * 0.001
      camera.far = maxRange * 20
      camera.updateProjectionMatrix()
      controls.update()
    }

    // Animation loop
    const animate = () => {
      animIdRef.current = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    // ResizeObserver
    const resizeObserver = new ResizeObserver(() => {
      const w = container.clientWidth
      const h = container.clientHeight
      if (w === 0 || h === 0) return
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    })
    resizeObserver.observe(container)
    observerRef.current = resizeObserver

    return cleanup
  }, [data])

  // Apply cross-panel highlight: emphasize highlighted traces, dim the rest.
  // Runs after the scene is built and whenever the highlight set changes.
  useEffect(() => {
    const lineMap = lineMapRef.current
    if (lineMap.size === 0) return
    const highlightSet = new Set(highlightedCells)
    const hasHighlights = highlightSet.size > 0

    lineMap.forEach(({ line, baseColor }, traceId) => {
      const mat = line.material as THREE.LineBasicMaterial
      if (!hasHighlights) {
        // No highlights → everything at full strength in its base color
        mat.color.setHex(baseColor)
        mat.opacity = 1
        mat.transparent = false
      } else if (highlightSet.has(traceId)) {
        // Highlighted → bright yellow, fully opaque, drawn on top
        mat.color.setHex(0xfacc15)
        mat.opacity = 1
        mat.transparent = false
      } else {
        // Not highlighted → dim
        mat.color.setHex(baseColor)
        mat.opacity = 0.12
        mat.transparent = true
      }
      mat.needsUpdate = true
    })
  }, [highlightedCells, data])

  const isEmpty = data && data.traces.length === 0

  return (
    <div className="h-full flex flex-col">
      {/* Legend */}
      {data && data.traces.length > 0 && (
        <div className="flex flex-wrap gap-3 px-3 py-2 border-b border-border-subtle text-xs text-text-secondary">
          {data.traces.map((t, i) => {
            const isHl = highlightedCells.includes(t.trace_id)
            const anyHl = highlightedCells.length > 0
            const hex = isHl ? '#facc15' : '#' + PALETTE[i % PALETTE.length].toString(16).padStart(6, '0')
            return (
              <span
                key={t.trace_id}
                className={`flex items-center gap-1 ${anyHl && !isHl ? 'opacity-40' : ''} ${isHl ? 'font-semibold text-text-primary' : ''}`}
              >
                <span className="inline-block w-3 h-3 rounded-full" style={{ background: hex }} />
                {t.chrom || t.trace_id}
              </span>
            )
          })}
        </div>
      )}

      {/* Canvas container */}
      <div ref={containerRef} className="flex-1 relative min-h-0 overflow-hidden">
        {(error || isEmpty) ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center space-y-2">
              <div className="text-3xl">🔮</div>
              <div className="text-sm text-text-secondary">
                {error ? `Failed to load 3D data: ${error}` : 'No 3D structure data'}
              </div>
            </div>
          </div>
        ) : (
          <canvas ref={canvasRef} className="w-full h-full block" />
        )}
      </div>
    </div>
  )
}

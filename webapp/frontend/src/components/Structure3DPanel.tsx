import { useRef, useEffect, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { useAppStore } from '../store'
import { sessionApiUrl, ws } from '../ws'
import { registerCapturer } from '../snapshot'

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

// A render segment: one polyline for a (cell, chrom) pair. Splitting cells by
// chrom is what lets show_structure filter by chrom and color_structure color
// by chrom — a whole-cell polyline can't do either.
interface BinInfo {
  start: number | null
  end: number | null
  spot_index: number   // index of this point within the cell's spot order
  annotations?: Record<string, unknown>
}
interface Segment {
  seg_id: string      // unique: `${cell_id}:${chrom}`
  cell_id: string
  chrom: string
  points: [number, number, number][]
  bins: BinInfo[]     // index-aligned with points; bin metadata for 3D picking
}

interface Structure3DData {
  segments: Segment[]
}

function hexStr(c: number): string {
  return '#' + c.toString(16).padStart(6, '0')
}

function annotationKey(seg: Segment, field: string): string | null {
  const bin = seg.bins.find(b => b.annotations?.[field] != null)
  const value = bin?.annotations?.[field]
  return value == null ? null : String(value)
}

export default function Structure3DPanel() {
  const dataVersion = useAppStore(s => s.dataVersion)
  const highlightedCells = useAppStore(s => s.highlightedCells)
  // Agent-driven filtering / coloring (show_structure / color_structure).
  const selectedStructureCell = useAppStore(s => s.selectedStructureCell)
  const selectedStructureChrom = useAppStore(s => s.selectedStructureChrom)
  const structureColorBy = useAppStore(s => s.structureColorBy)

  const [data, setData] = useState<Structure3DData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
  const controlsRef = useRef<OrbitControls | null>(null)
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
  const animIdRef = useRef<number | null>(null)
  const sceneRef = useRef<THREE.Scene | null>(null)
  const observerRef = useRef<ResizeObserver | null>(null)
  // Scene scale (max distance from centroid), used to size the pick threshold.
  const maxRangeRef = useRef<number>(1)
  // seg_id → its Line + base color + owning cell + segment, for highlight
  // updates without a rebuild and for resolving raycaster picks back to a bin.
  const lineMapRef = useRef<Map<string, { line: THREE.Line; baseColor: number; cellId: string; segment: Segment }>>(new Map())

  // Fetch data on mount and when dataVersion changes. We pull, per cell, the
  // coords (flat, in spots order) AND the bins (chrom per spot, same order) so
  // we can split each cell's polyline into per-chrom segments.
  useEffect(() => {
    let cancelled = false
    setError(null)

    const run = async () => {
      try {
        const cellsRes = await fetch(sessionApiUrl('/api/cells'))
        if (!cellsRes.ok) throw new Error(`Cells fetch failed: HTTP ${cellsRes.status}`)
        const cellsData = await cellsRes.json()
        const cellIds: string[] = (cellsData.cells || []).map((c: { cell_id: string }) => c.cell_id)
        if (cellIds.length === 0) {
          if (!cancelled) setData({ segments: [] })
          return
        }

        // Coords for all cells: float32 rows [cell_index, x, y, z].
        const coordsRes = await fetch(sessionApiUrl('/api/coords/batch'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cell_ids: cellIds }),
        })
        if (!coordsRes.ok) throw new Error(`Coords fetch failed: HTTP ${coordsRes.status}`)
        const float32 = new Float32Array(await coordsRes.arrayBuffer())

        // Per-cell ordered coordinate list.
        const coordsByCell = new Map<number, [number, number, number][]>()
        for (let i = 0; i < float32.length; i += 4) {
          const ci = Math.round(float32[i])
          if (!coordsByCell.has(ci)) coordsByCell.set(ci, [])
          coordsByCell.get(ci)!.push([float32[i + 1], float32[i + 2], float32[i + 3]])
        }

        // Bins (chrom per spot) for each cell, index-aligned with its coords.
        const binsLists = await Promise.all(
          cellIds.map(cid =>
            fetch(sessionApiUrl(`/api/bins/${encodeURIComponent(cid)}?annotations=true`))
              .then(r => (r.ok ? r.json() : null))
              .catch(() => null),
          ),
        )

        const segments: Segment[] = []
        cellIds.forEach((cid, ci) => {
          const pts = coordsByCell.get(ci) || []
          if (pts.length === 0) return
          const bins = (binsLists[ci]?.bins as Array<{
            chrom: string
            start?: number
            end?: number
            annotations?: Record<string, unknown>
          }> | undefined) || null

          if (bins && bins.length === pts.length) {
            // Group consecutive points by chrom into per-chrom polylines,
            // carrying each point's bin metadata (start/end + spot index) so a
            // 3D pick can report exactly which genomic bin the user clicked.
            const byChrom = new Map<string, [number, number, number][]>()
            const binsByChrom = new Map<string, BinInfo[]>()
            for (let k = 0; k < pts.length; k++) {
              const ch = String(bins[k]?.chrom ?? 'unknown')
              if (!byChrom.has(ch)) { byChrom.set(ch, []); binsByChrom.set(ch, []) }
              byChrom.get(ch)!.push(pts[k])
              binsByChrom.get(ch)!.push({
                start: bins[k]?.start ?? null,
                end: bins[k]?.end ?? null,
                spot_index: k,
                annotations: bins[k]?.annotations,
              })
            }
            byChrom.forEach((cpts, ch) => {
              segments.push({
                seg_id: `${cid}:${ch}`, cell_id: cid, chrom: ch,
                points: cpts, bins: binsByChrom.get(ch)!,
              })
            })
          } else {
            // No usable bins → one segment for the whole cell, chrom unknown.
            segments.push({
              seg_id: `${cid}:*`, cell_id: cid, chrom: 'unknown', points: pts,
              bins: pts.map((_, k) => ({ start: null, end: null, spot_index: k })),
            })
          }
        })

        if (!cancelled) setData({ segments })
      } catch (e) {
        if (!cancelled) setError(String(e))
      }
    }

    run()
    return () => { cancelled = true }
  }, [dataVersion])

  // Three.js setup — runs when data, the cell/chrom filter, or the color field
  // change. Filtering and coloring happen here so they take real visual effect.
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

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0xffffff)
    sceneRef.current = scene

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 100000)
    cameraRef.current = camera

    // preserveDrawingBuffer keeps the rendered frame readable after draw, which
    // is required for canvas.toDataURL() to return real pixels (otherwise the
    // WebGL back-buffer is cleared post-render and a snapshot comes back blank).
    // This is what makes capture_view_snapshot work for the 3D view.
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      canvas,
      preserveDrawingBuffer: true,
    })
    renderer.setSize(width, height)
    renderer.setPixelRatio(window.devicePixelRatio)
    rendererRef.current = renderer

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controlsRef.current = controls

    // Apply the show_structure filter: restrict to one cell and/or one chrom.
    const visible = data.segments.filter(s =>
      (!selectedStructureCell || s.cell_id === selectedStructureCell) &&
      (!selectedStructureChrom || s.chrom === selectedStructureChrom),
    )

    // Build color maps for the color_structure field. 'chrom' colors by
    // chromosome; anything else (default / 'trace_id' / 'cell_id') colors per
    // cell so each cell stays visually distinct.
    const byChrom = structureColorBy === 'chrom'
    const byAnnotation = Boolean(structureColorBy && !['chrom', 'cell_id', 'trace_id'].includes(structureColorBy))
    const chromColor = new Map<string, number>()
    Array.from(new Set(data.segments.map(s => s.chrom))).sort().forEach((ch, i) => {
      chromColor.set(ch, PALETTE[i % PALETTE.length])
    })
    const cellColor = new Map<string, number>()
    Array.from(new Set(data.segments.map(s => s.cell_id))).forEach((cid, i) => {
      cellColor.set(cid, PALETTE[i % PALETTE.length])
    })
    const annotationColor = new Map<string, number>()
    if (byAnnotation && structureColorBy) {
      Array.from(new Set(
        data.segments
          .map(s => annotationKey(s, structureColorBy))
          .filter((v): v is string => Boolean(v)),
      )).sort().forEach((value, i) => annotationColor.set(value, PALETTE[i % PALETTE.length]))
    }
    const baseColorFor = (s: Segment): number => {
      if (byChrom) return chromColor.get(s.chrom) ?? PALETTE[0]
      if (byAnnotation && structureColorBy) {
        const value = annotationKey(s, structureColorBy)
        if (value) return annotationColor.get(value) ?? PALETTE[0]
        return 0x9ca3af
      }
      return cellColor.get(s.cell_id) ?? PALETTE[0]
    }

    const allPoints: THREE.Vector3[] = []
    lineMapRef.current = new Map()
    visible.forEach(seg => {
      if (seg.points.length < 2) return
      const color = baseColorFor(seg)
      const geometry = new THREE.BufferGeometry()
      const positions = new Float32Array(seg.points.flat())
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
      const material = new THREE.LineBasicMaterial({ color, linewidth: 1 })
      const line = new THREE.Line(geometry, material)
      scene.add(line)
      lineMapRef.current.set(seg.seg_id, { line, baseColor: color, cellId: seg.cell_id, segment: seg })

      seg.points.forEach(([x, y, z]) => allPoints.push(new THREE.Vector3(x, y, z)))
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
      maxRangeRef.current = maxRange

      controls.target.copy(centroid)
      camera.position.set(centroid.x, centroid.y, centroid.z + maxRange * 2.5)
      camera.near = maxRange * 0.001
      camera.far = maxRange * 20
      camera.updateProjectionMatrix()
      controls.update()
    }

    const animate = () => {
      animIdRef.current = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    // 3D spot picking: a click raycasts against the rendered polylines and finds
    // the nearest vertex, then reports a `pick_spot` ui_event carrying that bin's
    // metadata (cell_id, chrom, start/end, spot_index). This closes the loop so
    // the agent can "analyze the bin/region the user just clicked". We threshold
    // by line proximity; Three's Line raycast uses `Raycaster.params.Line.threshold`.
    const raycaster = new THREE.Raycaster()
    // Scale the line-pick threshold to the scene size so clicks register at any
    // zoom (coords units vary widely between datasets).
    raycaster.params.Line!.threshold = Math.max(0.5, (maxRangeRef.current || 1) * 0.02)
    const pointer = new THREE.Vector2()
    // Distinguish a real click from an orbit-drag: remember where the press
    // started and ignore the click if the pointer moved more than a few pixels.
    const downAt = { x: 0, y: 0 }
    const handleDown = (ev: MouseEvent) => { downAt.x = ev.clientX; downAt.y = ev.clientY }
    renderer.domElement.addEventListener('pointerdown', handleDown)

    const handlePick = (ev: MouseEvent) => {
      if (Math.hypot(ev.clientX - downAt.x, ev.clientY - downAt.y) > 5) return  // was a drag
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const lines: THREE.Line[] = []
      lineMapRef.current.forEach(({ line }) => lines.push(line))
      const hits = raycaster.intersectObjects(lines, false)
      if (hits.length === 0) return
      const hit = hits[0]
      const line = hit.object as THREE.Line
      // Find which segment this line belongs to.
      let picked: Segment | null = null
      lineMapRef.current.forEach(({ line: l, segment }) => {
        if (l === line) picked = segment
      })
      if (!picked) return
      const seg: Segment = picked
      // hit.index is the vertex index into the segment's points (Line geometry).
      const vIdx = typeof hit.index === 'number' ? hit.index : 0
      const bin = seg.bins[Math.min(vIdx, seg.bins.length - 1)]
      const pendingId = useAppStore.getState().pendingInteractionId
      ws.send('ui_event', {
        source_view_id: 'structure3d',
        event_name: 'pick_spot',
        ...(pendingId ? { interaction_id: pendingId } : {}),
        payload: {
          cell_id: seg.cell_id,
          chrom: seg.chrom,
          start: bin?.start ?? null,
          end: bin?.end ?? null,
          spot_index: bin?.spot_index ?? vIdx,
        },
      })
      // Visual feedback: briefly highlight the picked cell.
      useAppStore.getState().highlightCells([seg.cell_id])
    }
    renderer.domElement.addEventListener('click', handlePick)

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

    return () => {
      renderer.domElement.removeEventListener('click', handlePick)
      renderer.domElement.removeEventListener('pointerdown', handleDown)
      cleanup()
    }
  }, [data, selectedStructureCell, selectedStructureChrom, structureColorBy])

  // Apply cross-panel highlight: emphasize segments of highlighted cells, dim
  // the rest. Runs after the scene is built and whenever the highlight set changes.
  useEffect(() => {
    const lineMap = lineMapRef.current
    if (lineMap.size === 0) return
    const highlightSet = new Set(highlightedCells)
    const hasHighlights = highlightSet.size > 0

    lineMap.forEach(({ line, baseColor, cellId }) => {
      const mat = line.material as THREE.LineBasicMaterial
      if (!hasHighlights) {
        mat.color.setHex(baseColor)
        mat.opacity = 1
        mat.transparent = false
      } else if (highlightSet.has(cellId)) {
        mat.color.setHex(0xfacc15)
        mat.opacity = 1
        mat.transparent = false
      } else {
        mat.color.setHex(baseColor)
        mat.opacity = 0.12
        mat.transparent = true
      }
      mat.needsUpdate = true
    })
  }, [highlightedCells, data, selectedStructureCell, selectedStructureChrom, structureColorBy])

  // Register the snapshot capturer for capture_view_snapshot. Force a fresh
  // render into the (preserveDrawingBuffer) canvas, then read it as PNG. The
  // animation loop already renders every frame, but an explicit render right
  // before toDataURL guarantees the latest state is in the buffer.
  useEffect(() => {
    return registerCapturer('structure3d', async () => {
      const renderer = rendererRef.current
      const scene = sceneRef.current
      const camera = cameraRef.current
      if (!renderer || !scene || !camera) {
        throw new Error('3D scene not ready')
      }
      controlsRef.current?.update()
      renderer.render(scene, camera)
      return renderer.domElement.toDataURL('image/png')
    })
  }, [])

  // Visible segments mirror the filter applied in the build effect (for the legend).
  const visibleSegments = (data?.segments ?? []).filter(s =>
    (!selectedStructureCell || s.cell_id === selectedStructureCell) &&
    (!selectedStructureChrom || s.chrom === selectedStructureChrom),
  )
  const isEmpty = data && visibleSegments.length === 0
  const byChrom = structureColorBy === 'chrom'

  // Legend entries: by chrom when coloring by chrom, else one per cell.
  const legendKeys = byChrom
    ? Array.from(new Set(visibleSegments.map(s => s.chrom))).sort()
    : Array.from(new Set(visibleSegments.map(s => s.cell_id)))
  const colorIndex = new Map<string, number>()
  const allKeys = byChrom
    ? Array.from(new Set((data?.segments ?? []).map(s => s.chrom))).sort()
    : Array.from(new Set((data?.segments ?? []).map(s => s.cell_id)))
  allKeys.forEach((k, i) => colorIndex.set(k, i))

  return (
    <div className="h-full flex flex-col">
      {/* Legend */}
      {data && visibleSegments.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 px-3 py-2 border-b border-border-subtle text-xs text-text-secondary">
          <span className="text-text-secondary/70">
            color: {byChrom ? 'chrom' : 'cell'}
            {selectedStructureCell ? ` · cell ${selectedStructureCell}` : ''}
            {selectedStructureChrom ? ` · ${selectedStructureChrom}` : ''}
          </span>
          {legendKeys.map(key => {
            const isHl = !byChrom && highlightedCells.includes(key)
            const anyHl = highlightedCells.length > 0
            const idx = colorIndex.get(key) ?? 0
            const hex = isHl ? '#facc15' : hexStr(PALETTE[idx % PALETTE.length])
            return (
              <span
                key={key}
                className={`flex items-center gap-1 ${anyHl && !byChrom && !isHl ? 'opacity-40' : ''} ${isHl ? 'font-semibold text-text-primary' : ''}`}
              >
                <span className="inline-block w-3 h-3 rounded-full" style={{ background: hex }} />
                {key}
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

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import DeckGL, { type DeckGLRef } from '@deck.gl/react'
import { ScatterplotLayer } from '@deck.gl/layers'
import { OrthographicView } from '@deck.gl/core'
import { useAppStore } from '../store'
import { registerCapturer } from '../snapshot'
import { sessionApiUrl } from '../ws'

// Module-level view instance — created once, not on every render
const ORTHO_VIEW = new OrthographicView({ id: 'ortho', flipY: false })

interface ViewState {
  target: [number, number, number]
  zoom: number
}

// Categorical color palette — [r, g, b]
const PALETTE: [number, number, number][] = [
  [99, 179, 237],   // blue
  [252, 129, 74],   // orange
  [104, 211, 145],  // green
  [246, 173, 85],   // yellow
  [183, 148, 246],  // purple
  [237, 100, 166],  // pink
  [129, 230, 217],  // teal
  [247, 210, 111],  // gold
]

interface EmbeddingPoint {
  x: number
  y: number
  cell_id: string
  cell_type: string
}

interface EmbeddingData {
  points: EmbeddingPoint[]
  cell_types: string[]
}

// Per-cell metadata row from /api/cells: always cell_id, plus any string fields
// (cell_type, etc.). Used to color by an arbitrary field, not just cell_type.
interface CellEntry {
  cell_id: string
  [field: string]: string
}

function computeInitialViewState(points: EmbeddingPoint[]): ViewState {
  if (points.length === 0) {
    return { target: [0, 0, 0], zoom: 1 }
  }
  const xs = points.map(p => p.x)
  const ys = points.map(p => p.y)
  const minX = xs.reduce((a, b) => Math.min(a, b), Infinity)
  const maxX = xs.reduce((a, b) => Math.max(a, b), -Infinity)
  const minY = ys.reduce((a, b) => Math.min(a, b), Infinity)
  const maxY = ys.reduce((a, b) => Math.max(a, b), -Infinity)
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  const rangeX = maxX - minX || 1
  const rangeY = maxY - minY || 1
  // zoom so the full spread fits in ~80% of a 500px canvas
  const zoom = Math.log2(400 / Math.max(rangeX, rangeY))
  return { target: [cx, cy, 0], zoom }
}

export default function EmbeddingPanel() {
  const dataVersion = useAppStore(s => s.dataVersion)
  const cellSelection = useAppStore(s => s.cellSelection)
  const highlightedCells = useAppStore(s => s.highlightedCells)
  const highlightCells = useAppStore(s => s.highlightCells)
  const embeddingColorBy = useAppStore(s => s.embeddingColorBy)

  const [data, setData] = useState<EmbeddingData | null>(null)
  const [cellMeta, setCellMeta] = useState<Record<string, CellEntry>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewState, setViewState] = useState<ViewState>({ target: [0, 0, 0], zoom: 1 })
  const deckRef = useRef<DeckGLRef>(null)

  const fetchEmbedding = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Fetch UMAP coords and per-cell metadata together. /api/umap carries
      // cell_type; /api/cells carries the full cell table so we can color by
      // any field the agent picks via color_embedding.
      const [umapRes, cellsRes] = await Promise.all([
        fetch(sessionApiUrl('/api/umap')),
        fetch(sessionApiUrl('/api/cells')).catch(() => null),
      ])
      if (!umapRes.ok) throw new Error(`HTTP ${umapRes.status}`)
      const json: EmbeddingData = await umapRes.json()

      const meta: Record<string, CellEntry> = {}
      if (cellsRes && cellsRes.ok) {
        const cj = await cellsRes.json()
        for (const c of (cj.cells || []) as CellEntry[]) {
          meta[String(c.cell_id)] = c
        }
      }
      setCellMeta(meta)

      if (!json.points || json.points.length === 0) {
        setData(null)
      } else {
        setData(json)
        setViewState(computeInitialViewState(json.points))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load embedding')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchEmbedding()
  }, [dataVersion, fetchEmbedding])

  // Register the snapshot capturer for capture_view_snapshot ('embedding').
  // deck.gl 9.x keeps preserveDrawingBuffers=true by default, so the WebGL
  // canvas is readable after a redraw. Force a redraw, then toDataURL it.
  useEffect(() => {
    return registerCapturer('embedding', async () => {
      const deck = deckRef.current?.deck
      const canvas = deck?.getCanvas?.()
      if (!canvas) throw new Error('embedding canvas not ready')
      try {
        deck?.redraw?.('snapshot')
      } catch {
        // best-effort: a redraw failure shouldn't block reading the buffer
      }
      await new Promise<void>(res => requestAnimationFrame(() => res()))
      return canvas.toDataURL('image/png')
    })
  }, [])

  // Derive from data with fallbacks so all hooks run unconditionally
  const points = data?.points ?? []

  // Which field colors the scatter. Default to 'cell_type'; color_embedding can
  // switch it to any cell-table field. Resolve each point's category value from
  // the /api/cells metadata, falling back to the point's own cell_type.
  const colorField = embeddingColorBy ?? 'cell_type'
  const valueFor = useCallback((p: EmbeddingPoint): string => {
    if (colorField === 'cell_id') return p.cell_id
    const m = cellMeta[p.cell_id]
    const v = m ? m[colorField] : undefined
    if (v != null) return String(v)
    // Fall back to the umap-provided cell_type when metadata lacks the field.
    if (colorField === 'cell_type') return p.cell_type ?? 'unknown'
    return 'unknown'
  }, [colorField, cellMeta])

  // Categories present for the active field, in stable sorted order.
  const categories = useMemo(() => {
    const set = new Set<string>()
    for (const p of points) set.add(valueFor(p))
    return Array.from(set).sort()
  }, [points, valueFor])

  // Build color lookup by category value of the active field.
  const colorMap = useMemo(() => {
    const map: Record<string, [number, number, number]> = {}
    categories.forEach((c, i) => { map[c] = PALETTE[i % PALETTE.length] })
    return map
  }, [categories])

  const selectedIds = useMemo(() => new Set(cellSelection.ids), [cellSelection.ids])
  const hasSelection = cellSelection.mode !== 'all' && selectedIds.size > 0
  const highlightedSet = useMemo(() => new Set(highlightedCells), [highlightedCells])
  const hasHighlights = highlightedSet.size > 0

  // Toggle a cell's highlight on click — drives cross-panel linkage.
  const handleClick = useCallback((info: { object?: EmbeddingPoint }) => {
    const id = info.object?.cell_id
    const current = useAppStore.getState().highlightedCells
    if (!id) {
      // Clicked empty space → clear highlights
      if (current.length) useAppStore.getState().highlightCells([])
      return
    }
    const next = current.includes(id)
      ? current.filter(c => c !== id)
      : [...current, id]
    useAppStore.getState().highlightCells(next)
  }, [])

  const layer = useMemo(() => new ScatterplotLayer<EmbeddingPoint>({
    id: 'umap-scatter',
    data: points,
    getPosition: (d) => [d.x, d.y, 0],
    getFillColor: (d) => {
      const isHighlighted = highlightedSet.has(d.cell_id)

      // If highlighted, use bright yellow
      if (isHighlighted) {
        return [255, 255, 0, 200] as [number, number, number, number]
      }

      // Otherwise use base color (by the active color field) with selection logic
      const base = colorMap[valueFor(d)] ?? PALETTE[0]
      if (hasSelection) {
        const alpha = selectedIds.has(d.cell_id) ? 255 : 40
        return [...base, alpha] as [number, number, number, number]
      }
      // Dim non-highlighted points when a highlight set is active
      if (hasHighlights) {
        return [...base, 60] as [number, number, number, number]
      }
      return [...base, 210] as [number, number, number, number]
    },
    getRadius: (d) => {
      const isHighlighted = highlightedSet.has(d.cell_id)
      return isHighlighted ? 2 : 1
    },
    radiusMinPixels: hasHighlights ? 6 : 3,
    radiusMaxPixels: hasHighlights ? 12 : 8,
    pickable: true,
    onClick: handleClick,
    updateTriggers: {
      getFillColor: [hasSelection, selectedIds, highlightedSet, hasHighlights, colorMap, valueFor],
      getRadius: [highlightedSet],
    },
  }), [points, colorMap, valueFor, hasSelection, selectedIds, highlightedSet, hasHighlights, handleClick])

  // Early returns after all hooks
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-sm text-gray-400 animate-pulse">Loading embedding…</div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-center space-y-2 max-w-xs px-4">
          <div className="text-3xl">📊</div>
          <div className="text-sm font-medium text-gray-600">No embedding data available</div>
          <div className="text-xs text-gray-400">
            Ask the agent to compute one, e.g. “compute the UMAP embedding”
            (it runs <span className="font-mono">compute_embedding</span>).
          </div>
          {error && <div className="text-xs text-red-400">{error}</div>}
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Canvas area */}
      <div className="flex-1 relative min-h-0">
        <DeckGL
          ref={deckRef}
          views={ORTHO_VIEW}
          viewState={viewState}
          onViewStateChange={({ viewState: vs }) => setViewState(vs as ViewState)}
          controller={true}
          layers={[layer]}
          style={{ position: 'absolute', inset: '0' }}
        />
      </div>

      {/* Legend */}
      <div className="flex-shrink-0 border-t border-gray-100 px-3 py-2 flex flex-wrap gap-x-4 gap-y-1">
        <span className="text-xs text-gray-400 mr-1">color: {colorField}</span>
        {categories.map((cat, i) => {
          const [r, g, b] = PALETTE[i % PALETTE.length]
          return (
            <div key={cat} className="flex items-center gap-1.5">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: `rgb(${r},${g},${b})` }}
              />
              <span className="text-xs text-gray-600">{cat}</span>
            </div>
          )
        })}
        <span className="ml-auto text-xs text-gray-400">{points.length} cells</span>
        {hasHighlights && (
          <>
            <span className="text-xs text-yellow-600 font-medium">
              {highlightedSet.size} highlighted
            </span>
            <button
              className="px-2 py-0.5 text-xs bg-gray-100 hover:bg-gray-200 rounded border border-gray-300"
              onClick={() => highlightCells([])}
            >
              Clear
            </button>
          </>
        )}
      </div>
    </div>
  )
}

import { useState, useEffect, useCallback, useMemo } from 'react'
import DeckGL from '@deck.gl/react'
import { ScatterplotLayer } from '@deck.gl/layers'
import { OrthographicView } from '@deck.gl/core'
import { useAppStore } from '../store'

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

  const [data, setData] = useState<EmbeddingData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewState, setViewState] = useState<ViewState>({ target: [0, 0, 0], zoom: 1 })

  const fetchEmbedding = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/umap')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json: EmbeddingData = await res.json()
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

  // Derive from data with fallbacks so all hooks run unconditionally
  const cell_types = data?.cell_types ?? []
  const points = data?.points ?? []

  // Build color lookup by cell_type
  const colorMap = useMemo(() => {
    const map: Record<string, [number, number, number]> = {}
    cell_types.forEach((ct, i) => { map[ct] = PALETTE[i % PALETTE.length] })
    return map
  }, [cell_types])

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

      // Otherwise use base color with selection logic
      const base = colorMap[d.cell_type] ?? PALETTE[0]
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
      getFillColor: [hasSelection, selectedIds, highlightedSet, hasHighlights],
      getRadius: [highlightedSet],
    },
  }), [points, colorMap, hasSelection, selectedIds, highlightedSet, hasHighlights, handleClick])

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
        <div className="text-center space-y-2">
          <div className="text-3xl">📊</div>
          <div className="text-sm font-medium text-gray-600">No embedding data available</div>
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
        {cell_types.map((ct, i) => {
          const [r, g, b] = PALETTE[i % PALETTE.length]
          return (
            <div key={ct} className="flex items-center gap-1.5">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: `rgb(${r},${g},${b})` }}
              />
              <span className="text-xs text-gray-600">{ct}</span>
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

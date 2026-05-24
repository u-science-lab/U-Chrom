import { useEffect, useRef, useState } from 'react'
import DeckGL from '@deck.gl/react'
import { ScatterplotLayer } from '@deck.gl/layers'
import { OrthographicView } from '@deck.gl/core'
import { useAppStore } from '../store'
import PanelContainer from './PanelContainer'

interface UmapPoint { cell_id: string; x: number; y: number; cell_type?: string }
interface UmapData { points: UmapPoint[]; cell_types: string[] }

const PALETTE: [number, number, number][] = [
  [137, 180, 250], [166, 227, 161], [243, 139, 168], [250, 179, 135],
  [203, 166, 247], [148, 226, 213], [249, 226, 175], [180, 190, 254],
  [116, 199, 236], [245, 194, 231],
]

function colorFor(cellType: string | undefined, typeIndex: Map<string, number>): [number, number, number] {
  if (!cellType) return [108, 112, 134]
  return PALETTE[(typeIndex.get(cellType) ?? 0) % PALETTE.length]
}

export default function CellEmbedding() {
  const [data, setData] = useState<UmapData>({ points: [], cell_types: [] })
  const [viewState, setViewState] = useState({ target: [0, 0, 0] as [number,number,number], zoom: 1 })
  const { cellSelection, setCellSelection } = useAppStore()
  const dataVersion = useAppStore(s => s.dataVersion)
  const deckRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Lasso state
  const [lasso, setLasso] = useState<{x:number,y:number,w:number,h:number}|null>(null)
  const dragStart = useRef<{x:number,y:number}|null>(null)

  useEffect(() => {
    fetch('/api/umap')
      .then(r => r.json())
      .then(d => { if (d?.points) setData(d) })
      .catch(() => {})
  }, [dataVersion])

  const typeIndex = new Map(data.cell_types.map((t, i) => [t, i]))

  const layer = new ScatterplotLayer<UmapPoint>({
    id: 'umap',
    data: data.points,
    getPosition: d => [d.x, d.y, 0],
    getFillColor: d => {
      const color = colorFor(d.cell_type, typeIndex)
      const selected = cellSelection.mode === 'all' || cellSelection.ids.includes(d.cell_id)
      return [...color, selected ? 255 : 40] as [number, number, number, number]
    },
    getRadius: 4,
    radiusUnits: 'pixels',
    pickable: true,
    onClick: ({ object }) => {
      if (object) setCellSelection({ mode: 'manual', ids: [object.cell_id], label: object.cell_id })
    },
    updateTriggers: { getFillColor: [cellSelection] },
  })

  function onMouseDown(e: React.MouseEvent) {
    if (e.button !== 0) return
    const rect = containerRef.current!.getBoundingClientRect()
    dragStart.current = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    setLasso(null)
  }

  function onMouseMove(e: React.MouseEvent) {
    if (!dragStart.current) return
    const rect = containerRef.current!.getBoundingClientRect()
    const cx = e.clientX - rect.left
    const cy = e.clientY - rect.top
    const x = Math.min(dragStart.current.x, cx)
    const y = Math.min(dragStart.current.y, cy)
    const w = Math.abs(cx - dragStart.current.x)
    const h = Math.abs(cy - dragStart.current.y)
    if (w > 4 || h > 4) setLasso({ x, y, w, h })
  }

  function onMouseUp(e: React.MouseEvent) {
    if (!dragStart.current || !lasso || !deckRef.current) {
      dragStart.current = null; setLasso(null); return
    }
    // Pick all objects in the lasso rect
    const picked = deckRef.current.pickObjects({
      x: lasso.x, y: lasso.y, width: lasso.w, height: lasso.h, layerIds: ['umap']
    })
    const ids = picked.map((p: any) => p.object?.cell_id).filter(Boolean)
    if (ids.length > 0) {
      setCellSelection({ mode: 'manual', ids, label: `${ids.length} cells selected` })
    }
    dragStart.current = null; setLasso(null)
  }

  return (
    <PanelContainer title="Cell Embedding">
      <div ref={containerRef} style={{ position: 'relative', width: '100%', height: '100%',
                                       cursor: 'crosshair' }}
        onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp}>
        <DeckGL
          ref={deckRef}
          views={new OrthographicView({ id: 'ortho' })}
          layers={[layer]}
          viewState={viewState}
          onViewStateChange={({ viewState: vs }: any) => setViewState(vs)}
          controller={!dragStart.current}
          style={{ position: 'absolute', inset: '0' }}
        />
        {lasso && (
          <svg style={{ position: 'absolute', inset: 0, pointerEvents: 'none',
                        width: '100%', height: '100%' }}>
            <rect x={lasso.x} y={lasso.y} width={lasso.w} height={lasso.h}
              fill="rgba(137,180,250,0.15)" stroke="#89b4fa" strokeWidth={1} strokeDasharray="4 2" />
          </svg>
        )}
        {data.cell_types.length > 0 && (
          <div style={{ position: 'absolute', bottom: 8, left: 8,
                        background: 'rgba(24,24,37,0.85)', padding: '6px 8px',
                        borderRadius: 4, fontSize: 11, color: '#cdd6f4',
                        display: 'flex', flexDirection: 'column', gap: 3, pointerEvents: 'none' }}>
            {data.cell_types.map((t, i) => {
              const [r, g, b] = PALETTE[i % PALETTE.length]
              return (
                <div key={t} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <div style={{ width: 10, height: 10, borderRadius: 2,
                                background: `rgb(${r},${g},${b})`, flexShrink: 0 }} />
                  <span>{t}</span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </PanelContainer>
  )
}

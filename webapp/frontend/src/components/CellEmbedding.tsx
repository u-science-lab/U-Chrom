import { useEffect, useState } from 'react'
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
  const i = typeIndex.get(cellType) ?? 0
  return PALETTE[i % PALETTE.length]
}

export default function CellEmbedding() {
  const [data, setData] = useState<UmapData>({ points: [], cell_types: [] })
  const { cellSelection, setCellSelection } = useAppStore()

  useEffect(() => {
    fetch('/api/umap').then(r => r.json()).then(setData).catch(() => {})
  }, [])

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
    onClick: ({ object }) => object && setCellSelection({ mode: 'manual', ids: [object.cell_id], label: object.cell_id }),
    updateTriggers: { getFillColor: [cellSelection] },
  })

  return (
    <PanelContainer title="Cell Embedding">
      <div style={{ position: 'relative', width: '100%', height: '100%' }}>
        <DeckGL
          views={new OrthographicView({ id: 'ortho' })}
          layers={[layer]}
          initialViewState={{ target: [0, 0, 0], zoom: 1 }}
          controller={true}
          style={{ position: 'absolute', inset: '0' }}
        />
        {data.cell_types.length > 0 && (
          <div style={{
            position: 'absolute', bottom: 8, left: 8, background: 'rgba(24,24,37,0.85)',
            padding: '6px 8px', borderRadius: 4, fontSize: 11, color: '#cdd6f4',
            display: 'flex', flexDirection: 'column', gap: 3, pointerEvents: 'none',
          }}>
            {data.cell_types.map((t, i) => {
              const [r, g, b] = PALETTE[i % PALETTE.length]
              return (
                <div key={t} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <div style={{ width: 10, height: 10, borderRadius: 2, background: `rgb(${r},${g},${b})`, flexShrink: 0 }} />
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

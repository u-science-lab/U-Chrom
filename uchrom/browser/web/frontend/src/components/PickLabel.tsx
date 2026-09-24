import { composeFilter, fmtBp } from '../filters'
import { useStore } from '../store'

export function PickLabel() {
  const pick = useStore((s) => s.pick)
  const layer = useStore((s) => s.layers.find((l) => l.id === s.pick?.layerId))
  const addLayer = useStore((s) => s.addLayer)
  const setPick = useStore((s) => s.setPick)
  if (!pick) return null
  const seg = pick.segment
  const cellId = seg.cell_id
  // Offer "focus" unless this layer already shows just that one cell.
  const canFocus = cellId !== null && layer && !(layer.filter.cell_ids?.length === 1 && layer.filter.cell_ids[0] === cellId)
  const focusCell = () => {
    if (!layer || cellId === null) return
    const filter = composeFilter(layer.filter, { cell_ids: [cellId] })
    if (!filter) return
    addLayer({ datasetId: layer.datasetId, parentId: layer.id, name: `cell ${cellId}`, filter, style: { ...layer.style, mode: 'tube' } })
    setPick(null)
  }
  return (
    <div className="pick-label" style={{ left: pick.screen.x + 14, top: pick.screen.y + 14 }}>
      <div className="pick-title">trace {seg.trace_id}</div>
      {cellId !== null && <div>cell {cellId}</div>}
      <div>
        bin {seg.chrom}:{pick.binStart.toLocaleString('en-US')}
      </div>
      <div>
        segment {seg.chrom}:{fmtBp(seg.start)}-{fmtBp(seg.end)} · {seg.n_points} spots
      </div>
      {layer && <div className="muted">layer {layer.name}</div>}
      {canFocus && (
        <button className="pick-action" onClick={focusCell}>
          Focus cell {cellId}
        </button>
      )}
    </div>
  )
}

import { fmtBp } from '../filters'
import { useStore } from '../store'

export function PickLabel() {
  const pick = useStore((s) => s.pick)
  const layer = useStore((s) => s.layers.find((l) => l.id === s.pick?.layerId))
  if (!pick) return null
  const seg = pick.segment
  return (
    <div className="pick-label" style={{ left: pick.screen.x + 14, top: pick.screen.y + 14 }}>
      <div className="pick-title">trace {seg.trace_id}</div>
      {seg.cell_id !== null && <div>cell {seg.cell_id}</div>}
      <div>
        bin {seg.chrom}:{pick.binStart.toLocaleString('en-US')}
      </div>
      <div>
        segment {seg.chrom}:{fmtBp(seg.start)}-{fmtBp(seg.end)} · {seg.n_points} spots
      </div>
      {layer && <div className="muted">layer {layer.name}</div>}
    </div>
  )
}

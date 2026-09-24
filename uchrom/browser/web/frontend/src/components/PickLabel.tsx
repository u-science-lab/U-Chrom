import { fmtBp } from '../filters'
import { useStore } from '../store'
import { isPointPick } from '../types'
import { fmtNum } from './format'

/** Details of the clicked trace / point, shown in the pane where it was clicked. */
export function PickLabel({ paneId }: { paneId?: string }) {
  const pick = useStore((s) => s.pick)
  const layer = useStore((s) => s.layers.find((l) => !isPointPick(s.pick) && l.id === s.pick?.layerId))
  if (!pick || (paneId && pick.paneId && pick.paneId !== paneId)) return null
  if (isPointPick(pick)) {
    return (
      <div className="pick-label" style={{ left: pick.screen.x + 14, top: pick.screen.y + 14 }}>
        <div className="pick-title">
          {pick.set.toUpperCase()} {pick.label}
        </div>
        {pick.cellId !== null && <div>cell {pick.cellId}</div>}
        {Object.entries(pick.values).map(([k, v]) => (
          <div key={k}>
            {k} {v === null ? '—' : fmtNum(v)}
          </div>
        ))}
        <div className="muted">
          xyz {pick.position.map((v) => v.toFixed(2)).join(', ')}
        </div>
      </div>
    )
  }
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

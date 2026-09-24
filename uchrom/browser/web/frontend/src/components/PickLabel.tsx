import { useLayoutEffect, useRef, useState } from 'react'
import { fmtBp } from '../filters'
import { useStore } from '../store'
import { isPointPick } from '../types'
import { fmtNum } from './format'

/** Details of the clicked trace / point, shown in the pane where it was clicked. */
export function PickLabel({ paneId }: { paneId?: string }) {
  const pick = useStore((s) => s.pick)
  const layer = useStore((s) => s.layers.find((l) => !isPointPick(s.pick) && l.id === s.pick?.layerId))
  const manyCells = useStore((s) => ((s.activeDatasetId && s.cells[s.activeDatasetId]) || []).length > 1)
  const openCellView = useStore((s) => s.openCellView)
  const setPick = useStore((s) => s.setPick)
  // keep the label inside the pane (flip left / up near the edges)
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  useLayoutEffect(() => {
    const el = ref.current
    const box = el?.parentElement
    if (!el || !box || !pick) return setPos(null)
    const { x, y } = pick.screen
    const w = el.offsetWidth
    const h = el.offsetHeight
    const left = x + 14 + w > box.clientWidth ? Math.max(0, x - 14 - w) : x + 14
    const top = y + 14 + h > box.clientHeight ? Math.max(0, y - 14 - h) : y + 14
    setPos({ left, top })
  }, [pick])
  if (!pick || (paneId && pick.paneId && pick.paneId !== paneId)) return null
  const cell = isPointPick(pick) ? pick.cellId : pick.segment.cell_id
  const open =
    manyCells && cell !== null ? (
      <button
        className="pick-open"
        onClick={() => {
          openCellView(cell)
          setPick(null)
        }}
        title="Open this cell in a new view pinned to it"
      >
        ↗ Open cell in new view
      </button>
    ) : null
  if (isPointPick(pick)) {
    return (
      <div ref={ref} className="pick-label" style={pos ?? { left: pick.screen.x + 14, top: pick.screen.y + 14 }}>
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
        {open}
      </div>
    )
  }
  const seg = pick.segment
  return (
    <div ref={ref} className="pick-label" style={pos ?? { left: pick.screen.x + 14, top: pick.screen.y + 14 }}>
      <div className="pick-title">trace {seg.trace_id}</div>
      {seg.cell_id !== null && <div>cell {seg.cell_id}</div>}
      <div>
        bin {seg.chrom}:{pick.binStart.toLocaleString('en-US')}
      </div>
      <div>
        segment {seg.chrom}:{fmtBp(seg.start)}-{fmtBp(seg.end)} · {seg.n_points} spots
      </div>
      {layer && <div className="muted">layer {layer.name}</div>}
      {open}
    </div>
  )
}

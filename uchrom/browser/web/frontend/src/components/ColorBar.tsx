import { fieldRange, rgbCss, viridis } from '../colors'
import { activeFieldValues, activeView, useStore } from '../store'
import { fieldLabel, fmtNum } from './format'

/** Colour scale while the overview is coloured by a cell field (`inline`: compact, for the workspace bar). */
export function ColorBar({ inline = false }: { inline?: boolean }) {
  const view = useStore(activeView)
  const values = useStore(activeFieldValues)
  if (view.overviewColor !== 'field' || !view.cellField) return null
  const [lo, hi] = values ? fieldRange(values.values()) : [0, 1]
  const stops = Array.from({ length: 9 }, (_, i) => `${rgbCss(viridis(i / 8))} ${(i / 8) * 100}%`).join(', ')
  if (inline) {
    return (
      <div className="colorbar inline" title="99th-percentile cap · grey = missing">
        <span className="colorbar-title">{fieldLabel(view.cellField)}</span>
        <span className="colorbar-tick">{values ? fmtNum(lo) : '…'}</span>
        <span className="colorbar-ramp" style={{ background: `linear-gradient(to right, ${stops})` }} />
        <span className="colorbar-tick">{values ? `≥${fmtNum(hi)}` : ''}</span>
      </div>
    )
  }
  return (
    <div className="colorbar">
      <div className="colorbar-title">{fieldLabel(view.cellField)}</div>
      <div className="colorbar-ramp" style={{ background: `linear-gradient(to right, ${stops})` }} />
      <div className="colorbar-ticks">
        <span>{values ? fmtNum(lo) : '…'}</span>
        <span>{values ? `≥${fmtNum(hi)}` : ''}</span>
      </div>
      <div className="muted small">99th pct cap · grey = missing</div>
    </div>
  )
}

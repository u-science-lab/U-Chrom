import { activeView, useStore } from '../store'

/** Overlay above the viewport while a cell is focused: navigate + context opacity. */
export function FocusBar() {
  const view = useStore(activeView)
  const cells = useStore((s) => (s.activeDatasetId && s.cells[s.activeDatasetId]) || null)
  const step = useStore((s) => s.stepCell)
  const focus = useStore((s) => s.focusCell)
  const setCtx = useStore((s) => s.setContextOpacity)
  const openCellView = useStore((s) => s.openCellView)
  if (!view.focusCell || !cells?.length) return null
  const idx = cells.findIndex((c) => c.cell_id === view.focusCell)
  const info = cells[idx]
  return (
    <div className="focus-bar">
      <button onClick={() => step(-1)} title="Previous cell (←)">
        ◀
      </button>
      <div className="focus-title">
        cell <b>{view.focusCell}</b>
        <span className="muted">
          {' '}
          {idx + 1}/{cells.length}
          {info && ` · ${info.n_traces} traces · ${info.n_chroms} chroms`}
        </span>
      </div>
      <button onClick={() => step(1)} title="Next cell (→)">
        ▶
      </button>
      <label className="focus-ctx" title="Opacity of the other cells">
        others
        <input type="range" min={0} max={0.6} step={0.01} value={view.contextOpacity} onChange={(e) => setCtx(+e.target.value)} />
      </label>
      <button onClick={() => openCellView(view.focusCell!)} title="Open this cell in a new view pinned to it">
        ↗ New view
      </button>
      <button onClick={() => focus(null)} title="Back to all cells (Esc)">
        All cells
      </button>
    </div>
  )
}

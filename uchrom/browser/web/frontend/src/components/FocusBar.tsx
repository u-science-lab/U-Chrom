import { activeView, hasCoords, useStore } from '../store'
import { useGroupInfo } from '../useGroups'
import { addGroupPane } from '../workspace'

/** Overlay above the viewport while a cell is focused: navigate + context opacity. */
export function FocusBar() {
  const view = useStore(activeView)
  const cells = useStore((s) => (s.activeDatasetId && s.cells[s.activeDatasetId]) || null)
  const step = useStore((s) => s.stepCell)
  const focus = useStore((s) => s.focusCell)
  const setCtx = useStore((s) => s.setContextOpacity)
  const openCellView = useStore((s) => s.openCellView)
  const focusGroup = useStore((s) => s.focusGroup)
  const setWorkspace = useStore((s) => s.setWorkspace)
  const coords = useStore((s) => hasCoords(s.datasets.find((d) => d.id === s.activeDatasetId)))
  const group = useGroupInfo(view.focusGroup)
  if (view.focusGroup && !view.focusCell) {
    return (
      <div className="focus-bar">
        <div className="focus-title">
          group <span className="swatch round" style={{ display: 'inline-block', width: 9, height: 9, background: group?.color ?? '#888' }} /> <b>{group?.name ?? view.focusGroup}</b>
          <span className="muted"> · {group?.cells ? `${group.cells.length} cells` : '…'}</span>
        </div>
        <label className="focus-ctx" title="Opacity of the other cells">
          others
          <input type="range" min={0} max={0.6} step={0.01} value={view.contextOpacity} onChange={(e) => setCtx(+e.target.value)} />
        </label>
        <button onClick={() => setWorkspace((w) => addGroupPane(w, coords ? 'genome' : 'matrix', view.focusGroup!))} title="Open a new view aggregating over this group">
          ↗ New view
        </button>
        <button onClick={() => focusGroup(null)} title="Back to all cells (Esc)">
          All cells
        </button>
      </div>
    )
  }
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

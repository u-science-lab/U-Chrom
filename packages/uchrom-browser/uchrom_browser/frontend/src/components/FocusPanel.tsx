import { activeView, hasCoords, useStore } from '../store'
import { useGroupInfo } from '../useGroups'
import { addGroupPane } from '../workspace'

/**
 * Inspector card of the focused cell or group: which one (and its place in the list), step to the
 * previous / next cell, the opacity of the other cells, a new view pinned to it, back to all cells.
 * Nothing when no cell or group is focused.  (Was a bar above the views, which pushed the layout
 * down whenever a cell was picked.)
 */
export function FocusPanel() {
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
  const isGroup = !!view.focusGroup && !view.focusCell
  if (!isGroup && (!view.focusCell || !cells?.length)) return null
  const idx = isGroup || !cells ? -1 : cells.findIndex((c) => c.cell_id === view.focusCell)
  const info = idx >= 0 && cells ? cells[idx] : null
  return (
    <section className="focus-card">
      <div className="focus-head">
        <span className="insp-label">{isGroup ? 'group' : 'cell'}</span>
        {!isGroup && (
          <button className="focus-step" onClick={() => step(-1)} title="Previous cell (←)">
            ‹
          </button>
        )}
        <span className="focus-name" title={isGroup ? (group?.name ?? view.focusGroup!) : view.focusCell!}>
          {isGroup && <span className="swatch round" style={{ background: group?.color ?? '#888' }} />}
          {isGroup ? (group?.name ?? view.focusGroup) : view.focusCell}
        </span>
        {!isGroup && (
          <button className="focus-step" onClick={() => step(1)} title="Next cell (→)">
            ›
          </button>
        )}
      </div>
      <div className="muted small focus-meta">
        {isGroup
          ? group?.cells
            ? `${group.cells.length.toLocaleString('en-US')} cells`
            : '…'
          : `${idx + 1} / ${cells!.length.toLocaleString('en-US')}${info && info.n_traces ? ` · ${info.n_traces} traces · ${info.n_chroms} chroms` : ''}`}
      </div>
      <div className="emb-row" title="Opacity of the other cells in the views">
        <span className="emb-lab">others</span>
        <div className="emb-ctl emb-slider">
          <input type="range" min={0} max={0.6} step={0.01} value={view.contextOpacity} onChange={(e) => setCtx(+e.target.value)} />
          <span className="val">{view.contextOpacity.toFixed(2)}</span>
        </div>
      </div>
      <div className="focus-actions">
        <button
          onClick={() =>
            isGroup ? setWorkspace((w) => addGroupPane(w, coords ? 'genome' : 'matrix', view.focusGroup!)) : openCellView(view.focusCell!)
          }
          title={isGroup ? 'Open a new view aggregating over this group' : 'Open this cell in a new view pinned to it'}
        >
          ↗ New view
        </button>
        <button onClick={() => (isGroup ? focusGroup(null) : focus(null))} title="Back to all cells (Esc, or a click on empty space in a view)">
          All cells
        </button>
      </div>
    </section>
  )
}

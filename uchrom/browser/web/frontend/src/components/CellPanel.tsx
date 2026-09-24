import { useEffect, useMemo, useRef, useState } from 'react'
import { activeFieldValues, activeView, orderedCells, useStore } from '../store'
import { fieldLabel, fmtNum } from './format'

/** Cell navigator: pick a cell to focus it (no layers are created). */
export function CellPanel() {
  const all = useStore((s) => (s.activeDatasetId && s.cells[s.activeDatasetId]) || null)
  const view = useStore(activeView)
  const values = useStore(activeFieldValues)
  const dsId = useStore((s) => s.activeDatasetId)
  const cellsById = useStore((s) => s.cells)
  const views = useStore((s) => s.views)
  const cellValues = useStore((s) => s.cellValues)
  // derive the order here: a selector returning a fresh array would re-render forever
  const ordered = useMemo(
    () => orderedCells({ activeDatasetId: dsId, cells: cellsById, views, cellValues }),
    [dsId, cellsById, views, cellValues],
  )
  const focus = useStore((s) => s.focusCell)
  const setSort = useStore((s) => s.setCellSort)
  const [query, setQuery] = useState('')
  const listRef = useRef<HTMLUListElement>(null)
  const byField = view.overviewColor === 'field' && !!view.cellField

  const rows = useMemo(() => {
    const index = new Map((all ?? []).map((c, i) => [c.cell_id, i + 1]))
    const q = query.trim().toLowerCase()
    const list = ordered.map((c) => ({ ...c, index: index.get(c.cell_id) ?? 0 }))
    return q ? list.filter((c) => c.cell_id.toLowerCase().includes(q)) : list
  }, [all, ordered, query])

  // keep the focused cell in view when stepping with the arrow keys
  useEffect(() => {
    listRef.current?.querySelector('li.selected')?.scrollIntoView({ block: 'nearest' })
  }, [view.focusCell])

  if (!all || all.length < 2) return null
  return (
    <section className="panel cells">
      <h2>
        Cells <span className="muted">{all.length}</span>
        {byField && (
          <span className="cell-sort">
            <button className={view.cellSort === 'id' ? 'active' : ''} onClick={() => setSort('id')} title="Natural id order">
              id
            </button>
            <button
              className={view.cellSort === 'value' ? 'active' : ''}
              onClick={() => setSort('value')}
              title={`Highest ${fieldLabel(view.cellField!)} first`}
            >
              {fieldLabel(view.cellField!)} ↓
            </button>
          </span>
        )}
      </h2>
      <input placeholder="Search cell id…" value={query} onChange={(e) => setQuery(e.target.value)} />
      <ul className="cell-list" ref={listRef}>
        <li className={view.focusCell === null ? 'selected' : ''} onClick={() => focus(null)}>
          <span className="idx" />
          All cells
        </li>
        {rows.map((c) => (
          <li
            key={c.cell_id}
            className={c.cell_id === view.focusCell ? 'selected' : ''}
            onClick={() => focus(c.cell_id)}
            title={`${c.n_spots.toLocaleString('en-US')} spots`}
          >
            <span className="idx">{c.index}</span>
            {c.cell_id}
            <span className="muted"> {c.n_traces} traces</span>
            {byField && <span className="cell-value">{values ? fmtNum(values.get(c.cell_id)) : '…'}</span>}
          </li>
        ))}
      </ul>
      <div className="muted small">Click a cell here or in the view · ←/→ to step · Esc for all</div>
    </section>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { activeView, useStore } from '../store'

/** Cell navigator: pick a cell to focus it (no layers are created). */
export function CellPanel() {
  const cells = useStore((s) => (s.activeDatasetId && s.cells[s.activeDatasetId]) || null)
  const view = useStore(activeView)
  const focus = useStore((s) => s.focusCell)
  const [query, setQuery] = useState('')
  const listRef = useRef<HTMLUListElement>(null)

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    const all = (cells ?? []).map((c, i) => ({ ...c, index: i + 1 }))
    return q ? all.filter((c) => c.cell_id.toLowerCase().includes(q)) : all
  }, [cells, query])

  // keep the focused cell in view when stepping with the arrow keys
  useEffect(() => {
    listRef.current?.querySelector('li.selected')?.scrollIntoView({ block: 'nearest' })
  }, [view.focusCell])

  if (!cells || cells.length < 2) return null
  return (
    <section className="panel cells">
      <h2>
        Cells <span className="muted">{cells.length}</span>
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
          </li>
        ))}
      </ul>
      <div className="muted small">Click a cell here or in the view · ←/→ to step · Esc for all</div>
    </section>
  )
}

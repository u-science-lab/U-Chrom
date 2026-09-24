import { useMemo, useState } from 'react'
import { activeView, defaultCategoryField, fieldKey, useStore } from '../store'
import { pinPane, type Pane } from '../workspace'

/** Category label of each cell (e.g. cell type), when the dataset has one. */
export function useCellTypes(): ReadonlyMap<string, unknown> | undefined {
  return useStore((s) => {
    const ds = s.datasets.find((d) => d.id === s.activeDatasetId)
    const f = defaultCategoryField(ds)
    return ds && f ? s.cellValues[fieldKey(ds.id, f.name)] : undefined
  })
}

/** "cell 1_0_34 · Bergmann" */
export function cellTitle(cell: string, types?: ReadonlyMap<string, unknown>): string {
  const t = types?.get(cell)
  return typeof t === 'string' ? `cell ${cell} · ${t}` : `cell ${cell}`
}

const MAX_SHOWN = 80

/**
 * Pane-header control: the view follows the global focus, or is pinned to
 * one cell ("📌 cell …").  Search a cell (id or type) to pin it; unpin to
 * follow the focus again.
 */
export function PaneCellControl({ pane }: { pane: Pane }) {
  const cells = useStore((s) => (s.activeDatasetId ? s.cells[s.activeDatasetId] : undefined))
  const focus = useStore((s) => activeView(s).focusCell)
  const setWorkspace = useStore((s) => s.setWorkspace)
  const types = useCellTypes()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const matches = useMemo(() => {
    if (!open || !cells) return []
    const t = q.trim().toLowerCase()
    const hit = (id: string) => {
      if (!t) return true
      const ty = types?.get(id)
      return id.toLowerCase().includes(t) || (typeof ty === 'string' && ty.toLowerCase().includes(t))
    }
    const out: string[] = []
    for (const c of cells) {
      if (hit(c.cell_id)) out.push(c.cell_id)
      if (out.length >= MAX_SHOWN) break
    }
    return out
  }, [open, cells, q, types])
  if (!cells || cells.length < 2) return null
  const pinned = pane.cell ?? null
  const pin = (cell: string | null) => {
    setWorkspace((w) => pinPane(w, pane.id, cell))
    setOpen(false)
    setQ('')
  }
  return (
    <div className="pane-menu pane-cell">
      <button
        className={pinned ? 'pinned' : ''}
        onClick={() => setOpen(!open)}
        title={pinned ? 'This view is pinned to one cell — click to change or unpin' : 'This view follows the focused cell — click to pin it to a cell'}
      >
        {pinned ? `📌 ${cellTitle(pinned, types)}` : 'follow focus ▾'}
      </button>
      {open && (
        <div className="pane-popup" onMouseLeave={() => setOpen(false)}>
          <input autoFocus placeholder="pin to cell… (id or type)" value={q} onChange={(e) => setQ(e.target.value)} />
          <ul>
            <li className={pinned ? '' : 'on'} onClick={() => pin(null)}>
              <span className="tick">{pinned ? '' : '✓'}</span>follow focus{focus ? ` (now ${focus})` : ''}
            </li>
            {focus && focus !== pinned && (
              <li onClick={() => pin(focus)}>
                <span className="tick">📌</span>focused {cellTitle(focus, types)}
              </li>
            )}
            {matches.map((id) => (
              <li key={id} className={id === pinned ? 'on' : ''} onClick={() => pin(id)}>
                <span className="tick">{id === pinned ? '✓' : ''}</span>
                {id}
                {typeof types?.get(id) === 'string' && <span className="muted"> · {types.get(id) as string}</span>}
              </li>
            ))}
            {matches.length >= MAX_SHOWN && <li className="muted disabled">… type to narrow down</li>}
          </ul>
        </div>
      )}
    </div>
  )
}

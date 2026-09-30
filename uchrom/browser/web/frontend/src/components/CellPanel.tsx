import { useEffect, useMemo, useRef, useState } from 'react'
import { cellValueColor, rgbCss } from '../colors'
import { activeView, defaultCategoryField, fieldKey, orderedCells, useStore } from '../store'
import { useFieldColors } from '../useFieldColors'
import { useGroupInfo } from '../useGroups'
import { fieldLabel, fmtValue } from './format'
import { SideClose } from './SideClose'
import { useSize } from './useSize'

/** Row height of the cell list (px; must match `.cell-list li` in index.css). */
const ROW_H = 22
/** Rows rendered beyond the visible window on each side. */
const OVERSCAN = 12

/**
 * Cell navigator: pick a cell to focus it (no layers are created).
 * Virtualised: only the rows in view are rendered, so thousands of cells
 * (scHi-C barcodes) scroll and filter smoothly.
 */
export function CellPanel() {
  const all = useStore((s) => (s.activeDatasetId && s.cells[s.activeDatasetId]) || null)
  const view = useStore(activeView)
  const dsId = useStore((s) => s.activeDatasetId)
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const cellsById = useStore((s) => s.cells)
  const views = useStore((s) => s.views)
  const cellValues = useStore((s) => s.cellValues)
  const datasets = useStore((s) => s.datasets)
  // derive the order here: a selector returning a fresh array would re-render forever
  const ordered = useMemo(
    () => orderedCells({ activeDatasetId: dsId, cells: cellsById, views, cellValues, datasets }),
    [dsId, cellsById, views, cellValues, datasets],
  )
  const focus = useStore((s) => s.focusCell)
  const setSort = useStore((s) => s.setCellSort)
  const openCellView = useStore((s) => s.openCellView)
  const colors = useFieldColors()
  const [query, setQuery] = useState('')
  const listRef = useRef<HTMLUListElement>(null)
  const { h: listH } = useSize(listRef)
  const [scrollTop, setScrollTop] = useState(0)
  const byField = view.overviewColor === 'field' && !!view.cellField
  const values = colors.cellValues
  // members of the focused group get a coloured edge
  const group = useGroupInfo(view.focusGroup)
  const members = useMemo(() => (group?.cells ? new Set(group.cells) : null), [group])

  // Without 3-D coordinates "n traces" is always 0: show the cell's type instead.
  const hasCoords = ds?.has_coords !== false && (ds?.n_spots ?? 0) > 0
  const typeField = hasCoords ? null : defaultCategoryField(ds)
  const typeValues = useStore((s) => (dsId && typeField ? s.cellValues[fieldKey(dsId, typeField.name)] : undefined))
  const typeInline = typeField && !(byField && view.cellField === typeField.name) ? typeValues : undefined

  const rows = useMemo(() => {
    const index = new Map((all ?? []).map((c, i) => [c.cell_id, i + 1]))
    const q = query.trim().toLowerCase()
    const list = ordered.map((c) => ({ ...c, index: index.get(c.cell_id) ?? 0 }))
    if (!q) return list
    // match the id, or the cell's category (e.g. "L2/3" finds every L2/3 cell)
    const tag = (id: string) => {
      const v = typeValues?.get(id) ?? (colors.categories ? values?.get(id) : undefined)
      return typeof v === 'string' ? v.toLowerCase() : ''
    }
    return list.filter((c) => c.cell_id.toLowerCase().includes(q) || tag(c.cell_id).includes(q))
  }, [all, ordered, query, typeValues, values, colors.categories])

  // keep the focused cell in view when stepping with the arrow keys
  useEffect(() => {
    const el = listRef.current
    if (!el) return
    const i = view.focusCell === null ? 0 : rows.findIndex((c) => c.cell_id === view.focusCell) + 1 // +1: "All cells"
    if (i < 0) return
    const top = i * ROW_H
    if (top < el.scrollTop) el.scrollTop = top
    else if (top + ROW_H > el.scrollTop + el.clientHeight) el.scrollTop = top + ROW_H - el.clientHeight
  }, [view.focusCell]) // eslint-disable-line react-hooks/exhaustive-deps

  // a new filter starts at the top
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = 0
    setScrollTop(0)
  }, [query, dsId])

  if (!all || all.length < 2) return null
  const first = Math.max(0, Math.floor(scrollTop / ROW_H) - 1 - OVERSCAN) // -1: the "All cells" row
  const last = Math.min(rows.length, Math.ceil((scrollTop + (listH || 400)) / ROW_H) + OVERSCAN)
  const shown = rows.slice(first, last)
  return (
    <section className="panel cells">
      <h2>
        Cells <span className="muted">{all.length.toLocaleString('en-US')}</span>
        <SideClose side="left" />
      </h2>
      <div className="cell-search-row">
        <input
          placeholder={typeField || colors.categories ? 'Search cell id or type…' : 'Search cell id…'}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {byField && (
          <span className="cell-sort" role="group" aria-label="Order of the cells">
            <button className={view.cellSort === 'id' ? 'active' : ''} onClick={() => setSort('id')} title="Natural id order">
              id
            </button>
            <button
              className={view.cellSort === 'value' ? 'active' : ''}
              onClick={() => setSort('value')}
              title={colors.categories ? `Group by ${fieldLabel(view.cellField!)}` : `Highest ${fieldLabel(view.cellField!)} first`}
            >
              {fieldLabel(view.cellField!)} {colors.categories ? '' : '↓'}
            </button>
          </span>
        )}
      </div>
      <ul className="cell-list" ref={listRef} onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}>
        <li className={view.focusCell === null ? 'selected' : ''} onClick={() => focus(null)}>
          <span className="idx" />
          All cells {query && <span className="muted">· {rows.length.toLocaleString('en-US')} match</span>}
        </li>
        {first > 0 && <li className="spacer" style={{ height: first * ROW_H }} aria-hidden />}
        {shown.map((c) => {
          const v = values?.get(c.cell_id)
          const t = typeInline?.get(c.cell_id)
          return (
            <li
              key={c.cell_id}
              className={`${c.cell_id === view.focusCell ? 'selected' : ''}${members?.has(c.cell_id) ? ' in-group' : ''}`}
              style={members?.has(c.cell_id) ? { boxShadow: `inset 3px 0 0 ${group!.color}` } : undefined}
              onClick={() => focus(c.cell_id)}
              title={`${c.cell_id}${hasCoords ? ` · ${c.n_spots.toLocaleString('en-US')} spots` : ''}${typeof t === 'string' ? ` · ${t}` : ''}${byField && v !== undefined ? ` · ${fieldLabel(view.cellField!)}: ${fmtValue(v)}` : ''}`}
            >
              <span className="idx">{c.index}</span>
              <span className="cell-id">{c.cell_id}</span>
              <button
                className="cell-open"
                onClick={(e) => {
                  e.stopPropagation()
                  openCellView(c.cell_id)
                }}
                title="Open this cell in a new view"
              >
                ↗
              </button>
              {hasCoords && <span className="muted"> {c.n_traces} traces</span>}
              {typeof t === 'string' && <span className="muted cell-tag">{t}</span>}
              {byField &&
                (colors.categories ? (
                  <span className="cell-value cat">
                    <span className="swatch round" style={{ background: rgbCss(cellValueColor(v, colors)) }} />
                    {values ? fmtValue(v) : '…'}
                  </span>
                ) : (
                  <span className="cell-value">{values ? fmtValue(v) : '…'}</span>
                ))}
            </li>
          )
        })}
        {last < rows.length && <li className="spacer" style={{ height: (rows.length - last) * ROW_H }} aria-hidden />}
      </ul>
      <div className="muted small">Click a cell here or in the view · ←/→ to step · Esc for all</div>
    </section>
  )
}

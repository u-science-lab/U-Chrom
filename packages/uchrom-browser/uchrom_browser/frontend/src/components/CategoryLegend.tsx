import { useMemo } from 'react'
import { categoryColor, MISSING_RGB, rgbCss } from '../colors'
import { activeView, useStore } from '../store'
import { useFieldColors } from '../useFieldColors'
import type { CellValue } from '../types'
import { fieldLabel } from './format'

/** Legend rows of a categorical overview field: value, colour, cell count. */
export function useCategoryRows() {
  const { field, cellValues, categories } = useFieldColors()
  return useMemo(() => {
    if (!field || !categories) return null
    // counts from the loaded values when present (they cover every cell), else the summary's
    const counts = new Map<string, number>()
    let missing = 0
    if (cellValues) {
      for (const v of cellValues.values() as Iterable<CellValue>) {
        if (typeof v === 'string') counts.set(v, (counts.get(v) ?? 0) + 1)
        else missing++
      }
    } else for (const c of field.categories ?? []) counts.set(c.value, c.count)
    const order = new Map<string, number>()
    for (const c of field.categories ?? []) order.set(c.value, order.size)
    for (const v of counts.keys()) if (!order.has(v)) order.set(v, order.size)
    const rows = [...order.keys()].map((value, i) => ({
      value,
      count: counts.get(value) ?? 0,
      color: rgbCss(categoryColor(i, value)),
      off: categories.get(value) === -1,
    }))
    return { field, rows, missing }
  }, [field, cellValues, categories])
}

/**
 * Legend of the categorical overview colouring (e.g. cell type): swatch,
 * name and cell count; click hides a category (greys it), double-click
 * shows only that one.
 */
export function CategoryLegend() {
  const legend = useCategoryRows()
  const hidden = useStore((s) => activeView(s).hiddenCategories)
  const toggle = useStore((s) => s.toggleCategory)
  const setHidden = useStore((s) => s.setHiddenCategories)
  if (!legend) return null
  const { field, rows, missing } = legend
  const names = rows.map((r) => r.value)
  return (
    <section className="legend">
      <h2>
        <span>
          {fieldLabel(field.name)} <span className="muted">{rows.length}</span>
        </span>
        <span className="legend-actions">
          <button onClick={() => setHidden([])} disabled={!hidden.length}>
            all
          </button>
          <button onClick={() => setHidden(names)} disabled={hidden.length === names.length}>
            none
          </button>
        </span>
      </h2>
      <ul className="legend-list categories">
        {rows.map((r) => (
          <li
            key={r.value}
            className={r.off ? 'off' : ''}
            onClick={() => toggle(r.value)}
            onDoubleClick={() => setHidden(names.filter((n) => n !== r.value))}
            title={`${r.value}: ${r.count.toLocaleString('en-US')} cells · click to grey out / restore · double-click to show only this one`}
          >
            <span className="swatch" style={{ background: r.color }} />
            <span className="name">{r.value}</span>
            <span className="muted count">{r.count.toLocaleString('en-US')}</span>
          </li>
        ))}
        {missing > 0 && (
          <li className="missing" title="Cells without a value (drawn grey)">
            <span className="swatch" style={{ background: rgbCss(MISSING_RGB) }} />
            <span className="name muted">missing</span>
            <span className="muted count">{missing.toLocaleString('en-US')}</span>
          </li>
        )}
      </ul>
    </section>
  )
}

import { chromColor } from '../colors'
import { activeView, useStore } from '../store'

/**
 * Chromosome legend = visibility filter.  Swatches match the rainbow colour
 * of each chromosome; toggling only changes what is drawn.
 */
export function ChromLegend() {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const view = useStore(activeView)
  const toggle = useStore((s) => s.toggleChrom)
  const setHidden = useStore((s) => s.setHiddenChroms)
  if (!ds || ds.chroms.length < 2) return null
  const hidden = new Set(view.hiddenChroms)
  const names = ds.chroms.map((c) => c.name)
  return (
    <section className="legend">
      <h2>
        Chromosomes
        <span className="legend-actions">
          <button onClick={() => setHidden([])} disabled={!hidden.size}>
            all
          </button>
          <button onClick={() => setHidden(names)} disabled={hidden.size === names.length}>
            none
          </button>
        </span>
      </h2>
      <ul className="legend-list">
        {ds.chroms.map((c) => (
          <li
            key={c.name}
            className={hidden.has(c.name) ? 'off' : ''}
            onClick={() => toggle(c.name)}
            onDoubleClick={() => setHidden(names.filter((n) => n !== c.name))}
            title="Click to show/hide · double-click to show only this one"
          >
            <span className="swatch" style={{ background: chromColor(c.name) }} />
            {c.name}
          </li>
        ))}
      </ul>
    </section>
  )
}

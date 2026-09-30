import { chromColor } from '../colors'
import { activeView, useStore } from '../store'
import { effectiveStyle } from '../workspace'

/**
 * Chromosome legend = visibility filter.  Swatches match the rainbow colour
 * of each chromosome; toggling only changes what is drawn.
 */
export function ChromLegend() {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const view = useStore(activeView)
  const toggle = useStore((s) => s.toggleChrom)
  const setHidden = useStore((s) => s.setHiddenChroms)
  const hasCells = useStore((s) => ((s.activeDatasetId && s.cells[s.activeDatasetId]) || []).length > 1)
  // the selected layer's colouring as the active 3-D view draws it
  const layerMode = useStore((s) => {
    const l = s.layers.find((x) => x.id === s.selectedLayerId)
    return l ? effectiveStyle(l, s.workspace.panes.find((p) => p.id === s.workspace.activePane)).colorMode : undefined
  })
  if (!ds || ds.chroms.length < 2) return null
  const hidden = new Set(view.hiddenChroms)
  // swatches are only meaningful when the view is coloured by chromosome
  const effective = hasCells && view.focusCell === null ? view.overviewColor : layerMode
  const showSwatch = effective === 'rainbow' 
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
            <span className="swatch" style={{ background: showSwatch ? chromColor(c.name) : 'var(--text-muted)' }} />
            {c.name}
          </li>
        ))}
      </ul>
    </section>
  )
}

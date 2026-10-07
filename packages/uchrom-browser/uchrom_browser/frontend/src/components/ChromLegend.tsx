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
  // the colouring the active 3-D view draws its cells in full with: a pinned cell (or the
  // focused one) → the layer style there; all cells / a group → the overview colouring
  const drawnMode = useStore((s) => {
    const pane = s.workspace.panes.find((p) => p.id === s.workspace.activePane)
    const l = s.layers.find((x) => x.id === s.selectedLayerId) ?? s.layers.find((x) => x.datasetId === s.activeDatasetId && x.parentId === null)
    const layerMode = l ? effectiveStyle(l, pane).colorMode : undefined
    const many = ((s.activeDatasetId && s.cells[s.activeDatasetId]) || []).length > 1
    if (!many || (l && l.parentId !== null)) return layerMode // subsets keep their own colouring
    const scope = pane?.scope
    const oneCell = scope?.kind === 'cell' || (scope?.kind !== 'all' && scope?.kind !== 'group' && activeView(s).focusCell !== null)
    return oneCell ? layerMode : activeView(s).overviewColor
  })
  if (!ds || ds.chroms.length < 2) return null
  const hidden = new Set(view.hiddenChroms)
  // swatches are only meaningful when the view is coloured by chromosome
  const showSwatch = drawnMode === 'rainbow' 
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

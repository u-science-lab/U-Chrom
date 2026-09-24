import { describeFilter } from '../filters'
import { autoTubeRadius } from '../render/segments'
import { activeView, useStore } from '../store'
import { CellInfoPanel } from './CellInfoPanel'
import { colourableFields } from './format'
import { ChromLegend } from './ChromLegend'
import { PointsPanel } from './PointsPanel'
import type { ColorMode, RenderMode } from '../types'

export function PropertiesPanel() {
  const layer = useStore((s) => s.layers.find((l) => l.id === s.selectedLayerId))
  const setStyle = useStore((s) => s.setStyle)
  const view = useStore(activeView)
  const setOverviewColor = useStore((s) => s.setOverviewColor)
  const hasCells = useStore((s) => ((s.activeDatasetId && s.cells[s.activeDatasetId]) || []).length > 1)
  const allFields = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.cell_fields)
  const cellFields = colourableFields(allFields ?? [])
  const setCellField = useStore((s) => s.setCellField)
  if (!layer) {
    return (
      <aside className="props panel">
        <CellInfoPanel />
        <ChromLegend />
        <PointsPanel />
        <h2>Properties</h2>
        <p className="muted">Select a layer.</p>
      </aside>
    )
  }
  const st = layer.style
  const upd = (p: Partial<typeof st>) => setStyle(layer.id, p)
  const header = layer.geometry?.header
  // Multi-cell data has two colourings: the all-cells overview (per cell by
  // default) and the focused cell (layer style).  The buttons edit the one
  // currently on screen.
  const overview = hasCells && view.focusCell === null
  const colorMode: ColorMode = overview ? view.overviewColor : st.colorMode
  const setColor = (m: ColorMode) => {
    if (!overview) return upd({ colorMode: m })
    // 'Field' needs a field: default to the first one
    if (m === 'field' && !view.cellField && cellFields.length) return setCellField(cellFields[0].name)
    setOverviewColor(m)
  }
  const groups = new Map<string, typeof cellFields>()
  for (const f of cellFields) groups.set(f.group, [...(groups.get(f.group) ?? []), f])
  const groupLabel = (g: string) => (g === 'cell' ? 'Cell' : g === 'rna' ? 'RNA' : g)
  const colorChoices: [ColorMode, string][] = [
    ...(overview ? ([['cell', 'Cell']] as [ColorMode, string][]) : []),
    ...(overview && cellFields.length ? ([['field', 'Field']] as [ColorMode, string][]) : []),
    ['rainbow', overview ? 'Chrom' : 'Rainbow'],
    ['trace', 'Trace'],
    ['custom', 'Custom'],
  ]
  // what is actually drawn in full (focused cell, visible chromosomes)
  const hidden = new Set(view.hiddenChroms)
  const drawn = header?.segments.filter((s) => !hidden.has(s.chrom) && (view.focusCell === null || s.cell_id === view.focusCell))
  const autoR = layer.geometry ? autoTubeRadius(layer.geometry) : null

  return (
    <aside className="props panel">
      <CellInfoPanel />
      <ChromLegend />
      <PointsPanel />
      <h2>Style</h2>
      <div className="prop-title">{layer.name}</div>
      <div className="muted small">filter: {describeFilter(layer.filter)}</div>

      <label>Render as</label>
      <div className="seg">
        {(['line', 'tube', 'points'] as RenderMode[]).map((m) => (
          <button key={m} className={st.mode === m ? 'active' : ''} onClick={() => upd({ mode: m })}>
            {m}
          </button>
        ))}
      </div>

      <label>{overview ? 'Colour · all cells' : view.focusCell ? `Colour · cell ${view.focusCell}` : 'Colour'}</label>
      <div className="seg">
        {colorChoices.map(([m, label]) => (
          <button key={m} className={colorMode === m ? 'active' : ''} onClick={() => setColor(m)}>
            {label}
          </button>
        ))}
      </div>
      {colorMode === 'custom' && <input type="color" value={st.color} onChange={(e) => upd({ color: e.target.value })} />}
      {overview && colorMode === 'field' && (
        <select value={view.cellField ?? ''} onChange={(e) => setCellField(e.target.value)}>
          {[...groups].map(([g, fs]) => (
            <optgroup key={g} label={groupLabel(g)}>
              {fs.map((f) => (
                <option key={f.name} value={f.name}>
                  {f.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      )}

      <label>
        Opacity <span className="val">{st.opacity.toFixed(2)}</span>
      </label>
      <input type="range" min={0.05} max={1} step={0.05} value={st.opacity} onChange={(e) => upd({ opacity: +e.target.value })} />

      {st.mode === 'line' && (
        <>
          <label>
            Line width <span className="val">{st.lineWidth}px</span>
          </label>
          <input type="range" min={1} max={10} step={0.5} value={st.lineWidth} onChange={(e) => upd({ lineWidth: +e.target.value })} />
        </>
      )}
      {st.mode === 'tube' && (
        <>
          <label>
            Tube radius <span className="val">{st.tubeRadius === null ? `auto (${autoR?.toPrecision(3) ?? '—'})` : st.tubeRadius.toPrecision(3)}</span>
          </label>
          <div className="row">
            <input
              type="number"
              step="any"
              min={0}
              placeholder="auto"
              value={st.tubeRadius ?? ''}
              onChange={(e) => upd({ tubeRadius: e.target.value === '' ? null : Math.max(0, +e.target.value) })}
            />
            <button onClick={() => upd({ tubeRadius: null })} disabled={st.tubeRadius === null}>
              auto
            </button>
          </div>
          <label className="check">
            <input type="checkbox" checked={st.highQuality} onChange={(e) => upd({ highQuality: e.target.checked })} /> High quality
          </label>
        </>
      )}
      {st.mode === 'points' && (
        <>
          <label>
            Point size <span className="val">{st.pointSize}px</span>
          </label>
          <input type="range" min={1} max={20} step={1} value={st.pointSize} onChange={(e) => upd({ pointSize: +e.target.value })} />
        </>
      )}

      {header && (
        <dl className="stats">
          <dt>{view.focusCell ? `cell ${view.focusCell}` : 'shown'} points</dt>
          <dd>{drawn!.reduce((a, s) => a + s.n_points, 0).toLocaleString('en-US')}</dd>
          <dt>traces</dt>
          <dd>{new Set(drawn!.map((s) => s.trace_id)).size.toLocaleString('en-US')}</dd>
          <dt>chroms</dt>
          <dd>{new Set(drawn!.map((s) => s.chrom)).size}</dd>
          <dt className="muted">layer points</dt>
          <dd className="muted">{header.n_points.toLocaleString('en-US')}</dd>
        </dl>
      )}
      {header?.truncated && (
        <div className="warn">
          Truncated: showing {header.n_points.toLocaleString('en-US')} of {header.total_points.toLocaleString('en-US')} points. Create a subset to see
          everything.
        </div>
      )}
      {layer.error && <div className="error">{layer.error}</div>}
    </aside>
  )
}

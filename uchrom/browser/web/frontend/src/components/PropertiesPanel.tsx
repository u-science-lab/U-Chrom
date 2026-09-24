import { describeFilter } from '../filters'
import { AUTO_BOND_FACTOR, splitForView } from '../render/bonds'
import { autoTubeRadius, tubeAllowed } from '../render/segments'
import { activeView, useStore } from '../store'
import { CellInfoPanel } from './CellInfoPanel'
import { colourableFields } from './format'
import { FieldPicker, groupTitle } from './FieldPicker'
import { ChromLegend } from './ChromLegend'
import { PointsPanel } from './PointsPanel'
import type { ColorMode, RenderMode } from '../types'

export function PropertiesPanel() {
  const layer = useStore((s) => s.layers.find((l) => l.id === s.selectedLayerId))
  const setStyle = useStore((s) => s.setStyle)
  const view = useStore(activeView)
  const setMaxBond = useStore((s) => s.setMaxBond)
  const unit = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.xyz_unit ?? '')
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
  const setColor = (m: ColorMode) => (overview ? setOverviewColor(m) : upd({ colorMode: m }))
  // Cell fields are offered per group: "Gene" (rna.*), "Property" (area,
  // centroid, …) and any other prefix by name — one button each.
  const groups = new Map<string, typeof cellFields>()
  for (const f of cellFields) groups.set(f.group, [...(groups.get(f.group) ?? []), f])
  const activeGroup = colorMode === 'field' ? cellFields.find((f) => f.name === view.cellField)?.group : undefined
  const pickGroup = (g: string) => {
    const fs = groups.get(g) ?? []
    if (!fs.length) return
    // keep the current field if it is in this group, else the first one
    setCellField(fs.some((f) => f.name === view.cellField) ? view.cellField! : fs[0].name)
  }
  const colorChoices: [ColorMode, string][] = [
    ...(overview ? ([['cell', 'Cell']] as [ColorMode, string][]) : []),
    ['rainbow', overview ? 'Chrom' : 'Rainbow'],
    ['trace', 'Trace'],
    ['custom', 'Custom'],
  ]
  // what is actually drawn in full (focused cell, visible chromosomes)
  const hidden = new Set(view.hiddenChroms)
  const drawn = header?.segments.filter((s) => !hidden.has(s.chrom) && (view.focusCell === null || s.cell_id === view.focusCell))
  const autoR = layer.geometry ? autoTubeRadius(layer.geometry) : null
  // tube mode silently falls back to lines for big selections — say so here
  const drawnPoints = drawn ? drawn.reduce((a, s) => a + s.n_points, 0) : 0
  const tubeFallback =
    st.mode === 'tube' && header && drawn && !tubeAllowed({ ...header, n_segments: drawn.length, n_points: drawnPoints, segments: drawn }, st.highQuality)
      ? drawn.length
      : 0

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
      {tubeFallback && (
        <div className="note small">
          {hasCells && view.focusCell === null ? (
            <>
              All cells are drawn as <b>lines</b>: at this zoom a tube is thinner than a pixel, and {tubeFallback.toLocaleString('en-US')} traces exceed
              the tube budget. Select a cell to see tubes.
            </>
          ) : (
            <>
              Drawn as <b>lines</b>: {tubeFallback.toLocaleString('en-US')} traces exceed the tube budget. Create a subset or select a cell to see tubes.
            </>
          )}
        </div>
      )}

      <label>{overview ? 'Colour · all cells' : view.focusCell ? `Colour · cell ${view.focusCell}` : 'Colour'}</label>
      <div className="seg">
        {colorChoices.slice(0, overview ? 1 : 0).map(([m, label]) => (
          <button key={m} className={colorMode === m ? 'active' : ''} onClick={() => setColor(m)}>
            {label}
          </button>
        ))}
        {overview &&
          [...groups.keys()].map((g) => (
            <button key={g} className={activeGroup === g ? 'active' : ''} onClick={() => pickGroup(g)} title={`Colour cells by a ${groupTitle(g).toLowerCase()}`}>
              {groupTitle(g)}
            </button>
          ))}
        {colorChoices.slice(overview ? 1 : 0).map(([m, label]) => (
          <button key={m} className={colorMode === m ? 'active' : ''} onClick={() => setColor(m)}>
            {label}
          </button>
        ))}
      </div>
      {colorMode === 'custom' && <input type="color" value={st.color} onChange={(e) => upd({ color: e.target.value })} />}
      {overview && activeGroup && (
        <FieldPicker
          key={activeGroup}
          fields={groups.get(activeGroup) ?? []}
          value={view.cellField}
          placeholder={`search ${groupTitle(activeGroup).toLowerCase()}…`}
          onPick={setCellField}
        />
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

      {layer.geometry && st.mode !== 'points' && (
        <MaxBond
          setting={view.maxBond}
          split={splitForView(layer.geometry, view.maxBond)}
          unit={unit}
          onChange={setMaxBond}
        />
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

/** "Max bond": cut polylines where consecutive spots are far apart. */
function MaxBond({
  setting,
  split,
  unit,
  onChange,
}: {
  setting: 'auto' | number | null
  split: { threshold: number | null; broken: number }
  unit: string
  onChange: (v: 'auto' | number | null) => void
}) {
  const shown =
    setting === null ? 'off' : `${setting === 'auto' ? `auto (${AUTO_BOND_FACTOR}× median) ` : ''}${split.threshold?.toPrecision(3) ?? '—'} ${unit}`
  return (
    <>
      <label title="Consecutive spots farther apart than this are not connected (unassigned spots, duplicated loci)">
        Max bond <span className="val">{shown}</span>
      </label>
      <div className="row">
        <input
          type="number"
          step="any"
          min={0}
          placeholder={setting === null ? 'off' : 'auto'}
          value={typeof setting === 'number' ? setting : ''}
          onChange={(e) => onChange(e.target.value === '' ? 'auto' : Math.max(0, +e.target.value))}
        />
        <button onClick={() => onChange('auto')} disabled={setting === 'auto'}>
          auto
        </button>
        <button onClick={() => onChange(null)} disabled={setting === null}>
          off
        </button>
      </div>
      {setting !== null && <div className="muted small">{split.broken.toLocaleString('en-US')} long bonds cut</div>}
    </>
  )
}

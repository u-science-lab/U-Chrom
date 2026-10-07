import { labelColorMap, rgbCss } from '../colors'
import { labelCounts } from '../render/points'
import { activeView, useStore } from '../store'

/**
 * Point sets (e.g. nascent RNA spots): show/hide, per-label legend with the
 * marker colours, and marker size.  Labels toggle on click, solo on double-click.
 */
export function PointsPanel() {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const loaded = useStore((s) => (s.activeDatasetId ? s.pointSets[s.activeDatasetId] : undefined))
  const view = useStore(activeView)
  const toggleSet = useStore((s) => s.togglePointSet)
  const toggleLabel = useStore((s) => s.toggleLabel)
  const setHiddenLabels = useStore((s) => s.setHiddenLabels)
  const setSize = useStore((s) => s.setPointSize)
  const infos = ds?.point_sets ?? []
  if (!infos.length) return null
  return (
    <section className="points-panel">
      {infos.map((info) => {
        const ps = loaded?.[info.name]
        const labels = ps ? labelCounts(ps) : info.labels
        const hidden = new Set(view.hiddenLabels[info.name] ?? [])
        const off = view.hiddenPointSets.includes(info.name)
        const names = labels.map((l) => l.value)
        const colorOf = labelColorMap(names) // same order as the markers
        return (
          <div key={info.name}>
            <h2>
              <label className="check">
                <input type="checkbox" checked={!off} onChange={() => toggleSet(info.name)} /> {info.name} points
                <span className="muted"> {info.n_points.toLocaleString('en-US')}</span>
              </label>
              <span className="legend-actions">
                <button onClick={() => setHiddenLabels(info.name, [])} disabled={!hidden.size}>
                  all
                </button>
                <button onClick={() => setHiddenLabels(info.name, names)} disabled={hidden.size === names.length}>
                  none
                </button>
              </span>
            </h2>
            {!ps && <div className="muted small">loading…</div>}
            {!off && (
              <ul className="legend-list labels">
                {labels.map((l) => (
                  <li
                    key={l.value}
                    className={hidden.has(l.value) ? 'off' : ''}
                    onClick={() => toggleLabel(info.name, l.value)}
                    onDoubleClick={() => setHiddenLabels(info.name, names.filter((n) => n !== l.value))}
                    title={`${l.count} spots · click to show/hide · double-click to show only this one`}
                  >
                    <span className="swatch round" style={{ background: rgbCss(colorOf(l.value)) }} />
                    <span className="name">{l.value || '(none)'}</span>
                    <span className="muted count">{l.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
      <label>
        Marker size <span className="val">{view.pointSize}px</span>
      </label>
      <input type="range" min={2} max={16} step={1} value={view.pointSize} onChange={(e) => setSize(+e.target.value)} />
    </section>
  )
}

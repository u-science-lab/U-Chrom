import { describeFilter } from '../filters'
import { autoTubeRadius } from '../render/segments'
import { useStore } from '../store'
import type { ColorMode, RenderMode } from '../types'

export function PropertiesPanel() {
  const layer = useStore((s) => s.layers.find((l) => l.id === s.selectedLayerId))
  const setStyle = useStore((s) => s.setStyle)
  if (!layer) {
    return (
      <aside className="props panel">
        <h2>Properties</h2>
        <p className="muted">Select a layer.</p>
      </aside>
    )
  }
  const st = layer.style
  const upd = (p: Partial<typeof st>) => setStyle(layer.id, p)
  const header = layer.geometry?.header
  const autoR = layer.geometry ? autoTubeRadius(layer.geometry) : null

  return (
    <aside className="props panel">
      <h2>Properties</h2>
      <div className="prop-title">{layer.name}</div>
      <div className="muted small">filter: {describeFilter(layer.filter)}</div>

      <label>Style</label>
      <div className="seg">
        {(['line', 'tube', 'points'] as RenderMode[]).map((m) => (
          <button key={m} className={st.mode === m ? 'active' : ''} onClick={() => upd({ mode: m })}>
            {m}
          </button>
        ))}
      </div>

      <label>Colour</label>
      <div className="seg">
        {([
          ['rainbow', 'Rainbow'],
          ['custom', 'Custom'],
          ['trace', 'Per trace'],
        ] as [ColorMode, string][]).map(([m, label]) => (
          <button key={m} className={st.colorMode === m ? 'active' : ''} onClick={() => upd({ colorMode: m })}>
            {label}
          </button>
        ))}
      </div>
      {st.colorMode === 'custom' && <input type="color" value={st.color} onChange={(e) => upd({ color: e.target.value })} />}

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
          <dt>points</dt>
          <dd>{header.n_points.toLocaleString('en-US')}</dd>
          <dt>segments</dt>
          <dd>{header.n_segments.toLocaleString('en-US')}</dd>
          <dt>chroms</dt>
          <dd>{new Set(header.segments.map((s) => s.chrom)).size}</dd>
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

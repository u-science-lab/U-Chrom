import { useStore } from '../store'
import { layerShownIn } from '../workspace'

export function StatusBar() {
  const status = useStore((s) => s.status)
  const error = useStore((s) => s.error)
  const setError = useStore((s) => s.setError)
  const layers = useStore((s) => s.layers)
  const activeId = useStore((s) => s.activeDatasetId)
  // the layers the active 3-D view draws
  const pane = useStore((s) => s.workspace.panes.find((p) => p.id === s.workspace.activePane))
  const shown = layers.filter((l) => l.datasetId === activeId && l.geometry && layerShownIn(l, pane))
  const points = shown.reduce((acc, l) => acc + l.geometry!.header.n_points, 0)
  const loading = layers.some((l) => l.loading)
  const truncated = shown.some((l) => l.geometry!.header.truncated)
  return (
    <footer className="statusbar">
      <span>
        {points.toLocaleString('en-US')} points in {shown.length} visible layer{shown.length === 1 ? '' : 's'}
      </span>
      {loading && <span><span className="spinner small" aria-hidden /> loading…</span>}
      {truncated && <span className="warn">some layers are truncated</span>}
      {status && <span className="warn">{status}</span>}
      {error && (
        <span className="error" onClick={() => setError(null)} title="Click to dismiss">
          {error} ✕
        </span>
      )}
    </footer>
  )
}

import { useState } from 'react'
import { treeOrder } from '../layers'
import { useStore } from '../store'
import { layerInPane, toggleLayerInPane } from '../workspace'

export function LayerPanel() {
  const activeId = useStore((s) => s.activeDatasetId)
  const all = useStore((s) => s.layers)
  const selected = useStore((s) => s.selectedLayerId)
  const select = useStore((s) => s.selectLayer)
  // the active 3-D view: its own subsets, and what it shows / hides
  const pane = useStore((s) => s.workspace.panes.find((p) => p.id === s.workspace.activePane))
  const setWorkspace = useStore((s) => s.setWorkspace)
  const rename = useStore((s) => s.renameLayer)
  const remove = useStore((s) => s.removeLayer)
  const [editing, setEditing] = useState<string | null>(null)
  const rows = treeOrder(all.filter((l) => l.datasetId === activeId && layerInPane(l, pane)))
  const shownHere = (name: string) => !pane?.hiddenLayers?.includes(name)

  return (
    <section className="panel">
      <h2>Layers</h2>
      {!rows.length && <p className="muted">Open a dataset to start.</p>}
      <ul className="layer-list">
        {rows.map(({ layer, depth }) => (
          <li
            key={layer.id}
            className={layer.id === selected ? 'selected' : ''}
            style={{ paddingLeft: 6 + depth * 14 }}
            onClick={() => select(layer.id)}
          >
            <button
              className={`eye ${shownHere(layer.name) ? 'on' : ''}`}
              title={shownHere(layer.name) ? 'Hide in this view' : 'Show in this view'}
              onClick={(e) => {
                e.stopPropagation()
                if (pane) setWorkspace((w) => toggleLayerInPane(w, pane.id, layer.name))
              }}
            >
              {shownHere(layer.name) ? '●' : '○'}
            </button>
            {editing === layer.id ? (
              <input
                className="rename"
                autoFocus
                defaultValue={layer.name}
                onClick={(e) => e.stopPropagation()}
                onBlur={(e) => {
                  rename(layer.id, e.target.value)
                  setEditing(null)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                  if (e.key === 'Escape') setEditing(null)
                }}
              />
            ) : (
              <span className="name" title="Double-click to rename" onDoubleClick={() => setEditing(layer.id)}>
                {layer.name}
              </span>
            )}
            <span className="layer-state">
              {layer.loading ? '…' : layer.error ? '!' : layer.geometry ? layer.geometry.header.n_points.toLocaleString('en-US') : ''}
            </span>
            <button
              className="del"
              title={layer.parentId ? 'Delete layer and its children' : 'Delete layer'}
              onClick={(e) => {
                e.stopPropagation()
                remove(layer.id)
              }}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

import { useState } from 'react'
import { treeOrder } from '../layers'
import { useStore } from '../store'

export function LayerPanel() {
  const activeId = useStore((s) => s.activeDatasetId)
  const all = useStore((s) => s.layers)
  const selected = useStore((s) => s.selectedLayerId)
  const select = useStore((s) => s.selectLayer)
  const setVisible = useStore((s) => s.setVisible)
  const rename = useStore((s) => s.renameLayer)
  const remove = useStore((s) => s.removeLayer)
  const [editing, setEditing] = useState<string | null>(null)
  const rows = treeOrder(all.filter((l) => l.datasetId === activeId))

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
              className={`eye ${layer.visible ? 'on' : ''}`}
              title={layer.visible ? 'Hide' : 'Show'}
              onClick={(e) => {
                e.stopPropagation()
                setVisible(layer.id, !layer.visible)
              }}
            >
              {layer.visible ? '●' : '○'}
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

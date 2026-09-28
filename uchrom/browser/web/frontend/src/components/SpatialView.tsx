import { useEffect, useMemo, useState } from 'react'
import { fetchSpatial, imageUrl } from '../api'
import { useStore } from '../store'
import type { Embedding, SpatialInfo, SpatialPoints, SpatialRegion } from '../types'
import { updatePane, type Pane } from '../workspace'
import { EmbeddingStyleControls, EmbeddingView, type ScatterSource } from './EmbeddingView'

/** The position set and region a Spatial pane shows, resolved against the dataset (first ones by default). */
export function resolveSpatial(list: SpatialInfo[], pane: Pane): { info: SpatialInfo | undefined; region: SpatialRegion | null } {
  const info = list.find((s) => s.key === pane.spatialKey) ?? list[0]
  const region = info?.regions.find((r) => r.name === pane.region) ?? info?.regions[0] ?? null
  return { info, region }
}

function useSpatialList(): SpatialInfo[] {
  return useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.spatial) ?? []
}

/**
 * Cells where they are in the tissue: one region (section / FOV) of a
 * cell-position set, to scale, over the region's image when it has one.
 * Colouring, lasso, zoom and focus work as in the Embedding view.
 */
export function SpatialView({ pane }: { pane: Pane }) {
  const dsId = useStore((s) => s.activeDatasetId)
  const list = useSpatialList()
  const { info, region } = resolveSpatial(list, pane)
  const [pts, setPts] = useState<SpatialPoints | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setPts(null)
    if (!dsId || !info) return
    let live = true
    setError(null)
    fetchSpatial(dsId, info.key, region?.name ?? null)
      .then((p) => live && setPts(p))
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
  }, [dsId, info?.key, region?.name, info])
  const data = useMemo<Embedding | null>(() => {
    if (!pts) return null
    const u = pts.unit ? ` (${pts.unit})` : ''
    return { key: pts.key, label: pts.region ?? pts.key, cell_ids: pts.cell_ids, x: pts.x, y: pts.y, axis_labels: [`x${u}`, `y${u}`] }
  }, [pts])
  const opacity = pane.imageOpacity ?? 1
  const source: ScatterSource = {
    data,
    error,
    yDown: (pts?.y_axis ?? info?.y_axis) === 'down',
    extent: pts?.image?.extent ?? null,
    image: pts?.image && dsId ? { url: imageUrl(dsId, pts.image.name), extent: pts.image.extent, opacity } : null,
    empty: list.length ? 'Loading positions…' : 'This dataset has no cell positions (cd.set_cell_positions).',
  }
  return <EmbeddingView pane={pane} source={source} />
}

/** Region picker with previous / next buttons (pane header and inspector). */
export function RegionPicker({ pane }: { pane: Pane }) {
  const setWorkspace = useStore((s) => s.setWorkspace)
  const list = useSpatialList()
  const { info, region } = resolveSpatial(list, pane)
  if (!info || info.regions.length < 2) return null
  const names = info.regions.map((r) => r.name)
  const i = region ? names.indexOf(region.name) : 0
  const go = (name: string) => setWorkspace((ws) => updatePane(ws, pane.id, { region: name }))
  return (
    <span className="region-picker">
      <button onClick={() => go(names[(i - 1 + names.length) % names.length])} title="Previous section">
        ‹
      </button>
      <select value={region?.name ?? ''} onChange={(e) => go(e.target.value)} title="Section / field of view shown">
        {info.regions.map((r) => (
          <option key={r.name} value={r.name}>
            {r.name} · {r.n_cells.toLocaleString('en-US')}
            {r.image ? ' · image' : ''}
          </option>
        ))}
      </select>
      <button onClick={() => go(names[(i + 1) % names.length])} title="Next section">
        ›
      </button>
    </span>
  )
}

/** Inspector: which positions and section, the image, then the point style (as in the Embedding view). */
export function SpatialControls({ pane }: { pane: Pane }) {
  const setWorkspace = useStore((s) => s.setWorkspace)
  const list = useSpatialList()
  const { info, region } = resolveSpatial(list, pane)
  const set = (patch: Partial<Pane>) => setWorkspace((ws) => updatePane(ws, pane.id, patch))
  if (!info) return <p className="muted">This dataset has no cell positions.</p>
  const opacity = pane.imageOpacity ?? 1
  return (
    <div className="emb-style">
      {list.length > 1 && (
        <div className="emb-row" title="Which cell positions (cd.cell_positions key)">
          <span className="emb-lab">positions</span>
          <div className="emb-ctl">
            <select value={info.key} onChange={(e) => set({ spatialKey: e.target.value, region: null })}>
              {list.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.key}
                  {s.unit ? ` (${s.unit})` : ''}
                  {s.n_images ? ' · images' : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
      <div className="emb-row">
        <span className="emb-lab">section</span>
        <div className="emb-ctl">
          <RegionPicker pane={pane} />
          {info.regions.length < 2 && <span>{region?.name ?? '—'}</span>}
        </div>
      </div>
      {region?.image ? (
        <div className="emb-row" title="Opacity of the section image (0 hides it)">
          <span className="emb-lab">image</span>
          <div className="emb-ctl emb-slider">
            <input type="range" min={0} max={1} step={0.05} value={opacity} onChange={(e) => set({ imageOpacity: +e.target.value })} />
            <span className="val">{opacity.toFixed(2)}</span>
          </div>
        </div>
      ) : (
        info.n_images > 0 && <div className="muted small emb-note">no image for this section</div>
      )}
      {info.status === 'inferred' && <div className="muted small emb-note">inferred positions{info.source ? ` (${info.source})` : ''}</div>}
      <EmbeddingStyleControls pane={pane} />
    </div>
  )
}

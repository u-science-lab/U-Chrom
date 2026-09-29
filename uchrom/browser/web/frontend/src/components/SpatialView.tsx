import { useEffect, useMemo, useState } from 'react'
import { fetchSpatial, imageUrl } from '../api'
import { useStore } from '../store'
import type { Embedding, SpatialInfo, SpatialPoints, SpatialRegion } from '../types'
import { updatePane, type Pane } from '../workspace'
import { usePaneScope, useScopeCells } from '../useGroups'
import { EmbeddingStyleControls, EmbeddingView, type ScatterSource } from './EmbeddingView'
import { Select } from './Select'

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
 * The region to show for the cells in focus: the one holding most of them,
 * or null when the current region already holds some (or none has any).
 * Pure — tested.
 */
export function regionToFollow(regions: (string | null)[], ids: string[], cells: ReadonlySet<string> | null, current: string | null): string | null {
  if (!cells || !cells.size) return null
  const counts = new Map<string, number>()
  ids.forEach((id, i) => {
    const r = regions[i]
    if (r !== null && cells.has(id)) counts.set(r, (counts.get(r) ?? 0) + 1)
  })
  if (!counts.size || (current !== null && counts.has(current))) return null
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0]
}

/**
 * Cells where they are in the tissue: one region (section / FOV) of a
 * cell-position set, to scale, over the region's image when it has one.
 * Colouring, lasso, zoom and focus work as in the Embedding view.  The
 * positions of every region are loaded once; when the focused cell / group
 * is in another region the view follows it there.
 */
export function SpatialView({ pane }: { pane: Pane }) {
  const dsId = useStore((s) => s.activeDatasetId)
  const setWorkspace = useStore((s) => s.setWorkspace)
  const list = useSpatialList()
  const { info, region } = resolveSpatial(list, pane)
  const [all, setAll] = useState<SpatialPoints | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setAll(null)
    if (!dsId || !info) return
    let live = true
    setError(null)
    fetchSpatial(dsId, info.key, null)
      .then((p) => live && setAll(p))
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dsId, info?.key])
  // the region's cells
  const data = useMemo<Embedding | null>(() => {
    if (!all) return null
    const keep = all.regions && region ? all.regions.map((r) => r === region.name) : null
    const pick = <T,>(v: T[]) => (keep ? v.filter((_, i) => keep[i]) : v)
    const u = all.unit ? ` (${all.unit})` : ''
    return { key: all.key, label: region?.name ?? all.key, cell_ids: pick(all.cell_ids), x: pick(all.x), y: pick(all.y), axis_labels: [`x${u}`, `y${u}`] }
  }, [all, region])
  // follow the focus into another region (only when the focus changes, so picking a region by hand sticks)
  const scope = usePaneScope(pane)
  const scopeCells = useScopeCells(scope)
  useEffect(() => {
    if (!all?.regions) return
    const to = regionToFollow(all.regions, all.cell_ids, scopeCells, region?.name ?? null)
    if (to) setWorkspace((ws) => updatePane(ws, pane.id, { region: to }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeCells, all])
  const image = region && all?.images ? (all.images[region.name] ?? null) : null
  const opacity = pane.imageOpacity ?? 1
  const source: ScatterSource = {
    data,
    error,
    yDown: (all?.y_axis ?? info?.y_axis) === 'down',
    extent: null, // fit the spots (an image may reach far beyond the measured area); the image is drawn at its extent
    image: image && dsId ? { url: imageUrl(dsId, image.name), extent: image.extent, opacity } : null,
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
      <Select value={region?.name ?? ''} onChange={(e) => go(e.target.value)} title="Section / field of view shown">
        {info.regions.map((r) => (
          <option key={r.name} value={r.name}>
            {r.name} · {r.n_cells.toLocaleString('en-US')}
            {r.image ? ' · image' : ''}
          </option>
        ))}
      </Select>
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
            <Select value={info.key} onChange={(e) => set({ spatialKey: e.target.value, region: null })}>
              {list.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.key}
                  {s.unit ? ` (${s.unit})` : ''}
                  {s.n_images ? ' · images' : ''}
                </option>
              ))}
            </Select>
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

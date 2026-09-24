import { create } from 'zustand'
import { DEFAULT_STYLE, removeCascade, uniqueName } from './layers'
import type { CellInfo, DatasetSummary, Geometry, Layer, LayerFilter, LayerStyle, PickInfo } from './types'

let nextId = 1
const newId = () => `L${nextId++}`

/**
 * Per-dataset display state.  These are *view* settings, not layers: they
 * change what is drawn and where the camera looks, never the data layers.
 */
export interface DatasetView {
  /** cell drawn in full; others become faint context.  null = all cells */
  focusCell: string | null
  hiddenChroms: string[]
  /** opacity of the non-focused cells (0 hides them) */
  contextOpacity: number
}

export const DEFAULT_VIEW: DatasetView = { focusCell: null, hiddenChroms: [], contextOpacity: 0.15 }

export interface AppState {
  datasets: DatasetSummary[]
  activeDatasetId: string | null
  layers: Layer[]
  selectedLayerId: string | null
  pick: PickInfo | null
  status: string | null
  error: string | null
  /** bumped to ask the viewport to refit the camera */
  resetViewToken: number
  /** bumped to ask the viewport to fly to the current focus */
  flyToken: number
  views: Record<string, DatasetView>
  /** cell table per dataset, natural order (empty when no cell_id) */
  cells: Record<string, CellInfo[]>

  setDatasets(ds: DatasetSummary[]): void
  addDataset(ds: DatasetSummary): void
  removeDataset(id: string): void
  setActiveDataset(id: string | null): void
  addLayer(opts: { datasetId: string; parentId: string | null; name: string; filter: LayerFilter; style?: Partial<LayerStyle> }): string
  removeLayer(id: string): void
  renameLayer(id: string, name: string): void
  setVisible(id: string, visible: boolean): void
  setStyle(id: string, style: Partial<LayerStyle>): void
  setLoading(id: string): void
  setGeometry(id: string, geometry: Geometry): void
  setLayerError(id: string, error: string): void
  selectLayer(id: string | null): void
  setPick(pick: PickInfo | null): void
  setStatus(msg: string | null): void
  setError(msg: string | null): void
  resetView(): void
  setCells(datasetId: string, cells: CellInfo[]): void
  focusCell(cellId: string | null): void
  stepCell(delta: number): void
  toggleChrom(chrom: string): void
  setHiddenChroms(chroms: string[]): void
  setContextOpacity(opacity: number): void
}

/** View state of the active dataset (defaults when none recorded). */
export function activeView(s: Pick<AppState, 'views' | 'activeDatasetId'>): DatasetView {
  return (s.activeDatasetId && s.views[s.activeDatasetId]) || DEFAULT_VIEW
}

const patchLayer = (layers: Layer[], id: string, patch: Partial<Layer>) =>
  layers.map((l) => (l.id === id ? { ...l, ...patch } : l))

export const useStore = create<AppState>((set, get) => {
  const patchView = (patch: Partial<DatasetView>, extra: Partial<AppState> = {}) => {
    const s = get()
    const id = s.activeDatasetId
    if (!id) return
    set({ views: { ...s.views, [id]: { ...activeView(s), ...patch } }, ...extra })
  }
  return {
  datasets: [],
  activeDatasetId: null,
  layers: [],
  selectedLayerId: null,
  pick: null,
  status: null,
  error: null,
  resetViewToken: 0,
  flyToken: 0,
  views: {},
  cells: {},

  setDatasets(ds) {
    // Create a root layer for every dataset that doesn't have one yet.
    const s = get()
    set({ datasets: ds })
    for (const d of ds) {
      if (!s.layers.some((l) => l.datasetId === d.id)) get().addDataset(d)
    }
    if (!get().activeDatasetId && ds.length) set({ activeDatasetId: ds[0].id })
  },

  addDataset(ds) {
    const s = get()
    const datasets = s.datasets.some((d) => d.id === ds.id)
      ? s.datasets.map((d) => (d.id === ds.id ? ds : d))
      : [...s.datasets, ds]
    set({ datasets, activeDatasetId: ds.id })
    if (!get().layers.some((l) => l.datasetId === ds.id && l.parentId === null)) {
      // Imaging data: tubes for the focused cell; the crowded overview falls
      // back to lines automatically.
      const style: Partial<LayerStyle> = ds.trace_mode ? { mode: 'tube' } : {}
      const id = get().addLayer({ datasetId: ds.id, parentId: null, name: ds.name, filter: {}, style })
      set({ selectedLayerId: id, resetViewToken: get().resetViewToken + 1 })
    }
  },

  removeDataset(id) {
    const s = get()
    const layers = s.layers.filter((l) => l.datasetId !== id)
    const datasets = s.datasets.filter((d) => d.id !== id)
    set({
      datasets,
      layers,
      activeDatasetId: s.activeDatasetId === id ? (datasets[0]?.id ?? null) : s.activeDatasetId,
      selectedLayerId: layers.some((l) => l.id === s.selectedLayerId) ? s.selectedLayerId : null,
      pick: null,
    })
  },

  setActiveDataset(id) {
    const root = get().layers.find((l) => l.datasetId === id && l.parentId === null)
    set({ activeDatasetId: id, selectedLayerId: root?.id ?? null, pick: null })
  },

  addLayer({ datasetId, parentId, name, filter, style }) {
    const id = newId()
    const layers = get().layers
    const layer: Layer = {
      id,
      name: uniqueName(layers.filter((l) => l.datasetId === datasetId), name),
      datasetId,
      parentId,
      filter,
      visible: true,
      style: { ...DEFAULT_STYLE, ...style },
      geometry: null,
      loading: false,
      error: null,
    }
    // A new subset hides its parent, like the desktop browser.
    const next = parentId ? patchLayer(layers, parentId, { visible: false }) : layers
    set({ layers: [...next, layer], selectedLayerId: id })
    return id
  },

  removeLayer(id) {
    const s = get()
    const layers = removeCascade(s.layers, id)
    set({
      layers,
      selectedLayerId: layers.some((l) => l.id === s.selectedLayerId) ? s.selectedLayerId : null,
      pick: s.pick && layers.some((l) => l.id === s.pick!.layerId) ? s.pick : null,
    })
  },

  renameLayer(id, name) {
    const trimmed = name.trim()
    if (trimmed) set({ layers: patchLayer(get().layers, id, { name: trimmed }) })
  },

  setVisible(id, visible) {
    set({ layers: patchLayer(get().layers, id, { visible }) })
  },

  setStyle(id, style) {
    set({
      layers: get().layers.map((l) => (l.id === id ? { ...l, style: { ...l.style, ...style } } : l)),
    })
  },

  setLoading(id) {
    set({ layers: patchLayer(get().layers, id, { loading: true, error: null }) })
  },

  setGeometry(id, geometry) {
    const s = get()
    const layer = s.layers.find((l) => l.id === id)
    // A new subset's first geometry refits the camera onto it (its parent is
    // hidden by then); restyling or reloading an existing layer does not.
    const refit = !!layer && layer.parentId !== null && layer.geometry === null
    set({
      layers: patchLayer(s.layers, id, { geometry, loading: false, error: null }),
      ...(refit ? { resetViewToken: s.resetViewToken + 1 } : {}),
    })
  },

  setLayerError(id, error) {
    set({ layers: patchLayer(get().layers, id, { loading: false, error }) })
  },

  selectLayer(id) {
    set({ selectedLayerId: id })
  },
  setPick(pick) {
    set({ pick })
  },
  setStatus(status) {
    set({ status })
  },
  setError(error) {
    set({ error })
  },
  resetView() {
    set({ resetViewToken: get().resetViewToken + 1 })
  },
  setCells(datasetId, cells) {
    set({ cells: { ...get().cells, [datasetId]: cells } })
  },
  focusCell(cellId) {
    const s = get()
    if (activeView(s).focusCell === cellId) return
    patchView({ focusCell: cellId }, { pick: null, flyToken: s.flyToken + 1 })
  },
  stepCell(delta) {
    const s = get()
    const list = (s.activeDatasetId && s.cells[s.activeDatasetId]) || []
    if (!list.length) return
    const cur = list.findIndex((c) => c.cell_id === activeView(s).focusCell)
    const next = cur < 0 ? (delta > 0 ? 0 : list.length - 1) : (cur + delta + list.length) % list.length
    get().focusCell(list[next].cell_id)
  },
  toggleChrom(chrom) {
    const hidden = new Set(activeView(get()).hiddenChroms)
    if (hidden.has(chrom)) hidden.delete(chrom)
    else hidden.add(chrom)
    patchView({ hiddenChroms: [...hidden] })
  },
  setHiddenChroms(chroms) {
    patchView({ hiddenChroms: [...chroms] })
  },
  setContextOpacity(contextOpacity) {
    patchView({ contextOpacity })
  },
  }
})

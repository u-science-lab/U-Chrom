import { create } from 'zustand'
import { setGroupResolver } from './api'
import { groupColor, nextGroupName, parseSavedGroups, removeGroup, renameGroup, upsertGroup, type GroupRef, type SavedGroup, type Selection } from './groups'
import { DEFAULT_STYLE, removeCascade, uniqueName } from './layers'
import { applyTheme, loadThemeChoice, resolveTheme, saveThemeChoice, systemPrefersDark, type Palette, type ThemeChoice } from './theme'
import { isPointPick } from './types'
import type { Locus } from './genome'
import { addPinnedPane, defaultWorkspace, dropGroupScope, paneSignature, parseWorkspace, type DataKind, type WorkspaceState } from './workspace'
import type { CellField, CellInfo, CellValue, ColorMode, DatasetSummary, Geometry, Layer, LayerFilter, LayerStyle, PickInfo, PointSet } from './types'

let nextId = 1
const newId = () => `L${nextId++}`

/**
 * Per-dataset display state.  These are *view* settings, not layers: they
 * change what is drawn and where the camera looks, never the data layers.
 */
export interface DatasetView {
  /** cell drawn in full; others become faint context.  null = all cells */
  focusCell: string | null
  /** group in focus instead of one cell (its cells drawn in full, views
   *  following the focus aggregate over it); exclusive with focusCell */
  focusGroup: GroupRef | null
  /** current lasso selection (registered, not saved as a named group yet) */
  selection: Selection | null
  hiddenChroms: string[]
  /** opacity of the non-focused cells (0 hides them) */
  contextOpacity: number
  /** colouring of the all-cells overview (and the faint context); a focused cell uses the layer style */
  overviewColor: ColorMode
  /** cell field (numeric or categorical) used when overviewColor is 'field' */
  cellField: string | null
  /** categories of a categorical cellField switched off in the legend */
  hiddenCategories: string[]
  /** cell list order: natural id order or by the field value (descending) */
  cellSort: 'id' | 'value'
  /** point sets switched off */
  hiddenPointSets: string[]
  /** hidden labels per point set (e.g. genes) */
  hiddenLabels: Record<string, string[]>
  /** point sprite size in px */
  pointSize: number
  /** cut bonds longer than this ('auto' = 10 × median bond, null = never) */
  maxBond: 'auto' | number | null
  /** genomic window shared by the tracks / matrix / stats panes (null → default) */
  locus: Locus | null
}

export const DEFAULT_VIEW: DatasetView = {
  focusCell: null,
  focusGroup: null,
  selection: null,
  hiddenChroms: [],
  contextOpacity: 0.15,
  overviewColor: 'cell',
  cellField: null,
  hiddenCategories: [],
  cellSort: 'id',
  hiddenPointSets: [],
  hiddenLabels: {},
  pointSize: 7,
  maxBond: 'auto',
  locus: null,
}

/** Whether a dataset has 3-D coordinates to draw (scHi-C without a model has none). */
export function hasCoords(ds: Pick<DatasetSummary, 'has_coords' | 'n_spots'> | undefined): boolean {
  return !!ds && ds.has_coords !== false && ds.n_spots > 0
}

/**
 * The categorical field a dataset is best summarised by: `cell_type`, else
 * the first category field whose name mentions a type or cluster.
 */
export function defaultCategoryField(ds: Pick<DatasetSummary, 'cell_fields'> | undefined): CellField | null {
  const cats = (ds?.cell_fields ?? []).filter((f) => f.kind === 'category')
  return cats.find((f) => f.name === 'cell_type') ?? cats.find((f) => /type|cluster/i.test(f.name)) ?? null
}

/** Initial view of a dataset: coloured by its cell type when it has one. */
export function initialView(ds: DatasetSummary): DatasetView {
  const f = defaultCategoryField(ds)
  return f ? { ...DEFAULT_VIEW, overviewColor: 'field', cellField: f.name } : DEFAULT_VIEW
}

/** Key of a cached cell-field vector. */
export const fieldKey = (datasetId: string, field: string) => `${datasetId}\u0000${field}`

const WS_KEY = 'uchrom.browser.workspace'
const GROUPS_KEY = 'uchrom.browser.groups'

/** Saved cell groups per dataset name (per viewer; storage may be unavailable). */
export function loadSavedGroups(): Record<string, SavedGroup[]> {
  try {
    const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(GROUPS_KEY) : null
    return raw ? parseSavedGroups(JSON.parse(raw)) : {}
  } catch {
    return {}
  }
}

function persistGroups(groups: Record<string, SavedGroup[]>) {
  try {
    localStorage.setItem(GROUPS_KEY, JSON.stringify(groups))
  } catch {
    /* private mode / blocked storage: groups last for this session only */
  }
}

/** Saved workspace (per viewer; storage may be unavailable or hold junk). */
export function loadWorkspace(): WorkspaceState | null {
  try {
    localStorage.removeItem('uchrom.browser.ui') // pre-workspace float/tab/split prefs
    const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(WS_KEY) : null
    return raw ? parseWorkspace(JSON.parse(raw)) : null
  } catch {
    return null
  }
}

function saveWorkspace(ws: WorkspaceState) {
  try {
    localStorage.setItem(WS_KEY, JSON.stringify(ws))
  } catch {
    /* private mode / blocked storage: layout just doesn't persist */
  }
}

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
  /** cached cell-field values: fieldKey(ds, field) → cell_id → value */
  cellValues: Record<string, Map<string, CellValue>>
  /** loaded point sets per dataset */
  pointSets: Record<string, Record<string, PointSet>>

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
  /** views laid out as equal panes */
  workspace: WorkspaceState
  /** false until the user changes the layout (or one was saved): until then
   *  the default follows the data (with / without embeddings) */
  workspaceTouched: boolean
  /** apply the data-dependent default unless the user has a layout */
  ensureDefaultWorkspace(kind: boolean | DataKind): void
  /** replace the workspace (used by the pane actions); persists it */
  setWorkspace(update: (ws: WorkspaceState) => WorkspaceState): void
  /** open `cell` in a new view pinned to it (3-D, or Genome without coordinates) */
  openCellView(cell: string): void
  setCells(datasetId: string, cells: CellInfo[]): void
  focusCell(cellId: string | null): void
  stepCell(delta: number): void
  toggleChrom(chrom: string): void
  setHiddenChroms(chroms: string[]): void
  setContextOpacity(opacity: number): void
  setOverviewColor(mode: ColorMode): void
  /** colour the overview by `field` (switches overviewColor to 'field') */
  setCellField(field: string | null): void
  setCellSort(sort: 'id' | 'value'): void
  setCellValues(datasetId: string, field: string, values: Map<string, CellValue>): void
  toggleCategory(value: string): void
  setHiddenCategories(values: string[]): void
  setPointSet(datasetId: string, set: PointSet): void
  togglePointSet(name: string): void
  toggleLabel(set: string, label: string): void
  setHiddenLabels(set: string, labels: string[]): void
  setPointSize(px: number): void
  setMaxBond(v: 'auto' | number | null): void
  setLocus(locus: Locus): void
  /** named cell groups per dataset name (persisted in the browser) */
  savedGroups: Record<string, SavedGroup[]>
  /** focus a group (null = none); clears the focused cell */
  focusGroup(ref: GroupRef | null): void
  /** set the lasso selection and focus it (null clears it) */
  setSelection(sel: Selection | null): void
  /** save the current selection as a named group (keeps its id) */
  saveSelection(name?: string): void
  renameSavedGroup(id: string, name: string): void
  deleteSavedGroup(id: string): void
  /** interface theme: the choice (persisted) and the applied palette */
  themeChoice: ThemeChoice
  palette: Palette
  setThemeChoice(choice: ThemeChoice): void
  /** re-apply the theme (the system preference changed) */
  refreshTheme(): void
  /** automatic colour range of each drawn matrix (key: pane id or pane:row) — inspector placeholders */
  matrixAuto: Record<string, [number, number]>
  setMatrixAuto(key: string, range: [number, number]): void
}

/** Saved groups of the active dataset. */
export function activeSavedGroups(s: Pick<AppState, 'savedGroups' | 'datasets' | 'activeDatasetId'>): SavedGroup[] {
  const name = s.datasets.find((d) => d.id === s.activeDatasetId)?.name
  return (name && s.savedGroups[name]) || NO_GROUPS
}
const NO_GROUPS: SavedGroup[] = []

/** Values of the active overview field, if loaded. */
export function activeFieldValues(s: Pick<AppState, 'views' | 'activeDatasetId' | 'cellValues'>): Map<string, CellValue> | null {
  const v = activeView(s)
  if (!s.activeDatasetId || !v.cellField) return null
  return s.cellValues[fieldKey(s.activeDatasetId, v.cellField)] ?? null
}

/**
 * Cells in display order: natural id order, or by the overview field value
 * (descending, missing last) when colouring by a field and sorting by value.
 * The cell list and ←/→ stepping both follow this order.
 */
export function orderedCells(s: Pick<AppState, 'views' | 'activeDatasetId' | 'cellValues' | 'cells'> & { datasets?: DatasetSummary[] }): CellInfo[] {
  const list = (s.activeDatasetId && s.cells[s.activeDatasetId]) || []
  const v = activeView(s)
  const vals = activeFieldValues(s)
  if (v.overviewColor !== 'field' || v.cellSort !== 'value' || !vals) return list
  // categories: legend order (first category on top); numbers: descending
  const order = (s.datasets?.find((d) => d.id === s.activeDatasetId)?.cell_fields?.find((f) => f.name === v.cellField)?.categories ?? []).map((c) => c.value)
  const rank = new Map(order.map((c, i) => [c, -i]))
  for (const x of vals.values()) if (typeof x === 'string' && !rank.has(x)) rank.set(x, -rank.size)
  const key = (c: CellInfo) => {
    const x = vals.get(c.cell_id)
    if (typeof x === 'string') return rank.get(x) ?? -Infinity
    return typeof x === 'number' && Number.isFinite(x) ? x : -Infinity
  }
  return list.map((c, i) => ({ c, i })).sort((a, b) => key(b.c) - key(a.c) || a.i - b.i).map((x) => x.c)
}

/** View state of the active dataset (defaults when none recorded). */
export function activeView(s: Pick<AppState, 'views' | 'activeDatasetId'>): DatasetView {
  return (s.activeDatasetId && s.views[s.activeDatasetId]) || DEFAULT_VIEW
}

const patchLayer = (layers: Layer[], id: string, patch: Partial<Layer>) =>
  layers.map((l) => (l.id === id ? { ...l, ...patch } : l))

const savedWorkspace = loadWorkspace()
const savedGroups = loadSavedGroups()
const savedTheme = loadThemeChoice()
const initialPalette = applyTheme(resolveTheme(savedTheme, systemPrefersDark()))

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
  cellValues: {},
  pointSets: {},

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
    if (!get().views[ds.id]) set({ views: { ...get().views, [ds.id]: initialView(ds) } })
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
      pick: s.pick && (isPointPick(s.pick) || layers.some((l) => l.id === (s.pick as { layerId: string }).layerId)) ? s.pick : null,
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
  workspace: savedWorkspace ?? defaultWorkspace(false),
  workspaceTouched: savedWorkspace !== null,
  ensureDefaultWorkspace(kind) {
    const s = get()
    if (s.workspaceTouched) return
    const ws = defaultWorkspace(kind)
    if (paneSignature(ws) !== paneSignature(s.workspace)) set({ workspace: ws })
  },
  setWorkspace(update) {
    const workspace = update(get().workspace)
    if (workspace === get().workspace) return
    set({ workspace, workspaceTouched: true })
    saveWorkspace(workspace)
  },
  openCellView(cell) {
    const ds = get().datasets.find((d) => d.id === get().activeDatasetId)
    get().setWorkspace((ws) => addPinnedPane(ws, hasCoords(ds) ? '3d' : 'genome', cell))
  },
  resetView() {
    set({ resetViewToken: get().resetViewToken + 1 })
  },
  setCells(datasetId, cells) {
    set({ cells: { ...get().cells, [datasetId]: cells } })
  },
  focusCell(cellId) {
    const s = get()
    const v = activeView(s)
    if (v.focusCell === cellId && (cellId !== null || v.focusGroup === null)) return
    // one focus at a time: a cell, or a group ("All cells" clears both)
    patchView({ focusCell: cellId, focusGroup: null }, { pick: null, flyToken: s.flyToken + 1 })
  },
  savedGroups,
  themeChoice: savedTheme,
  palette: initialPalette,
  setThemeChoice(choice) {
    saveThemeChoice(choice)
    set({ themeChoice: choice, palette: applyTheme(resolveTheme(choice, systemPrefersDark())) })
  },
  matrixAuto: {},
  setMatrixAuto(key, range) {
    const cur = get().matrixAuto[key]
    if (cur && cur[0] === range[0] && cur[1] === range[1]) return
    set({ matrixAuto: { ...get().matrixAuto, [key]: range } })
  },
  refreshTheme() {
    set({ palette: applyTheme(resolveTheme(get().themeChoice, systemPrefersDark())) })
  },
  focusGroup(ref) {
    const s = get()
    const v = activeView(s)
    if (v.focusGroup === ref && v.focusCell === null) return
    patchView({ focusGroup: ref, focusCell: null }, { pick: null, flyToken: s.flyToken + 1 })
  },
  setSelection(sel) {
    const s = get()
    const v = activeView(s)
    const focusGroup = sel ? sel.id : v.focusGroup === v.selection?.id ? null : v.focusGroup
    patchView({ selection: sel, focusGroup, focusCell: sel ? null : v.focusCell }, { pick: null, flyToken: s.flyToken + 1 })
  },
  saveSelection(name) {
    const s = get()
    const v = activeView(s)
    const ds = s.datasets.find((d) => d.id === s.activeDatasetId)
    if (!ds || !v.selection) return
    const list = s.savedGroups[ds.name] ?? []
    const existing = list.find((g) => g.id === v.selection!.id)
    const g: SavedGroup = {
      id: v.selection.id,
      name: name?.trim() || existing?.name || nextGroupName(list),
      color: existing?.color ?? groupColor(list.length),
      cells: v.selection.cells,
    }
    const savedGroups = { ...s.savedGroups, [ds.name]: upsertGroup(list, g) }
    set({ savedGroups })
    persistGroups(savedGroups)
    patchView({ selection: null, focusGroup: g.id, focusCell: null })
  },
  renameSavedGroup(id, name) {
    const s = get()
    const ds = s.datasets.find((d) => d.id === s.activeDatasetId)
    if (!ds) return
    const savedGroups = { ...s.savedGroups, [ds.name]: renameGroup(s.savedGroups[ds.name] ?? [], id, name) }
    set({ savedGroups })
    persistGroups(savedGroups)
  },
  deleteSavedGroup(id) {
    const s = get()
    const ds = s.datasets.find((d) => d.id === s.activeDatasetId)
    if (!ds) return
    const savedGroups = { ...s.savedGroups, [ds.name]: removeGroup(s.savedGroups[ds.name] ?? [], id) }
    set({ savedGroups })
    persistGroups(savedGroups)
    if (activeView(s).focusGroup === id) patchView({ focusGroup: null })
    // panes / rows scoped to it fall back to their other scope
    get().setWorkspace((w) => dropGroupScope(w, id))
  },
  stepCell(delta) {
    const s = get()
    const list = orderedCells(s)
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
  setOverviewColor(overviewColor) {
    patchView({ overviewColor })
  },
  setCellField(cellField) {
    const v = activeView(get())
    const hiddenCategories = cellField === v.cellField ? v.hiddenCategories : []
    patchView(cellField ? { cellField, overviewColor: 'field', hiddenCategories } : { cellField: null, hiddenCategories })
  },
  toggleCategory(value) {
    const hidden = new Set(activeView(get()).hiddenCategories)
    if (hidden.has(value)) hidden.delete(value)
    else hidden.add(value)
    patchView({ hiddenCategories: [...hidden] })
  },
  setHiddenCategories(values) {
    patchView({ hiddenCategories: [...values] })
  },
  setCellSort(cellSort) {
    patchView({ cellSort })
  },
  setCellValues(datasetId, field, values) {
    set({ cellValues: { ...get().cellValues, [fieldKey(datasetId, field)]: values } })
  },
  setPointSet(datasetId, ps) {
    const all = get().pointSets
    set({ pointSets: { ...all, [datasetId]: { ...(all[datasetId] ?? {}), [ps.name]: ps } } })
  },
  togglePointSet(name) {
    const hidden = new Set(activeView(get()).hiddenPointSets)
    if (hidden.has(name)) hidden.delete(name)
    else hidden.add(name)
    patchView({ hiddenPointSets: [...hidden] })
  },
  toggleLabel(setName, label) {
    const v = activeView(get())
    const hidden = new Set(v.hiddenLabels[setName] ?? [])
    if (hidden.has(label)) hidden.delete(label)
    else hidden.add(label)
    patchView({ hiddenLabels: { ...v.hiddenLabels, [setName]: [...hidden] } })
  },
  setHiddenLabels(setName, labels) {
    const v = activeView(get())
    patchView({ hiddenLabels: { ...v.hiddenLabels, [setName]: [...labels] } })
  },
  setPointSize(pointSize) {
    patchView({ pointSize })
  },
  setMaxBond(maxBond) {
    patchView({ maxBond })
  },
  setLocus(locus) {
    const cur = activeView(get()).locus
    if (cur && cur.chrom === locus.chrom && cur.start === locus.start && cur.end === locus.end) return
    patchView({ locus })
  },
  }
})

/** Cells of a registered group (saved or the current selection) for api.groupParam. */
setGroupResolver((datasetId, ref) => {
  const s = useStore.getState()
  const ds = s.datasets.find((d) => d.id === datasetId)
  const saved = ds ? (s.savedGroups[ds.name] ?? []).find((g) => g.id === ref) : undefined
  if (saved) return saved.cells
  const sel = s.views[datasetId]?.selection
  return sel && sel.id === ref ? sel.cells : null
})

import { create } from 'zustand'
import { ws } from './ws'

export interface GenomicViewport { chrom: string; start: number; end: number }
export interface CellSelection { mode: 'cell_type' | 'manual' | 'all'; ids: string[]; label: string }
export type TabType = 'genomic' | 'embedding' | 'structure3d' | 'notebook' | 'custom'

export interface GoslingArtifact {
  id: string
  title: string
  spec: object
  createdAt: number
  active: boolean
}

export interface NotebookCell {
  id: string
  code: string
  outputs: Array<{ type: 'text' | 'image' | 'error'; content: string }>
  running: boolean
}

interface AppStore {
  // Viewport
  viewport: GenomicViewport
  setViewport: (v: GenomicViewport, notifyAgent?: boolean) => void

  // Cell selection
  cellSelection: CellSelection
  setCellSelection: (s: CellSelection) => void

  // Active tab
  activeTab: TabType
  setActiveTab: (t: TabType) => void

  // Data version (bumped when new data loaded)
  dataVersion: number
  bumpDataVersion: () => void

  // Linked view state
  highlightedCells: string[]
  selectedRegion: { chr: string; start: number; end: number } | null
  highlightCells: (cellIds: string[]) => void
  selectRegion: (region: { chr: string; start: number; end: number } | null) => void

  // Highlight regions (for agent tools)
  highlightRegions: Array<{ chr: string; start: number; end: number; color: string }>
  setHighlightRegions: (regions: Array<{ chr: string; start: number; end: number; color: string }>) => void

  // Colormap config (for agent tools)
  colormapConfig: { scale: string; domain: [number, number] } | null
  setColormapConfig: (config: { scale: string; domain: [number, number] } | null) => void

  // Gosling A2UI
  activeGoslingSpec: object | null
  activeGoslingSpecId: string | null
  goslingArtifacts: GoslingArtifact[]
  setActiveGoslingSpec: (spec: object | undefined, id: string | undefined) => void
  addGoslingArtifact: (artifact: GoslingArtifact) => void
  applyGoslingPatch: (targetId: string, patch: { op: string; path: string; value: unknown }) => void
  // Rebuild gosling views from a backend snapshot (after WS reconnect).
  hydrateViews: (views: Array<{ view_id: string; view_type: string; state: Record<string, unknown>; title?: string }>) => void

  // Tier-2 generative UI: an agent-composed component tree (whitelisted nodes).
  activeComponentTree: { id: string; title: string; tree: unknown } | null
  setComponentTree: (id: string, title: string, tree: unknown) => void

  // Export signal: bumped (with a format) to ask the active Gosling view to export.
  // GoslingRenderer subscribes; consumers compare `id` to detect a fresh request.
  exportRequest: { id: number; format: 'png' | 'pdf' } | null
  requestExport: (format: 'png' | 'pdf') => void

  // Notebook
  notebookCells: NotebookCell[]
  addNotebookCell: (cell: NotebookCell) => void
  updateCellOutput: (cellId: string, outputs: NotebookCell['outputs']) => void
  setCellRunning: (cellId: string, running: boolean) => void
}

let _cellIdCounter = 1

export const useAppStore = create<AppStore>((set, get) => ({
  viewport: { chrom: 'chr1', start: 0, end: 248956422 },
  setViewport: (v, notifyAgent = false) => {
    set({ viewport: v })
    if (notifyAgent && ws.connected) {
      // ws.send already wraps as { type, payload }; pass v directly so the
      // backend reads session.viewport = payload (not a double-wrapped object).
      ws.send('update_viewport', v)
    }
  },

  cellSelection: { mode: 'all', ids: [], label: 'All Cells' },
  setCellSelection: (s) => set({ cellSelection: s }),

  activeTab: 'genomic',
  setActiveTab: (t) => set({ activeTab: t }),

  dataVersion: 0,
  bumpDataVersion: () => set(s => ({ dataVersion: s.dataVersion + 1 })),

  // Linked view state
  highlightedCells: [],
  selectedRegion: null,
  highlightCells: (cellIds) => set({ highlightedCells: cellIds }),
  selectRegion: (region) => set({ selectedRegion: region }),

  // Highlight regions
  highlightRegions: [],
  setHighlightRegions: (regions) => set({ highlightRegions: regions }),

  // Colormap config
  colormapConfig: null,
  setColormapConfig: (config) => set({ colormapConfig: config }),

  // Gosling
  activeGoslingSpec: null,
  activeGoslingSpecId: null,
  goslingArtifacts: [],
  setActiveGoslingSpec: (spec, id) => set({ activeGoslingSpec: spec, activeGoslingSpecId: id }),
  addGoslingArtifact: (artifact) => set(s => ({
    goslingArtifacts: [...s.goslingArtifacts, artifact]
  })),
  hydrateViews: (views) => {
    const gosling = views.filter(v => v.view_type === 'gosling' && v.state?.spec)
    if (gosling.length > 0) {
      const artifacts: GoslingArtifact[] = gosling.map(v => ({
        id: v.view_id,
        title: (v.title as string) || (v.state.title as string) || 'Genomic Visualization',
        spec: v.state.spec as object,
        createdAt: Date.now(),
        active: false,
      }))
      const last = artifacts[artifacts.length - 1]
      set({
        goslingArtifacts: artifacts,
        activeGoslingSpec: last.spec,
        activeGoslingSpecId: last.id,
      })
    }
    // Rebuild the most recent component tree, if any.
    const components = views.filter(v => v.view_type === 'component' && v.state?.tree)
    if (components.length > 0) {
      const v = components[components.length - 1]
      set({
        activeComponentTree: {
          id: v.view_id,
          title: (v.title as string) || (v.state.title as string) || 'Custom View',
          tree: v.state.tree,
        },
      })
    }
  },
  applyGoslingPatch: (targetId, patch) => {
    // Apply JSON patch to the active spec if it matches targetId
    const { activeGoslingSpec, activeGoslingSpecId } = get()
    if (activeGoslingSpecId !== targetId || !activeGoslingSpec) return
    // Simple path-based patch: only handle /views/N/tracks/M/mark etc.
    const newSpec = JSON.parse(JSON.stringify(activeGoslingSpec))
    const parts = patch.path.replace(/^\//, '').split('/')
    let obj: Record<string, unknown> = newSpec
    for (let i = 0; i < parts.length - 1; i++) {
      obj = (obj as Record<string, unknown>)[parts[i]] as Record<string, unknown>
      if (!obj) return
    }
    if (patch.op === 'replace' || patch.op === 'add') {
      obj[parts[parts.length - 1]] = patch.value
    } else if (patch.op === 'remove') {
      delete obj[parts[parts.length - 1]]
    }
    set({ activeGoslingSpec: newSpec })
  },

  // Export
  exportRequest: null,
  requestExport: (format) => set(s => ({
    exportRequest: { id: (s.exportRequest?.id ?? 0) + 1, format },
  })),

  // Tier-2 component tree
  activeComponentTree: null,
  setComponentTree: (id, title, tree) => set({ activeComponentTree: { id, title, tree } }),

  // Notebook
  notebookCells: [
    { id: `cell_${_cellIdCounter++}`, code: '# Load data and explore\nimport uchrom\ncd = uchrom.load_current()\nprint(cd)', outputs: [], running: false }
  ],
  addNotebookCell: (cell) => set(s => ({ notebookCells: [...s.notebookCells, cell] })),
  updateCellOutput: (cellId, outputs) => set(s => ({
    notebookCells: s.notebookCells.map(c => c.id === cellId ? { ...c, outputs } : c)
  })),
  setCellRunning: (cellId, running) => set(s => ({
    notebookCells: s.notebookCells.map(c => c.id === cellId ? { ...c, running } : c)
  })),
}))

export let _notebookCellIdCounter = _cellIdCounter
export function nextCellId() { return `cell_${++_cellIdCounter}` }

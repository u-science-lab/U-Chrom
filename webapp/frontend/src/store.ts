import { create } from 'zustand'
import { applyPatch as applyJsonPatch, type Operation } from 'fast-json-patch'
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

  // Agent-driven coloring / filtering (color_embedding / show_structure / color_structure)
  // embeddingColorBy: which cell-table field the UMAP scatter colors by (null → default 'cell_type').
  embeddingColorBy: string | null
  setEmbeddingColorBy: (field: string | null) => void
  // selectedStructureCell/Chrom: restrict the 3D view to one cell (and optional chrom); null → show all.
  selectedStructureCell: string | null
  selectedStructureChrom: string | null
  setStructureSelection: (cellId: string | null, chrom: string | null) => void
  // structureColorBy: which spot-table field the 3D traces color by (null → default per-trace palette).
  structureColorBy: string | null
  setStructureColorBy: (field: string | null) => void

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
  // Per-view RFC 6902 revision numbers (mirror the backend's ViewSession.revision).
  // Used to detect a STATE_DELTA gap: if an incoming patch's base_revision does
  // not match the local revision, we re-pull a full snapshot instead of applying.
  viewRevisions: Record<string, number>
  // Apply a standard JSON-Patch op array to a view's state document. Generic
  // infrastructure: `gosling` views patch their spec; other view types can opt
  // in by storing a patchable document. base/newRevision drive reconciliation.
  applyPatch: (
    viewId: string,
    ops: Operation[],
    baseRevision?: number | null,
    newRevision?: number | null,
  ) => void
  // Rebuild gosling views from a backend snapshot (after WS reconnect).
  hydrateViews: (views: Array<{ view_id: string; view_type: string; state: Record<string, unknown>; title?: string; revision?: number }>) => void

  // Tier-2 generative UI: an agent-composed component tree (whitelisted nodes).
  activeComponentTree: { id: string; title: string; tree: unknown } | null
  setComponentTree: (id: string, title: string, tree: unknown) => void

  // Export signal: bumped (with a format) to ask the active Gosling view to export.
  // GoslingRenderer subscribes; consumers compare `id` to detect a fresh request.
  exportRequest: { id: number; format: 'png' | 'pdf' } | null
  requestExport: (format: 'png' | 'pdf') => void

  // AG-UI-style interaction round-trip: while the agent blocks in
  // query_user_interaction(wait=true), the backend announces an interaction_id
  // (await_interaction). Views echo it back on their ui_event so the backend
  // resolves EXACTLY that waiter. null → the agent isn't waiting on anything.
  pendingInteractionId: string | null
  setPendingInteractionId: (id: string | null) => void

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

  // Agent-driven coloring / filtering
  embeddingColorBy: null,
  setEmbeddingColorBy: (field) => set({ embeddingColorBy: field }),
  selectedStructureCell: null,
  selectedStructureChrom: null,
  setStructureSelection: (cellId, chrom) =>
    set({ selectedStructureCell: cellId, selectedStructureChrom: chrom }),
  structureColorBy: null,
  setStructureColorBy: (field) => set({ structureColorBy: field }),

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
  viewRevisions: {},
  setActiveGoslingSpec: (spec, id) => set({ activeGoslingSpec: spec, activeGoslingSpecId: id }),
  addGoslingArtifact: (artifact) => set(s => ({
    goslingArtifacts: [...s.goslingArtifacts, artifact]
  })),
  hydrateViews: (views) => {
    // Adopt the backend revision for every view so subsequent base_revision
    // checks line up after a reconnect / snapshot re-pull.
    const revisions: Record<string, number> = { ...get().viewRevisions }
    for (const v of views) {
      if (typeof v.revision === 'number') revisions[v.view_id] = v.revision
    }
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
        viewRevisions: revisions,
      })
    } else {
      set({ viewRevisions: revisions })
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
  applyPatch: (viewId, ops, baseRevision = null, newRevision = null) => {
    const { activeGoslingSpec, activeGoslingSpecId, viewRevisions } = get()
    // Reconciliation: if the patch declares the revision it was built against
    // and that doesn't match our local revision, we've missed an update — drop
    // the delta and re-pull a full snapshot (RFC-6902 STATE_DELTA reconcile).
    if (baseRevision != null) {
      const local = viewRevisions[viewId]
      if (local != null && local !== baseRevision) {
        ws.send('view.request_snapshot', { view_id: viewId })
        return
      }
    }
    // Currently only the active Gosling spec is patchable on the client. Other
    // view types can opt in here once they hold a patchable state document.
    if (activeGoslingSpecId !== viewId || !activeGoslingSpec) {
      // Unknown/inactive target with a revision hint → reconcile to be safe.
      if (baseRevision != null) ws.send('view.request_snapshot', { view_id: viewId })
      return
    }
    let newSpec: object
    try {
      // validate=false: tolerate a stray op rather than throw the whole batch.
      const result = applyJsonPatch(
        JSON.parse(JSON.stringify(activeGoslingSpec)),
        ops as Operation[],
        /* validateOperation */ false,
        /* mutateDocument */ false,
      )
      newSpec = result.newDocument as object
    } catch (e) {
      // A malformed/unresolvable patch shouldn't desync us — re-pull instead.
      console.error('applyPatch failed; requesting snapshot', e)
      ws.send('view.request_snapshot', { view_id: viewId })
      return
    }
    const nextRev = newRevision != null
      ? newRevision
      : (viewRevisions[viewId] ?? 0) + 1
    set({
      activeGoslingSpec: newSpec,
      viewRevisions: { ...viewRevisions, [viewId]: nextRev },
    })
  },

  // Export
  exportRequest: null,
  requestExport: (format) => set(s => ({
    exportRequest: { id: (s.exportRequest?.id ?? 0) + 1, format },
  })),

  // Pending agent interaction (query_user_interaction wait=true)
  pendingInteractionId: null,
  setPendingInteractionId: (id) => set({ pendingInteractionId: id }),

  // Tier-2 component tree
  activeComponentTree: null,
  setComponentTree: (id, title, tree) => set({ activeComponentTree: { id, title, tree } }),

  // Notebook
  notebookCells: [
    { id: `cell_${_cellIdCounter++}`, code: '# `cd` (the loaded ChromData) is already available in the kernel.\n# numpy as np, pandas as pd, and matplotlib (Agg backend) are pre-imported.\nprint(cd)\nprint(cd.coords.shape)', outputs: [], running: false }
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

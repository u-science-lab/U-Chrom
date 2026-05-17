import { create } from 'zustand'

interface GenomicViewport { chrom: string; start: number; end: number }
interface CellSelection { mode: 'cell_type' | 'manual' | 'all'; ids: string[]; label: string }
export interface CameraState { position: [number,number,number]; target: [number,number,number] }

export type PanelType = 'umap' | 'structure3d' | 'contact_map' | 'track_plot'
export interface PanelDef { id: string; type: PanelType; label: string }

interface AppStore {
  viewport: GenomicViewport
  cellSelection: CellSelection
  panels: PanelDef[]
  cameraState: CameraState | null
  linkedCameras: boolean
  setViewport: (v: GenomicViewport) => void
  setCellSelection: (s: CellSelection) => void
  addPanel: (type: PanelType) => void
  removePanel: (id: string) => void
  setCameraState: (c: CameraState) => void
  setLinkedCameras: (v: boolean) => void
}

let _nextId = 1

export const useAppStore = create<AppStore>((set) => ({
  viewport: { chrom: 'chr1', start: 0, end: 1000000 },
  cellSelection: { mode: 'all', ids: [], label: 'All Cells' },
  panels: [{ id: 'p1', type: 'umap', label: 'Cell Embedding' }],
  cameraState: null,
  linkedCameras: false,
  setViewport: (v) => set({ viewport: v }),
  setCellSelection: (s) => set({ cellSelection: s }),
  addPanel: (type) => set(s => ({
    panels: [...s.panels, { id: `p${++_nextId}`, type, label: PANEL_LABELS[type] }]
  })),
  removePanel: (id) => set(s => ({ panels: s.panels.filter(p => p.id !== id) })),
  setCameraState: (c) => set({ cameraState: c }),
  setLinkedCameras: (v) => set({ linkedCameras: v }),
}))

const PANEL_LABELS: Record<PanelType, string> = {
  umap: 'Cell Embedding',
  structure3d: '3D Structure',
  contact_map: 'Contact Map',
  track_plot: 'Track Plot',
}

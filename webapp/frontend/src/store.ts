import { create } from 'zustand'

interface GenomicViewport { chrom: string; start: number; end: number }
interface CellSelection { mode: 'cell_type' | 'manual' | 'all'; ids: string[]; label: string }

interface AppStore {
  viewport: GenomicViewport
  cellSelection: CellSelection
  setViewport: (v: GenomicViewport) => void
  setCellSelection: (s: CellSelection) => void
}

export const useAppStore = create<AppStore>((set) => ({
  viewport: { chrom: 'chr1', start: 0, end: 1000000 },
  cellSelection: { mode: 'all', ids: [], label: 'All Cells' },
  setViewport: (v) => set({ viewport: v }),
  setCellSelection: (s) => set({ cellSelection: s }),
}))

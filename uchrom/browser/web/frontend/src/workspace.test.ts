import { describe, expect, it, vi } from 'vitest'
import { groupTitle } from './components/FieldPicker'
import { useStore } from './store'
import {
  addPane,
  defaultEmbeddingKey,
  defaultWorkspace,
  supportedPaneTypes,
  handleWorkspaceKey,
  MIN_FRAC,
  moveSplitter,
  normalizeSizes,
  parseWorkspace,
  removePane,
  retypePane,
  setLayout,
  updatePane,
} from './workspace'

const sum = (a: number[]) => a.reduce((x, y) => x + y, 0)

describe('default workspace', () => {
  it('pairs 3D with an embedding when the data has embeddings', () => {
    const ws = defaultWorkspace(true)
    expect(ws.layout).toBe('columns')
    expect(ws.panes.map((p) => p.type)).toEqual(['3d', 'embedding'])
    expect(ws.sizes).toEqual([0.6, 0.4])
    expect(defaultWorkspace(false).panes.map((p) => p.type)).toEqual(['3d', 'matrix']) // coords, no embeddings → 3D | distance matrix
  })
  it('prefers UMAP > t-SNE > PCA', () => {
    const e = (key: string, method: string) => ({ key, method, source: 'rna', label: key, n_dims: 2 })
    expect(defaultEmbeddingKey([e('a', 'pca'), e('b', 'tsne'), e('c', 'umap')])).toBe('c')
    expect(defaultEmbeddingKey([e('a', 'pca'), e('b', 'tsne')])).toBe('b')
    expect(defaultEmbeddingKey([])).toBeNull()
    const m = (key: string, modality: string) => ({ ...e(key, 'umap'), modality })
    expect(defaultEmbeddingKey([m('atac_umap', 'ATAC'), m('paper_umap', 'Published'), m('rna_umap', 'RNA')])).toBe('rna_umap')
    expect(defaultEmbeddingKey([m('atac_umap', 'ATAC'), m('umap', 'Published')])).toBe('umap')
  })
})

describe('pane actions', () => {
  it('adds, retypes, updates and removes panes with stable ids', () => {
    let ws = defaultWorkspace(true)
    ws = addPane(ws, 'embedding')
    expect(ws.panes.map((p) => p.id)).toEqual(['P1', 'P2', 'P3'])
    expect(ws.activePane).toBe('P3')
    expect(sum(ws.sizes)).toBeCloseTo(1)
    ws = updatePane(ws, 'P3', { embeddingKey: 'rna_pca', dims: [1, 2] })
    ws = retypePane(ws, 'P3', '3d')
    expect(ws.panes[2]).toEqual({ id: 'P3', type: '3d', embeddingKey: 'rna_pca', dims: [1, 2] })
    ws = removePane(ws, 'P2')
    expect(ws.panes.map((p) => p.id)).toEqual(['P1', 'P3'])
    expect(sum(ws.sizes)).toBeCloseTo(1)
    // ids are not reused while in use
    expect(addPane(ws, '3d').panes.map((p) => p.id)).toEqual(['P1', 'P3', 'P4'])
    // the last pane cannot be closed
    const one = removePane(removePane(ws, 'P3'), 'P1')
    expect(one.panes.map((p) => p.id)).toEqual(['P1'])
  })
  it('switching layout keeps panes and clears maximise', () => {
    const ws = { ...defaultWorkspace(true), maximized: 'P2' }
    const g = setLayout(ws, 'grid')
    expect(g.layout).toBe('grid')
    expect(g.panes).toBe(ws.panes)
    expect(g.maximized).toBeNull()
  })
})

describe('sizes', () => {
  it('normalises and clamps to a minimum share', () => {
    const s = normalizeSizes([0.98, 0.01, 0.01], 3)
    expect(sum(s)).toBeCloseTo(1)
    expect(Math.min(...s)).toBeGreaterThanOrEqual(MIN_FRAC - 1e-9)
    expect(normalizeSizes([1, 2], 3)).toEqual([1 / 3, 1 / 3, 1 / 3])
  })
  it('moves one splitter between its two neighbours only', () => {
    let ws = addPane(defaultWorkspace(true), '3d')
    ws = { ...ws, sizes: [0.4, 0.3, 0.3] }
    const m = moveSplitter(ws, 0, 0.55)
    expect(m.sizes[0]).toBeCloseTo(0.55)
    expect(m.sizes[1]).toBeCloseTo(0.15)
    expect(m.sizes[2]).toBeCloseTo(0.3)
    expect(moveSplitter(ws, 0, 0.99).sizes[1]).toBeCloseTo(MIN_FRAC)
  })
})

describe('persistence', () => {
  it('accepts a saved workspace and rejects junk', () => {
    const ws = addPane(defaultWorkspace(true), 'embedding')
    expect(parseWorkspace(JSON.parse(JSON.stringify(ws)))).toEqual(ws)
    expect(parseWorkspace(null)).toBeNull()
    expect(parseWorkspace({ layout: 'mosaic', panes: [] })).toBeNull()
    expect(parseWorkspace({ layout: 'tabs', panes: [{ id: 'a', type: 'map' }] })).toBeNull()
    const fixed = parseWorkspace({ layout: 'tabs', panes: [{ id: 'a', type: '3d' }], activePane: 'zz', sizes: 'x' })
    expect(fixed).toMatchObject({ activePane: 'a', sizes: [1], maximized: null })
  })
  it('the store applies the data-dependent default until the user changes the layout', () => {
    useStore.setState({ workspace: defaultWorkspace(false), workspaceTouched: false })
    useStore.getState().ensureDefaultWorkspace(true)
    expect(useStore.getState().workspace.panes.map((p) => p.type)).toEqual(['3d', 'embedding'])
    useStore.getState().setWorkspace((w) => setLayout(w, 'rows'))
    useStore.getState().ensureDefaultWorkspace(false)
    expect(useStore.getState().workspace.layout).toBe('rows')
    expect(useStore.getState().workspace.panes).toHaveLength(2)
  })
})

describe('workspace keys', () => {
  const actions = () => ({ hasPick: false, clearPick: vi.fn(), clearFocus: vi.fn(), step: vi.fn() })
  it('steps cells and clears pick before focus', () => {
    const a = actions()
    expect(handleWorkspaceKey({ key: 'ArrowRight', target: null }, a)).toBe(true)
    expect(handleWorkspaceKey({ key: 'ArrowUp', target: null }, a)).toBe(true)
    expect(a.step.mock.calls).toEqual([[1], [-1]])
    handleWorkspaceKey({ key: 'Escape', target: null }, a)
    expect(a.clearFocus).toHaveBeenCalledOnce()
    const b = { ...actions(), hasPick: true }
    handleWorkspaceKey({ key: 'Escape', target: null }, b)
    expect(b.clearPick).toHaveBeenCalledOnce()
    expect(b.clearFocus).not.toHaveBeenCalled()
  })
  it('ignores keys typed into inputs', () => {
    const a = actions()
    const input = { tagName: 'INPUT' } as unknown as EventTarget
    expect(handleWorkspaceKey({ key: 'ArrowRight', target: input }, a)).toBe(false)
    expect(a.step).not.toHaveBeenCalled()
  })
})

describe('colour groups', () => {
  it('names field groups for users', () => {
    expect(groupTitle('rna')).toBe('Gene')
    expect(groupTitle('cell')).toBe('Property')
    expect(groupTitle('if')).toBe('IF')
    expect(groupTitle('atac')).toBe('ATAC')
    expect(groupTitle('hic')).toBe('Hi-C')
  })
})

describe('embedding picker', () => {
  it('groups embeddings by modality as "<modality> · <method>"', async () => {
    const { groupEmbeddings } = await import('./components/EmbeddingView')
    const e = (key: string, method: string | null, modality?: string, label = key) => ({ key, method: method as string, source: '', modality, label, n_dims: 2 })
    const groups = groupEmbeddings([
      e('paper_umap', 'umap', 'Published', 'Paper UMAP (RNA)'),
      e('rna_pca', 'pca', 'RNA'),
      e('rna_umap', 'umap', 'RNA'),
      e('atac_lsi', 'lsi', 'ATAC'),
      e('atac_umap', 'umap', 'ATAC'),
      e('hic_umap', 'umap', 'Hi-C'),
      e('if_umap', 'umap', 'Histone/IF'),
      e('mystery', null, undefined, 'mystery'),
    ])
    expect(groups.map((g) => g.modality)).toEqual(['RNA', 'Histone/IF', 'ATAC', 'Hi-C', 'Published', 'Other'])
    expect(groups[0].items.map((i) => i.text)).toEqual(['RNA · UMAP', 'RNA · PCA'])
    expect(groups[2].items.map((i) => i.text)).toEqual(['ATAC · UMAP', 'ATAC · LSI'])
    expect(groups[4].items[0].text).toBe('Published · UMAP')
    expect(groups[5].items[0].text).toBe('Other · mystery')
    // two published UMAPs: fall back to their labels
    const two = groupEmbeddings([e('a', 'umap', 'Published', 'Paper A'), e('b', 'umap', 'Published', 'Paper B')])
    expect(two[0].items.map((i) => i.text)).toEqual(['Published · Paper A', 'Published · Paper B'])
  })
})

describe('views the data supports', () => {
  const none = { hasEmbeddings: false, hasCoords: false, hasTracks: false }
  it('lists only the views a dataset can fill', () => {
    expect(supportedPaneTypes({ ...none, hasCoords: true, hasEmbeddings: true })).toEqual(['3d', 'embedding', 'genome', 'matrix', 'stats'])
    // spatial Hi-C: positions, embeddings, ssA/B tracks, no 3-D, no contact map
    expect(supportedPaneTypes({ ...none, hasEmbeddings: true, hasTracks: true, hasSpatial: true, manyCells: true })).toEqual([
      'spatial',
      'embedding',
      'genome',
      'stats',
    ])
    expect(supportedPaneTypes({ ...none, hasContactMaps: true })).toEqual(['genome', 'matrix'])
  })
  it('defaults to Spatial next to the genome signals for cells in tissue', () => {
    const t = (k: Parameters<typeof defaultWorkspace>[0]) => defaultWorkspace(k).panes.map((p) => p.type)
    expect(t({ ...none, hasSpatial: true, hasTracks: true, hasEmbeddings: true })).toEqual(['spatial', 'genome'])
    expect(t({ ...none, hasSpatial: true, hasEmbeddings: true })).toEqual(['spatial', 'embedding'])
    expect(t({ ...none, hasEmbeddings: true })).toEqual(['matrix', 'embedding'])
  })
  it('keeps the spatial pane options of a saved layout', () => {
    const ws = parseWorkspace({
      layout: 'columns',
      panes: [{ id: 'P1', type: 'spatial', spatialKey: 'image', region: 'E14_5_HiC', imageOpacity: 0.4 }],
      activePane: 'P1',
      sizes: [1],
    })
    expect(ws?.panes[0]).toMatchObject({ type: 'spatial', spatialKey: 'image', region: 'E14_5_HiC', imageOpacity: 0.4 })
  })
})

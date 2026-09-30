import { describe, expect, it, vi } from 'vitest'
import { groupTitle } from './components/FieldPicker'
import { useStore } from './store'
import {
  addPane,
  defaultEmbeddingKey,
  defaultWorkspace,
  workspaceOf,
  effectiveStyle,
  parseLayerStyles,
  setPaneLayerStyle,
  paneSignature,
  gridShape,
  gridSizes,
  gridSpan,
  moveGridSplitter,
  supportedPaneTypes,
  handleWorkspaceKey,
  MIN_FRAC,
  moveSplitter,
  normalizeSizes,
  parseWorkspace,
  parseWorkspaces,
  removePane,
  retypePane,
  setLayout,
  updatePane,
} from './workspace'

const sum = (a: number[]) => a.reduce((x, y) => x + y, 0)

describe('default workspace', () => {
  it('opens every view the data supports in a grid', () => {
    const ws = defaultWorkspace(true)
    expect(ws.layout).toBe('grid')
    // …but Matrix, whose maps the Genome view's matrix rows already show
    expect(ws.panes.map((p) => p.type)).toEqual(['3d', 'embedding', 'genome', 'stats'])
    expect(defaultWorkspace(false).panes.map((p) => p.type)).toEqual(['3d', 'genome', 'stats'])
    // one view: no grid
    expect(defaultWorkspace({ hasCoords: false, hasEmbeddings: false, hasTracks: false })).toMatchObject({ layout: 'columns', panes: [{ type: 'matrix' }] })
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
    let ws = workspaceOf(['3d', 'embedding'], [0.6, 0.4])
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
    const ws = { ...workspaceOf(['3d', 'embedding'], [0.6, 0.4]), maximized: 'P2' }
    const g = setLayout(ws, 'grid')
    expect(g.layout).toBe('grid')
    expect(g.panes).toBe(ws.panes)
    expect(g.maximized).toBeNull()
  })
})

describe('grid', () => {
  it('shapes, spans and resizes', () => {
    expect([1, 2, 3, 4, 5, 6, 7].map((n) => gridShape(n))).toEqual([
      { cols: 1, rows: 1 }, { cols: 2, rows: 1 }, { cols: 2, rows: 2 }, { cols: 2, rows: 2 },
      { cols: 3, rows: 2 }, { cols: 3, rows: 2 }, { cols: 3, rows: 3 },
    ])
    expect([0, 1, 2, 3, 4].map((i) => gridSpan(i, 5))).toEqual([1, 1, 1, 1, 2]) // the last fills its row
    expect(gridSpan(3, 4)).toBe(1)
    let ws = workspaceOf(['3d', 'embedding', 'genome', 'matrix', 'stats'], undefined, 'grid') // 5 views: 3 × 2
    expect(gridSizes(ws)).toEqual({ cols: [1 / 3, 1 / 3, 1 / 3], rows: [0.5, 0.5] })
    ws = moveGridSplitter(ws, 'cols', 0, 0.5)
    expect(gridSizes(ws).cols[0]).toBeCloseTo(0.5)
    expect(gridSizes(ws).cols[1]).toBeCloseTo(1 / 6)
    ws = moveGridSplitter(ws, 'rows', 0, 0.95) // clamped: the other row keeps MIN_FRAC
    expect(gridSizes(ws).rows[1]).toBeCloseTo(MIN_FRAC)
    expect(parseWorkspace(JSON.parse(JSON.stringify(ws)))).toEqual(ws)
    // same shape (6 views): kept; another shape (7 views, 3 × 3): equal again
    expect(gridSizes(addPane(ws, 'genome')).rows[1]).toBeCloseTo(MIN_FRAC)
    expect(gridSizes(addPane(addPane(ws, 'genome'), 'stats')).rows).toEqual([1 / 3, 1 / 3, 1 / 3])
    expect(moveGridSplitter(ws, 'cols', 5, 0.5)).toBe(ws)
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
    let ws = addPane(workspaceOf(['3d', 'embedding'], [0.6, 0.4]), '3d')
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
    const ws = addPane(workspaceOf(['3d', 'embedding'], [0.6, 0.4]), 'embedding')
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
    expect(paneSignature(useStore.getState().workspace)).toBe(paneSignature(defaultWorkspace(true)))
    useStore.getState().setWorkspace((w) => setLayout(w, 'rows'))
    useStore.getState().ensureDefaultWorkspace(false)
    expect(useStore.getState().workspace.layout).toBe('rows')
    expect(paneSignature(useStore.getState().workspace)).toBe(paneSignature(defaultWorkspace(true)))
  })
  it('each dataset keeps its own layout', () => {
    useStore.setState({ workspace: defaultWorkspace(false), workspaceOwner: null, savedWorkspaces: {}, workspaceTouched: false })
    const st = () => useStore.getState()
    st().ensureDefaultWorkspace(true, 'a')
    expect(paneSignature(st().workspace)).toBe(paneSignature(defaultWorkspace(true)))
    st().setWorkspace((w) => setLayout(w, 'rows'))
    // another dataset: its own default, not a's layout
    st().ensureDefaultWorkspace(false, 'b')
    expect(st().workspace.layout).not.toBe('rows')
    expect(st().workspaceTouched).toBe(false)
    expect(st().workspace.panes.map((p) => p.type)).toEqual(defaultWorkspace(false).panes.map((p) => p.type))
    // back to a: its arranged layout
    st().ensureDefaultWorkspace(true, 'a')
    expect(st().workspace.layout).toBe('rows')
    expect(st().workspaceTouched).toBe(true)
    expect(Object.keys(st().savedWorkspaces)).toEqual(['a'])
    expect(parseWorkspaces({ a: st().workspace, junk: { layout: 'x' } })).toEqual({ a: st().workspace })
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
  it('defaults to every supported view for cells in tissue', () => {
    const t = (k: Parameters<typeof defaultWorkspace>[0]) => defaultWorkspace(k).panes.map((p) => p.type)
    expect(t({ ...none, hasSpatial: true, hasTracks: true, hasEmbeddings: true })).toEqual(['spatial', 'embedding', 'genome'])
    expect(t({ ...none, hasSpatial: true, hasEmbeddings: true })).toEqual(['spatial', 'embedding'])
    expect(t({ ...none, hasSpatial: true, hasContactMaps: true, manyCells: true })).toEqual(['spatial', 'genome', 'stats'])
    expect(t({ ...none, hasEmbeddings: true })).toEqual(['embedding'])
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

describe('3-D views styled on their own', () => {
  it('keeps each view\'s style changes over the layer style, persisted', () => {
    const layer = { name: 'ds', style: { mode: 'tube', colorMode: 'rainbow', color: '#ffffff', opacity: 1, lineWidth: 1, tubeRadius: null, pointSize: 4, highQuality: false } as const }
    let ws = workspaceOf(['3d', '3d'])
    ws = setPaneLayerStyle(ws, 'P1', 'ds', { mode: 'line' })
    ws = setPaneLayerStyle(ws, 'P1', 'ds', { opacity: 0.5 })
    expect(effectiveStyle(layer, ws.panes[0])).toMatchObject({ mode: 'line', opacity: 0.5, colorMode: 'rainbow' })
    expect(effectiveStyle(layer, ws.panes[1])).toBe(layer.style) // the other view: untouched
    const back = parseWorkspace(JSON.parse(JSON.stringify(ws)))!
    expect(back.panes[0].layerStyles).toEqual({ ds: { mode: 'line', opacity: 0.5 } })
    expect(parseLayerStyles({ ds: { mode: 'blob', opacity: 7, color: 'red' } })).toBeUndefined()
  })
})

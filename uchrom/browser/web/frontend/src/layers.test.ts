import { beforeEach, describe, expect, it } from 'vitest'
import { descendantIds, removeCascade, treeOrder, uniqueName } from './layers'
import { useStore } from './store'
import { decodeGeometry } from './api'
import { encodeGeometry, sampleHeader } from './testing'
import type { DatasetSummary, Layer } from './types'

const L = (id: string, parentId: string | null, name = id): Layer => ({
  id,
  name,
  datasetId: 'd',
  parentId,
  filter: {},
  visible: true,
  style: {} as Layer['style'],
  geometry: null,
  loading: false,
  error: null,
})

describe('layer tree helpers', () => {
  const layers = [L('r', null), L('a', 'r'), L('b', 'r'), L('a1', 'a'), L('x', null)]
  it('collects descendants', () => {
    expect([...descendantIds(layers, 'a')].sort()).toEqual(['a', 'a1'])
    expect(descendantIds(layers, 'r').size).toBe(4)
  })
  it('removes a subtree', () => {
    expect(removeCascade(layers, 'a').map((l) => l.id)).toEqual(['r', 'b', 'x'])
  })
  it('orders depth-first with depth', () => {
    expect(treeOrder(layers).map(({ layer, depth }) => `${layer.id}:${depth}`)).toEqual(['r:0', 'a:1', 'a1:2', 'b:1', 'x:0'])
  })
  it('treats orphans as roots', () => {
    expect(treeOrder([L('o', 'gone')]).map((r) => r.depth)).toEqual([0])
  })
  it('makes names unique', () => {
    expect(uniqueName(layers, 'new')).toBe('new')
    expect(uniqueName([L('1', null, 'chr1'), L('2', null, 'chr1 (2)')], 'chr1')).toBe('chr1 (3)')
  })
})

const ds: DatasetSummary = {
  id: 'd1',
  name: 'cell1',
  path: '/tmp/cell1.h5cd',
  n_spots: 10,
  n_traces: 2,
  n_cells: 1,
  xyz_unit: null,
  trace_mode: false,
  chroms: [],
}

describe('store', () => {
  beforeEach(() => {
    useStore.setState({ datasets: [], layers: [], activeDatasetId: null, selectedLayerId: null, pick: null })
  })

  it('creates one root layer per dataset', () => {
    useStore.getState().setDatasets([ds])
    useStore.getState().setDatasets([ds])
    const s = useStore.getState()
    expect(s.layers.length).toBe(1)
    expect(s.layers[0]).toMatchObject({ datasetId: 'd1', parentId: null, name: 'cell1', filter: {} })
    expect(s.activeDatasetId).toBe('d1')
    expect(s.selectedLayerId).toBe(s.layers[0].id)
  })

  it('adds, renames and cascades deletes of child layers', () => {
    const st = useStore.getState()
    st.addDataset(ds)
    const root = useStore.getState().layers[0].id
    const child = st.addLayer({ datasetId: 'd1', parentId: root, name: 'chr1', filter: { chroms: ['chr1'] } })
    const grand = st.addLayer({ datasetId: 'd1', parentId: child, name: 'chr1', filter: { chroms: ['chr1'] } })
    let s = useStore.getState()
    expect(s.layers.find((l) => l.id === grand)!.name).toBe('chr1 (2)')
    expect(s.layers.find((l) => l.id === root)!.visible).toBe(false) // parent hidden by subset
    expect(s.selectedLayerId).toBe(grand)

    st.renameLayer(child, '  first  ')
    st.renameLayer(child, '   ')
    expect(useStore.getState().layers.find((l) => l.id === child)!.name).toBe('first')

    st.removeLayer(child)
    s = useStore.getState()
    expect(s.layers.map((l) => l.id)).toEqual([root])
    expect(s.selectedLayerId).toBeNull()
  })

  it('style updates are per layer and immutable', () => {
    const st = useStore.getState()
    st.addDataset(ds)
    const root = useStore.getState().layers[0]
    st.setStyle(root.id, { mode: 'tube' })
    const after = useStore.getState().layers[0]
    expect(after.style.mode).toBe('tube')
    expect(root.style.mode).toBe('line')
    expect(after.style).not.toBe(root.style)
  })

  it("refits the camera on a new subset's first geometry only", () => {
    const st = useStore.getState()
    st.addDataset(ds)
    const root = useStore.getState().layers[0].id
    const geom = decodeGeometry(
      encodeGeometry(sampleHeader(), [0, 0, 0, 1, 0, 0, 2, 0, 0, 3, 4, 0, 3, 5, 0], [0, 100, 200, 100, 200], [0, 3, 5]),
    )
    const token = () => useStore.getState().resetViewToken
    const t0 = token()
    st.setGeometry(root, geom) // root: fitted by addDataset, no extra refit
    expect(token()).toBe(t0)
    const child = st.addLayer({ datasetId: 'd1', parentId: root, name: 'sub', filter: { trace_ids: ['t1'] } })
    st.setGeometry(child, geom)
    expect(token()).toBe(t0 + 1)
    st.setGeometry(child, geom) // reload / restyle keeps the user's camera
    expect(token()).toBe(t0 + 1)
  })

  it('removing a dataset drops its layers', () => {
    const st = useStore.getState()
    st.addDataset(ds)
    st.addDataset({ ...ds, id: 'd2', name: 'other' })
    st.removeDataset('d2')
    const s = useStore.getState()
    expect(s.datasets.map((d) => d.id)).toEqual(['d1'])
    expect(s.layers.every((l) => l.datasetId === 'd1')).toBe(true)
    expect(s.activeDatasetId).toBe('d1')
  })
})

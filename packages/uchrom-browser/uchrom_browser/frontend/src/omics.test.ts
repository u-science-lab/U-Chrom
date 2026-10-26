import { beforeEach, describe, expect, it } from 'vitest'
import { decodePointSet } from './api'
import { MISSING_RGB, fieldColor, fieldRange, labelColor, skewedField, vertexColors, viridis } from './colors'
import { decodeGeometry } from './api'
import { splitCellFields } from './components/CellInfoPanel'
import { fieldLabel, fmtNum } from './components/format'
import { labelCounts, splitPoints } from './render/points'
import { activeView, fieldKey, orderedCells, useStore } from './store'
import { encodeGeometry, sampleHeader } from './testing'
import type { DatasetSummary } from './types'

const f32 = (rgb: number[]) => rgb.map((x) => Math.fround(x))

describe('field colour scale', () => {
  it('viridis endpoints and clamping', () => {
    expect(viridis(0)).toEqual([0.267, 0.005, 0.329])
    expect(viridis(1)).toEqual([0.993, 0.906, 0.144])
    expect(viridis(-3)).toEqual(viridis(0))
    expect(viridis(7)).toEqual(viridis(1))
    expect(viridis(NaN)).toEqual(viridis(0))
  })
  it('range is [min, p99] of finite values', () => {
    const vals = [...Array.from({ length: 100 }, (_, i) => i), 10_000, null, NaN]
    expect(fieldRange(vals)).toEqual([0, 99])
    expect(fieldRange([5, 5, null])).toEqual([5, 6]) // degenerate
    expect(fieldRange([])).toEqual([0, 1])
  })
  it('skewed counts go on a log1p scale', () => {
    const counts = Array.from({ length: 1000 }, (_, i) => Math.round(Math.exp((i / 1000) * 9))) // log-uniform 1 … 8000
    expect(skewedField(counts)).toBe(true)
    expect(skewedField(Array.from({ length: 100 }, (_, i) => i))).toBe(false) // uniform
    expect(skewedField([...counts.map((c) => -c), 5])).toBe(false) // negative values
    expect(skewedField([1, 2])).toBe(false)
    expect(fieldColor(1000, [0, 1000], true)).toEqual(viridis(1))
    expect(fieldColor(Math.expm1(Math.log1p(1000) / 2), [0, 1000], true)[0]).toBeCloseTo(viridis(0.5)[0])
  })
  it('missing values are grey; above range saturates', () => {
    expect(fieldColor(null, [0, 10])).toEqual(MISSING_RGB)
    expect(fieldColor(NaN, [0, 10])).toEqual(MISSING_RGB)
    expect(fieldColor(1e6, [0, 10])).toEqual(viridis(1))
  })
  it("'field' mode colours each cell's segments by its value", () => {
    const seg = (trace_id: string, cell_id: string | null) => ({ trace_id, chrom: 'chr1', cell_id, n_points: 1, start: 0, end: 1 })
    const g = decodeGeometry(
      encodeGeometry({ ...sampleHeader(), segments: [seg('a', 'c1'), seg('b', 'c2'), seg('c', 'c3'), seg('d', null)] }, Array(12).fill(0), [0, 0, 0, 0], [0, 1, 2, 3, 4]),
    )
    const cellValues = new Map<string, number | null>([['c1', 0], ['c2', 10], ['c3', null]])
    const c = vertexColors(g, 'field', '#fff', { cellValues, fieldRange: [0, 10] })
    const rgb = (i: number) => Array.from(c.slice(3 * i, 3 * i + 3))
    expect(rgb(0)).toEqual(f32(viridis(0)))
    expect(rgb(1)).toEqual(f32(viridis(1)))
    expect(rgb(2)).toEqual(f32(MISSING_RGB))
    expect(rgb(3)).toEqual(f32(MISSING_RGB))
  })
  it('label colours are stable and differ between labels', () => {
    expect(labelColor('Nanog')).toEqual(labelColor('Nanog'))
    expect(labelColor('Nanog')).not.toEqual(labelColor('Sox2'))
  })
})

const points = () =>
  decodePointSet('rna', {
    n: 4,
    positions: [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3],
    cell_ids: ['c1', 'c1', 'c2', 'c2'],
    labels: ['Nanog', 'Sox2', 'Nanog', 'Sox2'],
    values: { peak_intensity: [1, 2, 3, null] },
  })

describe('point sets', () => {
  it('rejects inconsistent payloads', () => {
    expect(() => decodePointSet('x', { n: 2, positions: [0, 0, 0], cell_ids: ['a', 'b'], labels: ['a', 'b'], values: {} })).toThrow('inconsistent')
  })
  it('splits by focus and hides labels / non-finite positions', () => {
    const ps = points()
    ps.positions[11] = NaN
    let s = splitPoints(ps, new Set(), null)
    expect(Array.from(s.main)).toEqual([0, 1, 2]) // point 3 has NaN z
    expect(s.context.length).toBe(0)
    s = splitPoints(ps, new Set(), 'c2')
    expect(Array.from(s.main)).toEqual([2])
    expect(Array.from(s.context)).toEqual([0, 1])
    s = splitPoints(ps, new Set(['Sox2']), 'c1')
    expect(Array.from(s.main)).toEqual([0])
    expect(Array.from(s.context)).toEqual([2])
  })
  it('counts labels by frequency', () => {
    const ps = points()
    ps.labels[1] = 'Nanog'
    expect(labelCounts(ps)).toEqual([
      { value: 'Nanog', count: 3 },
      { value: 'Sox2', count: 1 },
    ])
  })
})

describe('cell details formatting', () => {
  it('splits attributes from RNA counts, sorted by count', () => {
    const { attrs, rna } = splitCellFields({ nucleus_area_um2: 158.7, 'rna.Sox2': 6, 'rna.Zfp42': 95, 'rna.Bad': null })
    expect(attrs).toEqual([['nucleus_area_um2', 158.7]])
    expect(rna.map((r) => r.label)).toEqual(['Zfp42', 'Sox2'])
  })
  it('labels and numbers', () => {
    expect(fieldLabel('nucleus_area_um2')).toBe('nucleus area (µm²)')
    expect(fieldLabel('rna.Nanog')).toBe('Nanog')
    expect(fmtNum(1234)).toBe('1,234')
    expect(fmtNum(158.66)).toBe('159')
    expect(fmtNum(0.012345)).toBe('0.0123')
    expect(fmtNum(null)).toBe('—')
  })
})

describe('store: fields, sorting, point visibility', () => {
  const ds: DatasetSummary = {
    id: 'd1', name: 'x', path: '/x', n_spots: 1, n_traces: 1, n_cells: 3, xyz_unit: 'um', trace_mode: true,
    chroms: [{ name: 'chr1', start: 0, end: 1, n_spots: 1, n_traces: 1 }],
    cell_fields: [{ name: 'rna.Nanog', group: 'rna', label: 'Nanog', min: 0, max: 9, n_valid: 3 }],
    point_sets: [{ name: 'rna', n_points: 4, label_field: 'gene', labels: [], value_fields: [] }],
  }
  beforeEach(() => {
    useStore.setState({ datasets: [], layers: [], activeDatasetId: null, selectedLayerId: null, pick: null, views: {}, cells: {}, cellValues: {}, pointSets: {} })
    const st = useStore.getState()
    st.addDataset(ds)
    st.setCells('d1', ['c1', 'c2', 'c10'].map((cell_id) => ({ cell_id, n_spots: 1, n_traces: 1, n_chroms: 1 })))
  })

  it('choosing a field switches the overview to field colouring', () => {
    useStore.getState().setCellField('rna.Nanog')
    expect(activeView(useStore.getState())).toMatchObject({ overviewColor: 'field', cellField: 'rna.Nanog' })
  })

  it('orders cells by value when sorting by the field; stepping follows it', () => {
    const st = useStore.getState()
    st.setCellField('rna.Nanog')
    st.setCellValues('d1', 'rna.Nanog', new Map([['c1', 1], ['c2', null], ['c10', 9]]))
    expect(useStore.getState().cellValues[fieldKey('d1', 'rna.Nanog')].get('c10')).toBe(9)
    expect(orderedCells(useStore.getState()).map((c) => c.cell_id)).toEqual(['c1', 'c2', 'c10'])
    st.setCellSort('value')
    expect(orderedCells(useStore.getState()).map((c) => c.cell_id)).toEqual(['c10', 'c1', 'c2'])
    st.stepCell(1)
    expect(activeView(useStore.getState()).focusCell).toBe('c10')
    st.stepCell(1)
    expect(activeView(useStore.getState()).focusCell).toBe('c1')
  })

  it('toggles point sets, labels and marker size per dataset view', () => {
    const st = useStore.getState()
    st.togglePointSet('rna')
    st.toggleLabel('rna', 'Nanog')
    st.toggleLabel('rna', 'Sox2')
    st.toggleLabel('rna', 'Nanog')
    st.setPointSize(11)
    const v = activeView(useStore.getState())
    expect(v.hiddenPointSets).toEqual(['rna'])
    expect(v.hiddenLabels).toEqual({ rna: ['Sox2'] })
    expect(v.pointSize).toBe(11)
    st.setHiddenLabels('rna', [])
    expect(activeView(useStore.getState()).hiddenLabels.rna).toEqual([])
  })
})

describe('colourable fields', () => {
  it('drops id columns and puts 0/1 flags last', async () => {
    const { colourableFields } = await import('./components/format')
    const f = (name: string, min: number, max: number) => ({ name, group: name.includes('.') ? name.split('.')[0] : 'cell', label: name, min, max, n_valid: 1 })
    const out = colourableFields([f('keep1', 0, 1), f('extra_cell_roi_id', 0, 0), f('nucleus_area_um2', 80, 400), f('rna.Nanog', 0, 52)])
    expect(out.map((x) => x.name)).toEqual(['nucleus_area_um2', 'rna.Nanog', 'keep1'])
  })
})

describe('categorical label colours', () => {
  it('gives the first 24 labels distinct colours, neighbours far apart', async () => {
    const { categoricalColor, labelColorMap } = await import('./colors')
    const cols = Array.from({ length: 24 }, (_, i) => categoricalColor(i).join(','))
    expect(new Set(cols).size).toBe(24)
    for (let i = 0; i < 23; i++) {
      const [a, b] = [categoricalColor(i), categoricalColor(i + 1)]
      expect(Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])).toBeGreaterThan(0.3)
    }
    const colorOf = labelColorMap(['Lgr4', 'Actb'])
    expect(colorOf('Lgr4')).toEqual(categoricalColor(0))
    expect(colorOf('Actb')).toEqual(categoricalColor(1))
  })
})

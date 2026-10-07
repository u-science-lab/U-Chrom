import { describe, expect, it } from 'vitest'
import { decodeGeometry } from './api'
import { HIDDEN_RGB, MISSING_RGB, categoricalColor, categoryIndex, cellRgb, cellValueColor, labelColor, vertexColors } from './colors'
import { fmtValue } from './components/format'
import { DEFAULT_VIEW, defaultCategoryField, hasCoords, initialView, orderedCells } from './store'
import { encodeGeometry, sampleHeader } from './testing'
import type { CellField, CellInfo, CellValue, DatasetSummary } from './types'

const typeField: CellField = {
  name: 'cell_type',
  group: 'cell',
  label: 'cell_type',
  kind: 'category',
  min: null,
  max: null,
  n_valid: 4,
  categories: [
    { value: 'L2/3', count: 2 },
    { value: 'Astro', count: 1 },
    { value: 'Micro', count: 1 },
  ],
}
const numField: CellField = { name: 'area', group: 'cell', label: 'area', kind: 'numeric', min: 0, max: 9, n_valid: 4 }
const ds = (fields: CellField[], extra: Partial<DatasetSummary> = {}) => ({ id: 'd', cell_fields: fields, has_coords: true, n_spots: 10, ...extra }) as DatasetSummary

describe('categorical cell colours', () => {
  it('indexes categories in the field order, hidden ones as −1, unknown ones appended', () => {
    const idx = categoryIndex(typeField, ['Astro'], ['Micro', 'Oligo', null])
    expect([...idx]).toEqual([
      ['L2/3', 0],
      ['Astro', -1],
      ['Micro', 2],
      ['Oligo', 3],
    ])
  })
  it('colours by category index, grey for missing, dark for hidden', () => {
    const categories = categoryIndex(typeField, ['Astro'])
    expect(cellValueColor('L2/3', { categories })).toEqual(categoricalColor(0))
    expect(cellValueColor('Micro', { categories })).toEqual(categoricalColor(2))
    expect(cellValueColor('Astro', { categories })).toEqual(HIDDEN_RGB)
    expect(cellValueColor(null, { categories })).toEqual(MISSING_RGB)
    expect(cellValueColor('nope', { categories })).toEqual(MISSING_RGB)
  })
  it('falls back to hashed colours past 24 categories', () => {
    const many: CellField = { ...typeField, categories: Array.from({ length: 30 }, (_, i) => ({ value: `t${i}`, count: 1 })) }
    const categories = categoryIndex(many)
    expect(cellValueColor('t25', { categories })).toEqual(labelColor('t25'))
  })
  it('cellRgb and vertexColors use the category colours in field mode', () => {
    const cellValues = new Map<string, CellValue>([['c1', 'Micro']])
    const categories = categoryIndex(typeField)
    expect(cellRgb('c1', 'field', '#fff', { cellValues, categories })).toEqual(categoricalColor(2))
    const geom = decodeGeometry(encodeGeometry(sampleHeader(), new Array(15).fill(0), [0, 100, 200, 100, 200], [0, 3, 5]))
    const c = vertexColors(geom, 'field', '#fff', { cellValues, categories })
    const [r, g, b] = categoricalColor(2)
    expect(c[0]).toBeCloseTo(r)
    expect(c[1]).toBeCloseTo(g)
    expect(c[2]).toBeCloseTo(b)
    // the second trace has no cell → missing grey
    expect(c[3 * 3]).toBeCloseTo(MISSING_RGB[0])
  })
  it('numeric fields keep viridis', () => {
    const cellValues = new Map<string, CellValue>([['c1', 9]])
    expect(cellRgb('c1', 'field', '#fff', { cellValues, fieldRange: [0, 9] })[2]).toBeLessThan(0.3) // yellow end
  })
  it('formats values of both kinds', () => {
    expect(fmtValue('L2/3')).toBe('L2/3')
    expect(fmtValue(1234)).toBe('1,234')
    expect(fmtValue(null)).toBe('—')
  })
})

describe('default overview colouring', () => {
  it('prefers cell_type, else a type / cluster category, never a numeric field', () => {
    expect(defaultCategoryField(ds([numField, typeField]))?.name).toBe('cell_type')
    const cluster = { ...typeField, name: 'leiden_cluster', label: 'leiden_cluster' }
    expect(defaultCategoryField(ds([numField, cluster]))?.name).toBe('leiden_cluster')
    const other = { ...typeField, name: 'batch', label: 'batch' }
    expect(defaultCategoryField(ds([other]))).toBeNull()
    expect(defaultCategoryField(ds([{ ...numField, name: 'type_score' }]))).toBeNull()
  })
  it('initial view colours by the cell type when there is one', () => {
    expect(initialView(ds([typeField]))).toMatchObject({ overviewColor: 'field', cellField: 'cell_type' })
    expect(initialView(ds([numField]))).toBe(DEFAULT_VIEW)
  })
  it('knows when a dataset has no coordinates', () => {
    expect(hasCoords(ds([]))).toBe(true)
    expect(hasCoords(ds([], { has_coords: false }))).toBe(false)
    expect(hasCoords(ds([], { n_spots: 0 }))).toBe(false)
    expect(hasCoords(undefined)).toBe(false)
  })
})

describe('cell order by a categorical field', () => {
  it('groups cells in legend order, missing last', () => {
    const cells = ['a', 'b', 'c', 'd', 'e'].map((cell_id) => ({ cell_id, n_spots: 0, n_traces: 0, n_chroms: 0 }) as CellInfo)
    const vals = new Map<string, CellValue>([
      ['a', 'Micro'],
      ['b', 'L2/3'],
      ['c', null],
      ['d', 'Astro'],
      ['e', 'L2/3'],
    ])
    const order = orderedCells({
      activeDatasetId: 'd',
      cells: { d: cells },
      views: { d: { ...DEFAULT_VIEW, overviewColor: 'field', cellField: 'cell_type', cellSort: 'value' } },
      cellValues: { 'd\u0000cell_type': vals },
      datasets: [ds([typeField])],
    })
    expect(order.map((c) => c.cell_id)).toEqual(['b', 'e', 'd', 'a', 'c'])
  })
})

import { describe, expect, it } from 'vitest'
import { summary } from './StorePanel'

describe('store tree lines', () => {
  it('say what each node holds', () => {
    expect(summary({ name: 'umap', path: 'cellm/umap', kind: 'array', bytes: 9, shape: [1799, 2], dtype: 'float64', n_chunks: 1 })).toBe('1,799 × 2 · float64 · 1 chunk')
    expect(summary({ name: 'bins.parquet', path: 't', kind: 'table', bytes: 9, rows: 41, columns: ['chrom', 'start'], row_groups: 1 })).toBe('41 rows · 2 columns · 1 row group')
    expect(summary({ name: 'index', path: 'index', kind: 'group', bytes: 9, children: [] })).toBe('group · 0 items')
    expect(summary({ name: 'x', path: 'x', kind: 'table', bytes: 9, error: 'ArrowInvalid: …' })).toBe('ArrowInvalid: …')
    // a store read over HTTP: the chunk files are not listed, the array gives its uncompressed size
    expect(summary({ name: 'pix', path: 'p', kind: 'array', bytes: null, nbytes: 2_400_000, shape: [100_000, 3], dtype: 'int64' })).toBe('100,000 × 3 · int64 · 2.4 MB uncompressed')
  })
})

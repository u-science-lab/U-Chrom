import { describe, expect, it } from 'vitest'
import { addRecent, baseName, breadcrumbs, datasetBadges, datasetCounts, fmtSize, parseRecent, RECENT_MAX } from './datasets'
import type { DatasetSummary } from './types'

describe('dataset helpers', () => {
  it('breadcrumbs from the root', () => {
    expect(breadcrumbs('/Users/a/data')).toEqual([
      { label: '/', path: '/' },
      { label: 'Users', path: '/Users' },
      { label: 'a', path: '/Users/a' },
      { label: 'data', path: '/Users/a/data' },
    ])
    expect(breadcrumbs('/')).toEqual([{ label: '/', path: '/' }])
    expect(breadcrumbs('C:\\data\\x', '\\')).toEqual([
      { label: 'C:', path: 'C:\\' },
      { label: 'data', path: 'C:\\data' },
      { label: 'x', path: 'C:\\data\\x' },
    ])
  })
  it('sizes, names', () => {
    expect(fmtSize(512)).toBe('512 B')
    expect(fmtSize(2_300_000)).toBe('2.3 MB')
    expect(fmtSize(880_000_000)).toBe('880 MB')
    expect(fmtSize(null)).toBe('')
    expect(baseName('/a/b/mouse.chromdata.zarr/')).toBe('mouse.chromdata.zarr')
  })
  it('what a dataset holds', () => {
    const d = { n_cells: 4290, n_spots: 0, has_coords: false, spatial: [{}], contact_maps: [], tracks: [{}], embeddings: [{}] } as unknown as DatasetSummary
    expect(datasetBadges(d)).toEqual(['spatial', 'tracks', 'embeddings'])
    expect(datasetCounts(d)).toBe('4,290 cells')
    expect(datasetCounts({ ...d, n_spots: 2000 })).toBe('4,290 cells · 2,000 spots')
  })
  it('recent paths: newest first, no duplicates, capped', () => {
    expect(addRecent(['/a', '/b'], '/b')).toEqual(['/b', '/a'])
    const many = Array.from({ length: 20 }, (_, i) => `/p${i}`)
    expect(addRecent(many, '/new')).toHaveLength(RECENT_MAX)
    expect(parseRecent(['/a', 3, '', null])).toEqual(['/a'])
    expect(parseRecent('junk')).toEqual([])
  })
})

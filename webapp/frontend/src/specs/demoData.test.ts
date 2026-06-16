import { describe, expect, it } from 'vitest'
import { DEMO_OPTIONS, UCHROM_DEMO_DATA_PATH } from './demoData'

describe('demoData', () => {
  it('offers exactly the U-Chrom and official demos for the demo menu', () => {
    expect(DEMO_OPTIONS).toEqual([
      { id: 'uchrom-demo', label: 'U-Chrom Demo' },
      { id: 'official-demo', label: 'Official Demo' },
    ])
  })

  it('uses the richer local ChromData fixture through a portable relative path', () => {
    expect(UCHROM_DEMO_DATA_PATH).toBe('example-data/rich_multicell.h5cd')
    expect(UCHROM_DEMO_DATA_PATH.startsWith('/')).toBe(false)
  })
})

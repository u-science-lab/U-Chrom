import { describe, expect, it } from 'vitest'
import { regionToFollow } from './SpatialView'

describe('Spatial view follows the focus', () => {
  const ids = ['a1', 'a2', 'b1', 'b2', 'b3']
  const regions = ['A', 'A', 'B', 'B', 'B']
  it('moves to the region holding most of the focused cells', () => {
    expect(regionToFollow(regions, ids, new Set(['b1']), 'A')).toBe('B')
    expect(regionToFollow(regions, ids, new Set(['a1', 'b1', 'b2']), null)).toBe('B')
  })
  it('stays when the current region has some, or nothing is focused', () => {
    expect(regionToFollow(regions, ids, new Set(['a1', 'b1', 'b2']), 'A')).toBeNull()
    expect(regionToFollow(regions, ids, null, 'A')).toBeNull()
    expect(regionToFollow(regions, ids, new Set(['zz']), 'A')).toBeNull()
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { makeDefaultContactSpec } from './localContactMapSpec'
import { sanitizeUrls } from '../urlSafety'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('makeDefaultContactSpec', () => {
  it('builds a Gosling 1.x matrix heatmap with a parseable tileset URL', () => {
    const spec = makeDefaultContactSpec('chr1', 'mm10') as any
    const track = spec.views[0].tracks[0]

    expect(track.alignment).toBeUndefined()
    expect(track.data).toEqual({
      type: 'matrix',
      url: 'http://localhost/api/v1/tileset_info/?d=contact-chr1',
    })
    expect(track.x.field).toBe('xs')
    expect(track.xe.field).toBe('xe')
    expect(track.y.field).toBe('ys')
    expect(track.ye.field).toBe('ye')
  })

  it('survives the client URL sanitizer for same-origin tileset URLs', () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost' } })
    const spec = makeDefaultContactSpec('chr1', 'mm10') as any
    const cleaned = sanitizeUrls(spec) as any

    expect(cleaned.views[0].tracks[0].data.url).toBe(
      'http://localhost/api/v1/tileset_info/?d=contact-chr1',
    )
  })
})

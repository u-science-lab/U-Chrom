import { describe, expect, it } from 'vitest'
import { OFFICIAL_DEMO_SPEC } from './remoteDemoSpec'

type AnyTrack = Record<string, any>

function collectTracks(node: any): AnyTrack[] {
  if (!node || typeof node !== 'object') return []
  const own = node.data ? [node as AnyTrack] : []
  const children = Array.isArray(node.tracks) ? node.tracks.flatMap(collectTracks) : []
  const views = Array.isArray(node.views) ? node.views.flatMap(collectTracks) : []
  return [...own, ...children, ...views]
}

describe('OFFICIAL_DEMO_SPEC', () => {
  it('uses official Gosling remote sources with multiple data track types', () => {
    const tracks = collectTracks(OFFICIAL_DEMO_SPEC)
    const types = new Set(tracks.map(track => track.data?.type).filter(Boolean))

    expect(tracks.length).toBeGreaterThanOrEqual(8)
    expect(Array.from(types)).toEqual(expect.arrayContaining(['matrix', 'bigwig', 'beddb', 'multivec']))
  })

  it('renders matrix tracks using the Gosling 1.x-compatible matrix contract', () => {
    const matrixTracks = collectTracks(OFFICIAL_DEMO_SPEC)
      .filter(track => track.data?.type === 'matrix')

    expect(matrixTracks).toHaveLength(2)
    expect(matrixTracks.map(track => track.data.url)).toEqual(expect.arrayContaining([
      'https://server.gosling-lang.org/api/v1/tileset_info/?d=hffc6-microc-hg38',
      'https://server.gosling-lang.org/api/v1/tileset_info/?d=hffc6-hic-hg38',
    ]))

    for (const track of matrixTracks) {
      expect(track.mark).toBe('bar')
      expect(track.x.field).toBe('xs')
      expect(track.xe.field).toBe('xe')
      expect(track.y.field).toBe('ys')
      expect(track.ye.field).toBe('ye')
    }
  })
})

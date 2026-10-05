import { describe, expect, it, vi } from 'vitest'
import { decodeGeometry, listDatasets } from './api'
import { encodeGeometry, sampleHeader } from './testing'

describe('decodeGeometry', () => {
  it('round-trips the binary layout', () => {
    const pos = [0, 0, 0, 1, 0, 0, 2, 0, 0, 3, 4, 0, 1, 1, 0]
    const buf = encodeGeometry(sampleHeader(), pos, [0, 100, 200, 100, 200], [0, 3, 5])
    const g = decodeGeometry(buf)
    expect(g.header.n_points).toBe(5)
    expect(g.header.n_segments).toBe(2)
    expect(g.header.segments[1].cell_id).toBeNull()
    expect(Array.from(g.positions)).toEqual(pos)
    expect(Array.from(g.starts)).toEqual([0, 100, 200, 100, 200])
    expect(Array.from(g.offsets)).toEqual([0, 3, 5])
  })

  it('handles an empty selection', () => {
    const h = { ...sampleHeader(), segments: [], total_points: 0 }
    const g = decodeGeometry(encodeGeometry(h, [], [], [0]))
    expect(g.header.n_points).toBe(0)
    expect(g.offsets.length).toBe(1)
  })

  it('rejects truncated payloads', () => {
    const buf = encodeGeometry(sampleHeader(), new Array(15).fill(0), [0, 1, 2, 3, 4], [0, 3, 5])
    expect(() => decodeGeometry(buf.slice(0, buf.byteLength - 4))).toThrow(/expected/)
    expect(() => decodeGeometry(new ArrayBuffer(2))).toThrow()
  })
})

describe('request', () => {
  it('shares one network call between identical GETs in flight', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify([{ id: 'd1' }]), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const [a, b] = await Promise.all([listDatasets(), listDatasets()])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(a).toEqual(b)
    await listDatasets() // finished: a later call asks again (data may have changed)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    vi.unstubAllGlobals()
  })
})

describe('request while a hosted server wakes up', () => {
  it('waits for a 503 with Retry-After and asks again', async () => {
    vi.useFakeTimers()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('starting', { status: 503, headers: { 'Retry-After': '1' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 'd9' }]), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const p = listDatasets()
    await vi.advanceTimersByTimeAsync(1500)
    expect(await p).toEqual([{ id: 'd9' }])
    expect(fetchMock).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })
})

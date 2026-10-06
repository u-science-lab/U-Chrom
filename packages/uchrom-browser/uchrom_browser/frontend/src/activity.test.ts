import { describe, expect, it } from 'vitest'
import { useActivity, withPhase } from './activity'

describe('activity', () => {
  it('counts requests and never goes below zero', () => {
    const a = useActivity.getState()
    a.begin()
    a.begin()
    expect(useActivity.getState().pending).toBe(2)
    a.end()
    a.end()
    a.end()
    expect(useActivity.getState().pending).toBe(0)
  })
  it('a phase is shown while its work runs, also when it fails', async () => {
    let during: string[] = []
    await withPhase('p1', 'Opening x…', async () => {
      during = useActivity.getState().phases.map((p) => p.text)
    })
    expect(during).toEqual(['Opening x…'])
    expect(useActivity.getState().phases).toEqual([])
    await expect(withPhase('p2', 'boom', async () => Promise.reject(new Error('x')))).rejects.toThrow('x')
    expect(useActivity.getState().phases).toEqual([])
  })
  it('restarting a phase of the same id replaces it', () => {
    const a = useActivity.getState()
    a.startPhase('wake', 'one')
    a.startPhase('wake', 'two')
    expect(useActivity.getState().phases.map((p) => p.text)).toEqual(['two'])
    a.endPhase('wake')
  })
})

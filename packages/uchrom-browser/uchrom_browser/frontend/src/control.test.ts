import { afterEach, describe, expect, it, vi } from 'vitest'
import { startControl } from './control'
import { useStore } from './store'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  private listeners = new Map<string, (event: unknown) => void>()
  closed = false

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (event: unknown) => void) {
    this.listeners.set(type, listener)
  }

  emit(type: string, event: unknown) {
    this.listeners.get(type)?.(event)
  }

  close() {
    this.closed = true
  }
}

describe('control channel agent lease', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    FakeEventSource.instances = []
  })

  it('locks and unlocks the UI through the private lease action', async () => {
    const replies: Array<{ url: string; body: unknown }> = []
    vi.stubGlobal('EventSource', FakeEventSource as unknown as typeof EventSource)
    vi.stubGlobal('window', { addEventListener: vi.fn(), removeEventListener: vi.fn() })
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      replies.push({ url: String(input), body: JSON.parse(String(init?.body)) })
      return new Response('{}', { status: 200 })
    })

    const stop = startControl()
    const source = FakeEventSource.instances[0]
    source.emit('action', { data: JSON.stringify({ id: 'a1', name: '__agent_lease__', args: { active: true } }) })
    await vi.waitFor(() => expect(useStore.getState().agentLease).toBe(true))
    await vi.waitFor(() => expect(replies).toHaveLength(1))
    expect(replies[0]).toEqual({ url: '/api/control/results/a1', body: { ok: true, result: { active: true } } })

    source.emit('action', { data: JSON.stringify({ id: 'a2', name: '__agent_lease__', args: { active: false } }) })
    await vi.waitFor(() => expect(useStore.getState().agentLease).toBe(false))
    await vi.waitFor(() => expect(replies).toHaveLength(2))
    expect(replies[1]).toEqual({ url: '/api/control/results/a2', body: { ok: true, result: { active: false } } })
    stop()
  })
})

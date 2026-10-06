/**
 * What the page is waiting for, so that nobody stares at a blank screen: how many requests are in flight (a thin progress
 * bar at the top), and a named phase (connecting, waking the server, opening a dataset) with a card that counts the
 * seconds and says why it can take long.  Pure state: the components that show it are `ActivityBar` / `ActivityCard`.
 */
import { create } from 'zustand'

export interface Phase {
  id: string
  text: string
  /** extra line after a while ("the server starts on demand …") */
  hint?: string
  since: number
}

interface ActivityState {
  pending: number
  phases: Phase[]
  begin(): void
  end(): void
  startPhase(id: string, text: string, hint?: string): void
  updatePhase(id: string, text: string): void
  endPhase(id: string): void
}

export const useActivity = create<ActivityState>((set, get) => ({
  pending: 0,
  phases: [],
  begin: () => set((s) => ({ pending: s.pending + 1 })),
  end: () => set((s) => ({ pending: Math.max(0, s.pending - 1) })),
  startPhase: (id, text, hint) => {
    const rest = get().phases.filter((p) => p.id !== id)
    set({ phases: [...rest, { id, text, hint, since: Date.now() }] })
  },
  updatePhase: (id, text) => set((s) => ({ phases: s.phases.map((p) => (p.id === id ? { ...p, text } : p)) })),
  endPhase: (id) => set((s) => ({ phases: s.phases.filter((p) => p.id !== id) })),
}))

/** Run `work` as a named phase: it is shown while the promise is pending. */
export async function withPhase<T>(id: string, text: string, work: () => Promise<T>, hint?: string): Promise<T> {
  useActivity.getState().startPhase(id, text, hint)
  try {
    return await work()
  } finally {
    useActivity.getState().endPhase(id)
  }
}

export const WAKE_HINT = 'A hosted server starts when it is needed: the first visit after a quiet period can take up to a minute.'

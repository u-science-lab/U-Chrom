// Render-diagnostics feedback channel.
//
// When a view fails to render — a React error-boundary trip, or a Gosling spec
// that won't compile — we report it back to the backend (`view.diagnostic`) so
// the agent can SEE that its output broke (via get_view_state) and self-correct.
// This closes the render→agent loop the same way capture_view_snapshot closes
// the see→correct loop, but for failures rather than pixels.

import { ws } from './ws'
import { useAppStore } from './store'

export interface ViewDiagnostic {
  view_id: string
  level?: 'error' | 'warning'
  source?: string // 'react-error-boundary' | 'gosling-spec' | ...
  message: string
  detail?: string
  revision?: number | null
}

// Throttle identical diagnostics so a render that throws every frame can't spam
// the socket. Keyed by view_id+source+message, with a short cooldown.
const _lastSent = new Map<string, number>()
const COOLDOWN_MS = 2000

export function reportViewDiagnostic(diag: ViewDiagnostic): void {
  const key = `${diag.view_id}|${diag.source ?? ''}|${diag.message}`
  const now = Date.now()
  const last = _lastSent.get(key)
  if (last != null && now - last < COOLDOWN_MS) return
  _lastSent.set(key, now)

  const revision = diag.revision ?? useAppStore.getState().viewRevisions[diag.view_id] ?? null
  ws.send('view.diagnostic', {
    view_id: diag.view_id,
    level: diag.level ?? 'error',
    source: diag.source ?? 'render',
    message: diag.message,
    detail: diag.detail,
    revision,
  })
}

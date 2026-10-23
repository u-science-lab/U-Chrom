/**
 * Control channel: receive actions from the server (sent by `uchrom_browser.connect()` and other
 * callers of POST /api/control/actions), run them with `actions.ts` and post the result back.
 */

import { captureAgentUiState, restoreAgentUiState, runAction } from './actions'
import { runAsAgentMutation } from './mutationGate'
import { useStore } from './store'

const PAGE_ID = `p${Math.random().toString(36).slice(2, 10)}`
let PAGE_TOKEN = ''

async function reply(id: string, body: { ok: boolean; result?: unknown; error?: string }) {
  try {
    await fetch(`/api/control/results/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-UChrom-Page-Token': PAGE_TOKEN },
      body: JSON.stringify(body),
    })
  } catch {
    /* the caller times out */
  }
}

function markActive() {
  fetch(`/api/control/active?page=${PAGE_ID}`, { method: 'POST', headers: { 'X-UChrom-Page-Token': PAGE_TOKEN } }).catch(() => undefined)
}

/** Connect once; the browser's EventSource reconnects by itself after a server restart. */
export function startControl(): () => void {
  if (typeof EventSource === 'undefined') return () => undefined
  const es = new EventSource(`/api/control/events?page=${PAGE_ID}`)
  es.addEventListener('action', (ev) => {
    const msg = JSON.parse((ev as MessageEvent).data) as { id: string; name: string; args: Record<string, unknown> }
    const internalMutation = msg.args?.__agent_mutation__ === true
    const args = { ...(msg.args ?? {}) }
    delete args.__agent_mutation__
    const action = msg.name === '__agent_lease__'
      ? Promise.resolve((() => {
          const active = args.active === true
          useStore.getState().setAgentLease(active)
          return { active }
        })())
      : msg.name === '__agent_snapshot__'
      ? captureAgentUiState()
      : msg.name === '__agent_restore__'
        ? runAsAgentMutation(() => restoreAgentUiState(args.state, args.expected_canonical))
        : msg.name === '__agent_clear_lease__'
          ? Promise.resolve((() => {
              useStore.getState().setAgentLease(false)
              return { active: false, forced: true }
            })())
        : runAction(msg.name, args, { agentMutation: internalMutation })
    action
      .then((result) => reply(msg.id, { ok: true, result: result ?? null }))
      .catch((e: unknown) => reply(msg.id, { ok: false, error: e instanceof Error ? e.message : String(e) }))
  })
  // the page the researcher last used receives actions when several are open
  window.addEventListener('focus', markActive)
  es.addEventListener('hello', (ev) => {
    const data = JSON.parse((ev as MessageEvent).data) as { token?: string }
    PAGE_TOKEN = data.token ?? ''
    markActive()
  })
  return () => {
    es.close()
    window.removeEventListener('focus', markActive)
  }
}

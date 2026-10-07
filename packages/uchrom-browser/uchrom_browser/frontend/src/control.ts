/**
 * Control channel: receive actions from the server (sent by `uchrom_browser.connect()` and other
 * callers of POST /api/control/actions), run them with `actions.ts` and post the result back.
 */

import { runAction } from './actions'

const PAGE_ID = `p${Math.random().toString(36).slice(2, 10)}`

async function reply(id: string, body: { ok: boolean; result?: unknown; error?: string }) {
  try {
    await fetch(`/api/control/results/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    /* the caller times out */
  }
}

function markActive() {
  fetch(`/api/control/active?page=${PAGE_ID}`, { method: 'POST' }).catch(() => undefined)
}

/** Connect once; the browser's EventSource reconnects by itself after a server restart. */
export function startControl(): () => void {
  if (typeof EventSource === 'undefined') return () => undefined
  const es = new EventSource(`/api/control/events?page=${PAGE_ID}`)
  es.addEventListener('action', (ev) => {
    const msg = JSON.parse((ev as MessageEvent).data) as { id: string; name: string; args: Record<string, unknown> }
    runAction(msg.name, msg.args)
      .then((result) => reply(msg.id, { ok: true, result: result ?? null }))
      .catch((e: unknown) => reply(msg.id, { ok: false, error: e instanceof Error ? e.message : String(e) }))
  })
  // the page the researcher last used receives actions when several are open
  window.addEventListener('focus', markActive)
  es.addEventListener('hello', markActive)
  return () => {
    es.close()
    window.removeEventListener('focus', markActive)
  }
}

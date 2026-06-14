// Snapshot capture registry + orchestrator for capture_view_snapshot.
//
// The backend's capture_view_snapshot tool sends a `request_snapshot`
// (request_id + view_id); the agent then SEES the returned image and can
// self-correct. The wrinkle: panels are only mounted while their tab is active
// (see TabContainer), so to capture an arbitrary view we must (1) switch to its
// tab, (2) wait for that panel to mount + render, then (3) read its canvas.
//
// Each panel registers an async capturer under its view_id while mounted. The
// orchestrator switches tabs, waits (poll) for the capturer to appear and for a
// render frame to land, invokes it, and replies `snapshot_result`.

import { ws } from './ws'
import { useAppStore, type TabType } from './store'

export type SnapshotCapturer = () => Promise<string>

// view_id -> capturer. A panel sets its entry on mount, clears it on unmount.
const capturers = new Map<string, SnapshotCapturer>()

export function registerCapturer(viewId: string, fn: SnapshotCapturer): () => void {
  capturers.set(viewId, fn)
  return () => {
    if (capturers.get(viewId) === fn) capturers.delete(viewId)
  }
}

// view_id -> the tab that must be active for that panel to mount.
const VIEW_TO_TAB: Record<string, TabType> = {
  genomic: 'genomic',
  structure3d: 'structure3d',
  embedding: 'embedding',
}

function sleep(ms: number): Promise<void> {
  return new Promise(res => setTimeout(res, ms))
}

// Wait until a capturer for `viewId` is registered (panel mounted), up to
// `timeoutMs`. Returns the capturer or null on timeout.
async function waitForCapturer(viewId: string, timeoutMs: number): Promise<SnapshotCapturer | null> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const fn = capturers.get(viewId)
    if (fn) return fn
    await sleep(100)
  }
  return capturers.get(viewId) ?? null
}

// Handle one request_snapshot: switch tab, wait for mount+render, capture, reply.
async function handleRequest(requestId: string, viewId: string) {
  const reply = (data_url: string | null, error: string | null) =>
    ws.send('snapshot_result', { request_id: requestId, data_url, error })

  const tab = VIEW_TO_TAB[viewId]
  if (!tab) {
    reply(null, `unknown view_id '${viewId}'`)
    return
  }

  // Switch to the tab so its panel mounts (no-op if already active).
  const store = useAppStore.getState()
  if (store.activeTab !== tab) store.setActiveTab(tab)

  // Wait for the panel to register its capturer (mount), then give it a couple
  // of animation frames to actually paint before we read the canvas.
  const capturer = await waitForCapturer(viewId, 8000)
  if (!capturer) {
    reply(null, `view '${viewId}' did not mount in time`)
    return
  }
  // Two rAFs + a short delay: lets React commit and the renderer draw a frame.
  await new Promise<void>(res => requestAnimationFrame(() => requestAnimationFrame(() => res())))
  await sleep(150)

  try {
    const dataUrl = await capturer()
    if (!dataUrl) {
      reply(null, `view '${viewId}' produced an empty snapshot`)
      return
    }
    reply(dataUrl, null)
  } catch (e) {
    reply(null, `capture failed: ${e instanceof Error ? e.message : String(e)}`)
  }
}

// Wire the ws listener once. Idempotent across hot-reloads via a module flag.
let installed = false
export function installSnapshotOrchestrator(): () => void {
  if (installed) return () => {}
  installed = true
  const off = ws.onMessage('request_snapshot', (msg) => {
    const requestId = msg.request_id as string | undefined
    const viewId = msg.view_id as string | undefined
    if (!requestId || !viewId) return
    void handleRequest(requestId, viewId)
  })
  return () => {
    installed = false
    off()
  }
}

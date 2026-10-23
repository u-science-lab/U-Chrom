import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchAtlas, fetchHealth } from '../api'
import { buildHandoffState, handoffCommand, handoffSummary, type HandoffState } from '../handoff'
import { activeView, useStore } from '../store'
import type { AtlasDataset } from '../types'

export function isCatalogResponseCurrent(generation: number, currentGeneration: number, requestedPath: string, currentPath: string | null): boolean {
  return generation === currentGeneration && requestedPath === currentPath
}

export function isHandoffDialogEscape(key: string): boolean {
  return key === 'Escape'
}

export function trapHandoffDialogTab(event: { key: string; shiftKey: boolean; preventDefault: () => void }, focusables: Array<{ focus: () => void }>, active: { focus: () => void } | null): boolean {
  if (event.key !== 'Tab' || focusables.length === 0) return false
  const current = active ? focusables.indexOf(active) : -1
  const next = event.shiftKey
    ? (current <= 0 ? focusables.length - 1 : current - 1)
    : (current === -1 || current === focusables.length - 1 ? 0 : current + 1)
  event.preventDefault()
  focusables[next].focus()
  return true
}

export function HostedHandoff() {
  const dataset = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const view = useStore((s) => activeView(s))
  const workspace = useStore((s) => s.workspace)
  const [hosted, setHosted] = useState(false)
  const [atlasDataset, setAtlasDataset] = useState<AtlasDataset | null>(null)
  const [version, setVersion] = useState('Unknown')
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [state, setState] = useState<HandoffState | null>(null)
  const [command, setCommand] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [catalogPending, setCatalogPending] = useState(false)
  const catalogGeneration = useRef(0)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const modalRef = useRef<HTMLElement>(null)
  const wasOpen = useRef(false)

  useEffect(() => {
    let live = true
    fetchHealth().then((health) => { if (live) setHosted(!!health.hosted) }).catch(() => {})
    return () => { live = false }
  }, [])

  useEffect(() => {
    if (open) {
      wasOpen.current = true
      closeRef.current?.focus()
      const onKeyDown = (event: KeyboardEvent) => {
        if (isHandoffDialogEscape(event.key)) {
          event.preventDefault()
          setOpen(false)
          return
        }
        const active = document.activeElement as HTMLElement | null
        const focusables = modalRef.current ? Array.from(modalRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])')) : []
        trapHandoffDialogTab(event, focusables, active)
      }
      document.addEventListener('keydown', onKeyDown)
      return () => document.removeEventListener('keydown', onKeyDown)
    }
    if (wasOpen.current) {
      wasOpen.current = false
      triggerRef.current?.focus()
    }
  }, [open])

  useEffect(() => {
    catalogGeneration.current += 1
    setAtlasDataset(null)
    setVersion('Unknown')
    setCatalogPending(false)
  }, [dataset?.id, dataset?.path])

  const summary = useMemo(() => state && atlasDataset ? handoffSummary(state, { id: atlasDataset.id, name: atlasDataset.name ?? atlasDataset.title }, version) : [], [state, atlasDataset, version])
  if (!hosted || !dataset) return null

  const show = () => {
    if (!dataset) return
    const requestedPath = dataset.path
    const generation = ++catalogGeneration.current
    setAtlasDataset(null)
    setVersion('Unknown')
    setCatalogPending(true)
    const loadCatalog = async () => {
      try {
        const response = await fetchAtlas()
        const match = response.catalog?.datasets.find((entry) => entry.url.replace(/\/+$/, '') === dataset.path.replace(/\/+$/, '')) ?? null
        const current = useStore.getState()
        const currentDataset = current.datasets.find((entry) => entry.id === current.activeDatasetId)
        if (!isCatalogResponseCurrent(generation, catalogGeneration.current, requestedPath, currentDataset?.path ?? null)) return
        setAtlasDataset(match)
        setVersion(response.catalog?.updated ?? 'Unknown')
      } catch {
        if (generation !== catalogGeneration.current) return
        setAtlasDataset(null)
        setVersion('Unknown')
      } finally {
        if (generation === catalogGeneration.current) setCatalogPending(false)
      }
    }
    void loadCatalog()
    setState(buildHandoffState(view, workspace))
    setQuestion('')
    setCommand('')
    setError(null)
    setOpen(true)
  }

  const create = async () => {
    if (!state) return
    setBusy(true)
    setError(null)
    try {
      const response = await fetch('api/agent/handoffs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dataset_id: atlasDataset?.id, ...(question.trim() ? { question: question.trim() } : {}), page_state: state }),
      })
      const body = await response.json().catch(() => ({})) as { token?: string; error?: string }
      if (!response.ok || !body.token) throw new Error(body.error ?? `handoff failed (${response.status})`)
      setCommand(handoffCommand(body.token))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    if (!command) return
    try {
      await navigator.clipboard.writeText(command)
    } catch {
      setError('Clipboard access was unavailable. Select and copy the instruction manually.')
    }
  }

  return (
    <>
      <button ref={triggerRef} className="hosted-handoff-button" onClick={show} title="Prepare a one-time local agent handoff">Continue locally</button>
      {open && (
        <div className="handoff-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false) }}>
          <section ref={modalRef} className="handoff-modal" role="dialog" aria-modal="true" aria-labelledby="hosted-handoff-title">
            <button ref={closeRef} className="handoff-modal-close" onClick={() => setOpen(false)} aria-label="Close">×</button>
            <h2 id="hosted-handoff-title">Continue locally</h2>
            <p className="muted small">Confirm the exact semantic state that will be transferred. Atlas and hosted pages never probe localhost.</p>
            {summary.length ? (
              <dl className="handoff-state-facts">
                {summary.map(([label, value]) => <span key={label}><dt>{label}</dt><dd>{value}</dd></span>)}
              </dl>
            ) : <p className="muted small">Matching this dataset to the public catalog…</p>}
            <label className="small" htmlFor="hosted-handoff-question">Question for your agent</label>
            <textarea id="hosted-handoff-question" rows={3} maxLength={4000} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Tell the agent what you want to compare, locate, or inspect" />
            <p className="muted small">Only the dataset reference, confirmed page state, and question are sent. No local paths, credentials, or raw matrix are included.</p>
            {error && <p className="error small">{error}</p>}
            {command && <div className="handoff-command"><label className="small" htmlFor="hosted-handoff-command">Paste into configured Claude Code or Codex</label><textarea id="hosted-handoff-command" rows={2} readOnly value={command} /><button onClick={copy}>Copy instruction</button><p className="muted small">Valid for 10 minutes and redeemable once. The token is not a URL.</p></div>}
            <div className="handoff-modal-actions"><button className="primary" onClick={() => void create()} disabled={busy || catalogPending || !atlasDataset}>{busy ? 'Generating…' : 'Generate local handoff'}</button><button onClick={() => setOpen(false)}>Done</button></div>
          </section>
        </div>
      )}
    </>
  )
}

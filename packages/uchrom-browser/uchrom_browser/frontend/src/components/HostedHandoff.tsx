import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchAtlas, fetchHealth } from '../api'
import { buildHandoffState, buildLocalHandoff, handoffSummary, type HandoffState } from '../handoff'
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

export function handoffIssueMessage(reason: 'invalid-dataset-url' | 'state-too-large' | 'prompt-too-large'): string {
  if (reason === 'invalid-dataset-url') return 'The dataset URL must be a public HTTPS URL.'
  if (reason === 'state-too-large') return 'The semantic snapshot exceeds 1 MiB UTF-8. Shrink the selection and reopen this dialog; nothing was truncated.'
  return 'The full prompt exceeds 1 MiB UTF-8. Shorten the question or shrink the selection; nothing was truncated.'
}

export function hostedHandoffPayload(view: Parameters<typeof buildHandoffState>[0], workspace: Parameters<typeof buildHandoffState>[1], includeCellIds = false): { state: HandoffState; includeCellIds: boolean } {
  return { state: buildHandoffState(view, workspace, { includeCellIds }), includeCellIds }
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
  const [includeCellIds, setIncludeCellIds] = useState(false)
  const [error, setError] = useState<string | null>(null)
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
  const localHandoff = useMemo(() => state && atlasDataset ? buildLocalHandoff(atlasDataset.url, question, state) : null, [state, atlasDataset, question])
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
    setState(hostedHandoffPayload(view, workspace).state)
    setIncludeCellIds(false)
    setQuestion('')
    setError(null)
    setOpen(true)
  }

  const copy = async (value: string, label: string) => {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      setError(`Clipboard access was unavailable. Select and copy the ${label} manually.`)
    }
  }

  return (
    <>
      <button ref={triggerRef} className="hosted-handoff-button" onClick={show} title="Prepare a local agent continuation">Continue locally</button>
      {open && (
        <div className="handoff-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false) }}>
          <section ref={modalRef} className="handoff-modal" role="dialog" aria-modal="true" aria-labelledby="hosted-handoff-title">
            <button ref={closeRef} className="handoff-modal-close" onClick={() => setOpen(false)} aria-label="Close">×</button>
            <h2 id="hosted-handoff-title">Continue locally</h2>
            <p className="muted small">Confirm the exact semantic state that will be included in your local prompt. This page never probes localhost or sends the snapshot to a server.</p>
            {summary.length ? (
              <dl className="handoff-state-facts">
                {summary.map(([label, value]) => <span key={label}><dt>{label}</dt><dd>{value}</dd></span>)}
              </dl>
            ) : <p className="muted small">{catalogPending ? 'Matching this dataset to the public catalog…' : 'No matching public catalog URL was found, so a local command cannot be generated.'}</p>}
            {atlasDataset && <p className="muted small">Public dataset URL: <code>{atlasDataset.url}</code></p>}
            <label className="small" htmlFor="hosted-handoff-question">Question for your agent</label>
            <textarea id="hosted-handoff-question" rows={3} maxLength={4000} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Tell the agent what you want to compare, locate, or inspect" />
            {state?.selection && <label className="handoff-privacy small" htmlFor="hosted-handoff-cell-ids">
              <input
                id="hosted-handoff-cell-ids"
                type="checkbox"
                checked={includeCellIds}
                onChange={(event) => {
                  const next = event.target.checked
                  setIncludeCellIds(next)
                  setState(hostedHandoffPayload(view, workspace, next).state)
                }}
              />
              <span><strong>Include canonical cell IDs</strong><br /><span className="muted">Unchecked by default; IDs are omitted from the prompt unless you explicitly opt in.</span></span>
            </label>}
            <p className="muted small">Run the local command first, wait for the page to open, then paste the prompt. It starts by reading the local canonical state before analysis or any proposed change. The prompt contains the public dataset URL, your question, and this exact semantic snapshot. No local paths, credentials, or raw matrix are included.</p>
            {error && <p className="error small">{error}</p>}
            {localHandoff && !localHandoff.ok && <p className="error small">{handoffIssueMessage(localHandoff.reason)}</p>}
            {localHandoff && 'command' in localHandoff && <div className="handoff-command">
              <label className="small" htmlFor="hosted-handoff-install">Install from a U-Chrom source checkout</label>
              <textarea id="hosted-handoff-install" rows={2} readOnly value={localHandoff.installCommand} />
              <button onClick={() => void copy(localHandoff.installCommand, 'install command')}>Copy install command</button>
              <label className="small" htmlFor="hosted-handoff-command">Run this on your computer</label>
              <textarea id="hosted-handoff-command" rows={2} readOnly value={localHandoff.command} />
              <button onClick={() => void copy(localHandoff.command, 'command')}>Copy command</button>
            </div>}
            {localHandoff?.ok && <div className="handoff-command">
              <label className="small" htmlFor="hosted-handoff-prompt">Paste this prompt into configured Claude Code or Codex</label>
              <textarea id="hosted-handoff-prompt" rows={8} readOnly value={localHandoff.prompt} />
              <button onClick={() => void copy(localHandoff.prompt, 'prompt')}>Copy prompt</button>
              <p className="muted small">Prompt size: {Math.ceil(localHandoff.promptBytes / 1024)} KiB UTF-8.</p>
            </div>}
            <div className="handoff-modal-actions"><button onClick={() => setOpen(false)}>Done</button></div>
          </section>
        </div>
      )}
    </>
  )
}

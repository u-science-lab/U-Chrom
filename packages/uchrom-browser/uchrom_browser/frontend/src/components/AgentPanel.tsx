import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  agentSetupStatus,
  agentHistory,
  applyAgentPlan,
  approveAgentPlan,
  attachAgentPage,
  formatAction,
  formatLocus,
  loadAgentSnapshot,
  pendingAgentPlans,
  planStatusLabel,
  rejectAgentPlan,
  sourceLabel,
  setupStageLabel,
  nextSetupAction,
  undoAgentPlan,
  type AgentPage,
  type AgentPlan,
  type AgentSnapshot,
  type AgentSetupStatus,
} from '../agent'

function statsScope(snapshot: AgentSnapshot): string {
  const stats = snapshot.views?.find((view) => view.type === 'stats')
  const scope = stats?.chrom_scope
  return typeof scope === 'string' ? scope : '—'
}

export function AgentPanel() {
  const [pages, setPages] = useState<AgentPage[]>([])
  const [pageId, setPageId] = useState('')
  const [snapshot, setSnapshot] = useState<AgentSnapshot | null>(null)
  const [plans, setPlans] = useState<AgentPlan[]>([])
  const [history, setHistory] = useState<AgentPlan[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [setup, setSetup] = useState<AgentSetupStatus>({ stage: 'not_running', pages: [] })

  const selectedPage = useMemo(() => pages.find((page) => page.page === pageId), [pages, pageId])

  const refreshPages = useCallback(async () => {
    const status = await agentSetupStatus()
    const next = status.pages
    setSetup(status)
    setPages(next)
    setPageId((current) => {
      if (current && next.some((page) => page.page === current)) return current
      return next.find((page) => page.pinned)?.page ?? next[0]?.page ?? ''
    })
    return next
  }, [])

  const refreshState = useCallback(async (target: string) => {
    const [nextSnapshot, nextPlans, nextHistory] = await Promise.all([loadAgentSnapshot(target), pendingAgentPlans(target), agentHistory(target)])
    setSnapshot(nextSnapshot)
    setPlans(nextPlans)
    setHistory(nextHistory)
  }, [])

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        setError(null)
        const status = await agentSetupStatus()
        const next = status.pages
        if (!active) return
        setSetup(status)
        setPages(next)
        setPageId((current) => current && next.some((page) => page.page === current) ? current : next.find((page) => page.pinned)?.page ?? next[0]?.page ?? '')
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause))
      }
    }
    void load()
    const timer = window.setInterval(() => void load(), 5000)
    window.addEventListener('focus', load)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('focus', load)
    }
  }, [])

  useEffect(() => {
    if (!selectedPage?.pinned || !pageId) {
      setSnapshot(null)
      setPlans([])
      return
    }
    let active = true
    const load = async () => {
      try {
        const [nextSnapshot, nextPlans, nextHistory] = await Promise.all([loadAgentSnapshot(pageId), pendingAgentPlans(pageId), agentHistory(pageId)])
        if (!active) return
        setSnapshot(nextSnapshot)
        setPlans(nextPlans)
        setHistory(nextHistory)
        setError(null)
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause))
      }
    }
    void load()
    const timer = window.setInterval(() => void load(), 5000)
    window.addEventListener('focus', load)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('focus', load)
    }
  }, [pageId, selectedPage?.pinned])

  const attach = async () => {
    if (!pageId) return
    setBusy('attach')
    try {
      await attachAgentPage(pageId)
      await refreshPages()
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(null)
    }
  }

  const reject = async (plan: AgentPlan) => {
    setBusy(plan.plan_id)
    try {
      await rejectAgentPlan(plan.plan_id)
      await refreshState(plan.page_id)
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(null)
    }
  }

  const apply = async (plan: AgentPlan) => {
    if (!snapshot || snapshot.page_id !== plan.page_id || snapshot.state_revision !== plan.expected_revision) {
      setError('Plan is stale; refresh the canonical page state before applying it.')
      return
    }
    setBusy(plan.plan_id)
    try {
      if (plan.status === 'pending') await approveAgentPlan(plan.plan_id)
      await applyAgentPlan(plan.plan_id)
      await refreshState(plan.page_id)
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
      try {
        await refreshState(plan.page_id)
      } catch {
        // Keep the original action error visible when the follow-up read also fails.
      }
    } finally {
      setBusy(null)
    }
  }

  const undo = async (plan: AgentPlan) => {
    if (!snapshot || !plan.state_revision) return
    setBusy(plan.plan_id)
    try {
      await undoAgentPlan(plan.plan_id, plan.page_id, snapshot.state_revision)
      await refreshState(plan.page_id)
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(null)
    }
  }

  return (
    <details className="agent-panel" open>
      <summary className="agent-head">
        <h2>Agent</h2>
        <span className="agent-state">{snapshot ? sourceLabel(snapshot.source) : setupStageLabel(setup.stage)}</span>
      </summary>
      {error && <p className="error">{error}</p>}
      <div className="agent-setup-status" aria-live="polite">
        <span className="agent-setup-stage">{setupStageLabel(setup.stage)}</span>
        <span className="agent-setup-next">{nextSetupAction(setup.stage)}</span>
      </div>
      {!pages.length && !error && <p className="muted small">No connected agent pages.</p>}
      {pages.length > 0 && (
        <>
          <div className="agent-page-picker">
            <label htmlFor="agent-page">page</label>
            <select id="agent-page" value={pageId} onChange={(event) => setPageId(event.target.value)}>
              {pages.map((page) => <option key={page.page} value={page.page}>{page.page}{page.pinned ? ' (pinned)' : ''}</option>)}
            </select>
            {!selectedPage?.pinned && <button onClick={() => void attach()} disabled={busy !== null}>Pin</button>}
          </div>
          {snapshot && selectedPage?.pinned && (
            <>
              <dl className="agent-facts">
                <dt>dataset</dt><dd title={snapshot.dataset?.id}>{String(snapshot.dataset?.name ?? snapshot.dataset?.id ?? '—')}</dd>
                <dt>selection</dt><dd>{snapshot.selection?.n_cells ?? 0}{snapshot.selection?.group ? ` · ${snapshot.selection.group}` : ''}</dd>
                <dt>locus</dt><dd>{formatLocus(snapshot.locus)}</dd>
                <dt>Stats scope</dt><dd>{statsScope(snapshot)}</dd>
                <dt>layout</dt><dd>{snapshot.layout ?? '—'} · {snapshot.views?.length ?? 0} views</dd>
                <dt>revision</dt><dd>{snapshot.state_revision}</dd>
              </dl>
              {plans.map((plan) => {
                const stale = plan.page_id !== snapshot.page_id || plan.expected_revision !== snapshot.state_revision
                return (
                  <div className="agent-plan" key={plan.plan_id}>
                    <div className="agent-plan-title">
                      <strong>{plan.plan_id}</strong>
                      <span className={`agent-status agent-status-${plan.status}`}>{planStatusLabel(plan.status)}</span>
                    </div>
                    <ol>{plan.actions.map((action, index) => <li key={`${plan.plan_id}-${index}`}>{formatAction(action)}</li>)}</ol>
                    <div className="agent-actions">
                      <button onClick={() => void apply(plan)} disabled={busy !== null || stale} title={stale ? 'The page changed after this plan was proposed' : 'Approve and apply this plan'}>Apply</button>
                      <button onClick={() => void reject(plan)} disabled={busy !== null}>Reject</button>
                    </div>
                  </div>
                )
              })}
              {history.length > 0 && (
                <div className="agent-history">
                  <h3>Recent agent changes</h3>
                  {history.map((entry) => (
                    <div className="agent-history-item" key={entry.plan_id}>
                      <div className="agent-plan-title">
                        <strong>{entry.plan_id}</strong>
                        <span className={`agent-status agent-status-${entry.status}`}>{planStatusLabel(entry.status)}</span>
                      </div>
                      {entry.results?.map((result, index) => (
                        <p className="muted small" key={`${entry.plan_id}-${index}`}>
                          {String(result.name)}: {result.ok ? JSON.stringify(result.result ?? 'ok') : String(result.error ?? 'failed')}
                        </p>
                      ))}
                      {entry.undo_reason && <p className="muted small">Undo unavailable: {entry.undo_reason}</p>}
                      {entry.can_undo && <button onClick={() => void undo(entry)} disabled={busy !== null || snapshot.state_revision !== entry.state_revision}>Undo last agent change</button>}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </details>
  )
}

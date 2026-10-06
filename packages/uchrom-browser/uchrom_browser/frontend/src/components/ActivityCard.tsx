import { useEffect, useState } from 'react'
import { useActivity } from '../activity'

/** A thin indeterminate bar at the top while requests are in flight (shown after a short delay: quick ones stay quiet). */
export function ActivityBar() {
  const pending = useActivity((s) => s.pending)
  const [show, setShow] = useState(false)
  useEffect(() => {
    if (!pending) {
      setShow(false)
      return
    }
    const t = setTimeout(() => setShow(true), 250)
    return () => clearTimeout(t)
  }, [pending])
  return show ? <div className="activity-bar" role="progressbar" aria-label="Loading" /> : null
}

/**
 * The longest-running named phase as a card with a spinner, the seconds waited and, after a while, why it takes long.
 * It never blocks the page (a click goes through); it only says that something is happening.
 */
export function ActivityCard() {
  const phase = useActivity((s) => s.phases[s.phases.length - 1])
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!phase) return
    const t = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(t)
  }, [phase])
  if (!phase) return null
  const secs = Math.max(0, Math.floor((now - phase.since) / 1000))
  return (
    <div className="activity-card" role="status" aria-live="polite">
      <span className="spinner" aria-hidden />
      <div>
        <div className="activity-text">
          {phase.text} <span className="muted">{secs >= 2 ? `${secs} s` : ''}</span>
        </div>
        {phase.hint && secs >= 6 && <div className="muted small activity-hint">{phase.hint}</div>}
      </div>
    </div>
  )
}

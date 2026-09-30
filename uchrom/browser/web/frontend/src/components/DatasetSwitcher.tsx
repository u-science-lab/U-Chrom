import { useCallback, useRef, useState } from 'react'
import { closeDataset } from '../api'
import { datasetBadges, datasetCounts } from '../datasets'
import { useStore } from '../store'
import { OpenDialog } from './OpenDialog'
import { Popover } from './Popover'

/**
 * The loaded datasets (top bar): the active one as a button (name, counts); its menu lists every loaded
 * dataset (name, counts, what it holds, path) to switch to, each with a close button, and "Open
 * dataset…" (the file dialog).  Replaces the drop-down + Open… + Close of the top bar.
 */
export function DatasetSwitcher() {
  const datasets = useStore((s) => s.datasets)
  const activeId = useStore((s) => s.activeDatasetId)
  const setActive = useStore((s) => s.setActiveDataset)
  const removeDataset = useStore((s) => s.removeDataset)
  const setError = useStore((s) => s.setError)
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState(false)
  const ref = useRef<HTMLButtonElement>(null)
  const close = useCallback(() => setOpen(false), [])
  const active = datasets.find((d) => d.id === activeId)

  const unload = async (id: string) => {
    try {
      await closeDataset(id)
      removeDataset(id)
    } catch (e) {
      setError(`Close failed: ${(e as Error).message}`)
    }
  }

  return (
    <>
      {active ? (
        <button ref={ref} className={`ds-switch${open ? ' open' : ''}`} onClick={() => setOpen(!open)} title={active.path} aria-haspopup="menu">
          <DbIcon />
          <span className="ds-name">{active.name}</span>
          <span className="ds-meta">{datasetCounts(active)}</span>
          <span className="caret" aria-hidden>
            ▾
          </span>
        </button>
      ) : (
        <button className="ds-switch empty" onClick={() => setDialog(true)} title="Open a dataset">
          <DbIcon />
          <span className="ds-name">Open a dataset…</span>
        </button>
      )}
      <Popover anchor={ref} open={open && !!active} onClose={close} className="menu-popup">
        <div className="ds-menu">
          <div className="ds-menu-title">Loaded datasets · {datasets.length}</div>
          <ul role="menu">
            {datasets.map((d) => (
              <li key={d.id} className={`ds-item${d.id === activeId ? ' current' : ''}`}>
                <button
                  className="ds-pick"
                  role="menuitemradio"
                  aria-checked={d.id === activeId}
                  onClick={() => {
                    setActive(d.id)
                    setOpen(false)
                  }}
                  title={d.path}
                >
                  <span className="ds-check" aria-hidden>
                    {d.id === activeId ? '✓' : ''}
                  </span>
                  <span className="ds-text">
                    <span className="ds-line">
                      <span className="ds-name">{d.name}</span>
                      <span className="ds-meta">{datasetCounts(d)}</span>
                    </span>
                    <span className="ds-badges">
                      {datasetBadges(d).map((b) => (
                        <span key={b} className={`ds-badge b-${b}`}>
                          {b}
                        </span>
                      ))}
                    </span>
                    <span className="ds-path">
                      <bdi>{d.path}</bdi>
                    </span>
                  </span>
                </button>
                <button className="ds-close" onClick={() => void unload(d.id)} title={`Close ${d.name} (unload it from the server)`} aria-label={`Close ${d.name}`}>
                  ×
                </button>
              </li>
            ))}
          </ul>
          <button
            className="ds-open"
            onClick={() => {
              setOpen(false)
              setDialog(true)
            }}
          >
            <span aria-hidden>＋</span> Open dataset…
          </button>
        </div>
      </Popover>
      {dialog && <OpenDialog onClose={() => setDialog(false)} />}
    </>
  )
}

function DbIcon() {
  return (
    <svg className="ds-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.3">
      <ellipse cx="8" cy="3.5" rx="5.5" ry="2" />
      <path d="M2.5 3.5v9c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-9" />
      <path d="M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" />
    </svg>
  )
}

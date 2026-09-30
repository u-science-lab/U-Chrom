import { useCallback, useRef, useState } from 'react'
import { closeDataset, openDataset } from '../api'
import { useStore } from '../store'
import { THEME_CHOICES } from '../theme'
import { Popover } from './Popover'
import { Select } from './Select'

export function TopBar() {
  const datasets = useStore((s) => s.datasets)
  const activeId = useStore((s) => s.activeDatasetId)
  const setActive = useStore((s) => s.setActiveDataset)
  const addDataset = useStore((s) => s.addDataset)
  const removeDataset = useStore((s) => s.removeDataset)
  const setError = useStore((s) => s.setError)
  const [opening, setOpening] = useState(false)
  const [path, setPath] = useState('')
  const [busy, setBusy] = useState(false)
  const active = datasets.find((d) => d.id === activeId)

  const submit = async () => {
    if (!path.trim()) return
    setBusy(true)
    try {
      addDataset(await openDataset(path.trim()))
      setOpening(false)
      setPath('')
      setError(null)
    } catch (e) {
      setError(`Open failed: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  const close = async () => {
    if (!active) return
    try {
      await closeDataset(active.id)
      removeDataset(active.id)
    } catch (e) {
      setError(`Close failed: ${(e as Error).message}`)
    }
  }

  return (
    <header className="topbar">
      <div className="brand" title="U-Chrom Browser">
        <img className="brand-logo" src={`${import.meta.env.BASE_URL}favicon.svg`} alt="U-Chrom Browser" height={30} />
      </div>
      <Select value={activeId ?? ''} onChange={(e) => setActive(e.target.value || null)} disabled={!datasets.length}>
        {!datasets.length && <option value="">No dataset loaded</option>}
        {datasets.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name}
          </option>
        ))}
      </Select>
      {opening ? (
        <form
          className="open-form"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <input
            autoFocus
            placeholder="/path/to/data.chromdata.zarr (.cdz, .h5cd, .csv) on the server"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && setOpening(false)}
          />
          <button type="submit" disabled={busy}>
            {busy ? 'Loading…' : 'Load'}
          </button>
          <button type="button" onClick={() => setOpening(false)}>
            Cancel
          </button>
        </form>
      ) : (
        <button onClick={() => setOpening(true)}>Open…</button>
      )}
      {active && (
        <button onClick={() => void close()} title="Unload this dataset from the server">
          Close
        </button>
      )}
      {active && (
        <div className="summary" title={active.path}>
          {active.n_spots.toLocaleString('en-US')} spots · {active.n_traces.toLocaleString('en-US')} traces ·{' '}
          {active.n_cells.toLocaleString('en-US')} cells · {active.chroms.length} chroms
          {active.xyz_unit ? ` · ${active.xyz_unit}` : ''}
        </div>
      )}
      <SidebarToggles />
      <ThemeMenu />
    </header>
  )
}

/** ◐ menu (right of the top bar): System / Dark / Light / Paper, remembered in the browser. */
function ThemeMenu() {
  const choice = useStore((s) => s.themeChoice)
  const name = useStore((s) => s.palette.name)
  const setChoice = useStore((s) => s.setThemeChoice)
  const [open, setOpen] = useState(false)
  const btn = useRef<HTMLButtonElement>(null)
  const closeMenu = useCallback(() => setOpen(false), [])
  return (
    <div className="theme-menu">
      <button ref={btn} onClick={() => setOpen(!open)} title={`Theme: ${THEME_CHOICES.find((c) => c.value === choice)?.label}${choice === 'system' ? ` (${name})` : ''}`} aria-label="Theme">
        ◐
      </button>
      <Popover anchor={btn} open={open} onClose={closeMenu} className="menu-popup">
        <ul>
          {THEME_CHOICES.map((c) => (
            <li
              key={c.value}
              className={c.value === choice ? 'on' : ''}
              title={c.hint}
              onClick={() => {
                setChoice(c.value)
                setOpen(false)
              }}
            >
              <span className="tick">{c.value === choice ? '✓' : ''}</span>
              {c.label}
              {c.value === 'system' && <span className="muted"> ({name === 'dark' ? 'dark' : 'light'} now)</span>}
            </li>
          ))}
        </ul>
      </Popover>
    </div>
  )
}

/** Show / hide the left side bar (cells, groups, colour) and the right one (inspector). */
function SidebarToggles() {
  const sidebars = useStore((s) => s.sidebars)
  const toggle = useStore((s) => s.toggleSidebar)
  const icon = (side: 'left' | 'right') => (
    <svg viewBox="0 0 16 14" width="16" height="14" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.3">
      <rect x="1" y="1" width="14" height="12" rx="2" />
      <rect x={side === 'left' ? 1 : 10.2} y="1" width="4.8" height="12" rx="1" fill="currentColor" fillOpacity={sidebars[side] ? 0.9 : 0.12} stroke="none" />
    </svg>
  )
  const cmd = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform) ? '⌘' : 'Ctrl+'
  return (
    <div className="sidebar-toggles" role="group" aria-label="Side bars">
      <button className={sidebars.left ? 'on' : ''} onClick={() => toggle('left')} aria-pressed={sidebars.left}
              title={`${sidebars.left ? 'Hide' : 'Show'} the left side bar (${cmd}[)`}>
        {icon('left')}
      </button>
      <button className={sidebars.right ? 'on' : ''} onClick={() => toggle('right')} aria-pressed={sidebars.right}
              title={`${sidebars.right ? 'Hide' : 'Show'} the inspector (${cmd}])`}>
        {icon('right')}
      </button>
    </div>
  )
}

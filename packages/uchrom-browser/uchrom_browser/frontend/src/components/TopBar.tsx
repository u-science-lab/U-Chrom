import { useCallback, useRef, useState } from 'react'
import { useStore } from '../store'
import { THEME_CHOICES } from '../theme'
import { Popover } from './Popover'
import { DatasetSwitcher } from './DatasetSwitcher'

export function TopBar() {
  return (
    <header className="topbar">
      <div className="brand" title="U-Chrom Browser">
        <img className="brand-logo" src={`${import.meta.env.BASE_URL}favicon.svg`} alt="U-Chrom Browser" height={30} />
      </div>
      <DatasetSwitcher />
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
  const hasData = useStore((s) => s.datasets.length > 0)     // the start page has no side bars
  const icon = (side: 'left' | 'right') => (
    <svg viewBox="0 0 16 14" width="16" height="14" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.3">
      <rect x="1" y="1" width="14" height="12" rx="2" />
      <rect x={side === 'left' ? 1 : 10.2} y="1" width="4.8" height="12" rx="1" fill="currentColor" fillOpacity={sidebars[side] ? 0.9 : 0.12} stroke="none" />
    </svg>
  )
  const cmd = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform) ? '⌘' : 'Ctrl+'
  return (
    <div className="sidebar-toggles" role="group" aria-label="Side bars">
      <button className={sidebars.left ? 'on' : ''} onClick={() => toggle('left')} aria-pressed={sidebars.left} disabled={!hasData}
              title={`${sidebars.left ? 'Hide' : 'Show'} the left side bar (${cmd}[)`}>
        {icon('left')}
      </button>
      <button className={sidebars.right ? 'on' : ''} onClick={() => toggle('right')} aria-pressed={sidebars.right} disabled={!hasData}
              title={`${sidebars.right ? 'Hide' : 'Show'} the inspector (${cmd}])`}>
        {icon('right')}
      </button>
    </div>
  )
}

import { useStore } from '../store'
import type { Side } from '../sidebars'

/** Collapse button inside a side bar ("«" left, "»" right); the top-bar toggles bring it back. */
export function SideClose({ side }: { side: Side }) {
  const toggle = useStore((s) => s.toggleSidebar)
  const cmd = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform) ? '⌘' : 'Ctrl+'
  const what = side === 'left' ? 'the side bar' : 'the inspector'
  return (
    <button className={`side-close ${side}`} onClick={() => toggle(side)} title={`Hide ${what} (${cmd}${side === 'left' ? '[' : ']'}); the top-bar button shows it again`} aria-label={`Hide ${what}`}>
      <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        {side === 'left' ? <path d="M6.5 2.5 3 6l3.5 3.5M10 2.5 6.5 6 10 9.5" /> : <path d="M5.5 2.5 9 6 5.5 9.5M2 2.5 5.5 6 2 9.5" />}
      </svg>
    </button>
  )
}

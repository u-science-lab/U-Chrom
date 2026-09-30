/** Which side bars are open (left: cells / groups / colour; right: the inspector), per viewer. */
export interface Sidebars {
  left: boolean
  right: boolean
}
export type Side = keyof Sidebars

export const SIDEBARS_KEY = 'uchrom.browser.sidebars'
export const DEFAULT_SIDEBARS: Sidebars = { left: true, right: true }

/** Stored value -> Sidebars; anything malformed -> both open.  Pure — tested. */
export function parseSidebars(raw: unknown): Sidebars {
  if (!raw || typeof raw !== 'object') return DEFAULT_SIDEBARS
  const r = raw as Partial<Sidebars>
  return { left: typeof r.left === 'boolean' ? r.left : true, right: typeof r.right === 'boolean' ? r.right : true }
}

export function loadSidebars(): Sidebars {
  try {
    const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(SIDEBARS_KEY) : null
    return raw ? parseSidebars(JSON.parse(raw)) : DEFAULT_SIDEBARS
  } catch {
    return DEFAULT_SIDEBARS
  }
}

export function saveSidebars(s: Sidebars): void {
  try {
    localStorage.setItem(SIDEBARS_KEY, JSON.stringify(s))
  } catch {
    /* blocked storage: the choice just doesn't persist */
  }
}

/** The side a key toggles: Ctrl / Cmd + [ the left bar, Ctrl / Cmd + ] the right one (not while typing). */
export function sidebarKey(e: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'altKey' | 'target'>): Side | null {
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return null
  const tag = (e.target as HTMLElement | null)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return null
  return e.key === '[' ? 'left' : e.key === ']' ? 'right' : null
}

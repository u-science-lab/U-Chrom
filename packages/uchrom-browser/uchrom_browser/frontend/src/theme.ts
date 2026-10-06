/**
 * Interface themes.  The choice ('system' by default) is kept in
 * localStorage; the resolved theme is set as `data-theme` on <html>, where
 * index.css defines every colour as a custom property — including the
 * `--c-*` ones that canvases and the 3-D view read through `palette()`.
 * Data colormaps (viridis, rainbow, category palettes) do not change.
 */

export type ThemeName = 'dark' | 'light' | 'paper'
export type ThemeChoice = 'system' | ThemeName

export const THEME_CHOICES: { value: ThemeChoice; label: string; hint: string }[] = [
  { value: 'system', label: 'System', hint: 'Follow the operating system (light / dark)' },
  { value: 'dark', label: 'Dark', hint: 'Dark panels and views' },
  { value: 'light', label: 'Light', hint: 'Light panels and views' },
  { value: 'paper', label: 'Paper', hint: 'Light, with white views — for figures and PNG export' },
]

const KEY = 'uchrom.browser.theme'

/** The theme a choice shows, given whether the system prefers dark. */
export function resolveTheme(choice: ThemeChoice, prefersDark: boolean): ThemeName {
  return choice === 'system' ? (prefersDark ? 'dark' : 'light') : choice
}

const isChoice = (v: unknown): v is ThemeChoice => THEME_CHOICES.some((c) => c.value === v)

type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem'>

function defaultStorage(): Storage | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null
  } catch {
    return null
  }
}

/** Saved choice; 'system' when nothing (valid) is stored or storage is unavailable. */
export function loadThemeChoice(storage: Storage | null = defaultStorage()): ThemeChoice {
  try {
    const v = storage?.getItem(KEY)
    return isChoice(v) ? v : 'system'
  } catch {
    return 'system'
  }
}

/** Remember the choice (silently does nothing when storage is blocked). */
export function saveThemeChoice(choice: ThemeChoice, storage: Storage | null = defaultStorage()): void {
  try {
    storage?.setItem(KEY, choice)
  } catch {
    /* private mode / blocked storage: the choice lasts for this page */
  }
}

/** Whether the system prefers a dark UI (true when it can't be asked). */
export function systemPrefersDark(): boolean {
  try {
    return typeof matchMedia === 'undefined' ? true : !matchMedia('(prefers-color-scheme: light)').matches
  } catch {
    return true
  }
}

/** Colours used when drawing on canvases / WebGL (from the `--c-*` CSS variables). */
export interface Palette {
  name: ThemeName
  viewportBg: string
  accent: string
  axis: string
  grid: string
  text: string
  muted: string
  /** "white" of the dark theme: rings, focus lines, highlight (near-black in light themes) */
  strong: string
  /** 3-D cells outside a focused group */
  context: string
  guide: string
  rowBg: string
  zero: string
  band: string
  bar: string
  lassoFill: string
  /** outline of scatter dots (pale colours on white); 'transparent' = none */
  dotRing: string
  intervalFill: string
  intervalStroke: string
  loop: string
  trackPos: string
  trackNeg: string
  trackPlain: string
  error: string
  /** matrix cells without a value (hex) */
  missing: string
  /** outline around matrix areas ('transparent' = none) */
  matrixFrame: string
}

/** Dark palette (also the fallback without a DOM, e.g. in tests). */
export const DARK: Palette = {
  name: 'dark',
  viewportBg: '#1b1d21',
  accent: '#5c9ded',
  axis: 'rgba(216,218,223,0.55)',
  grid: 'rgba(216,218,223,0.08)',
  text: '#b9bdc4',
  muted: '#8f949c',
  strong: '#ffffff',
  context: '#6b7078',
  guide: 'rgba(255,255,255,0.16)',
  rowBg: 'rgba(255,255,255,0.03)',
  zero: 'rgba(255,255,255,0.18)',
  band: 'rgba(92,157,237,0.18)',
  bar: 'rgba(92,157,237,0.75)',
  lassoFill: 'rgba(255,255,255,0.08)',
  dotRing: 'transparent',
  intervalFill: 'rgba(92,157,237,0.35)',
  intervalStroke: 'rgba(92,157,237,0.9)',
  loop: '#d08bf0',
  trackPos: '#e8784f',
  trackNeg: '#4f8fe8',
  trackPlain: '#6aa4ef',
  error: '#e07a7a',
  missing: '#616166',
  matrixFrame: 'transparent',
}

const VARS: Record<Exclude<keyof Palette, 'name'>, string> = {
  viewportBg: '--viewport-bg',
  accent: '--accent',
  axis: '--c-axis',
  grid: '--c-grid',
  text: '--c-text',
  muted: '--c-muted',
  strong: '--c-strong',
  context: '--c-context',
  guide: '--c-guide',
  rowBg: '--c-row-bg',
  zero: '--c-zero',
  band: '--c-band',
  bar: '--c-bar',
  lassoFill: '--c-lasso-fill',
  dotRing: '--c-dot-ring',
  intervalFill: '--c-interval-fill',
  intervalStroke: '--c-interval-stroke',
  loop: '--c-loop',
  trackPos: '--c-track-pos',
  trackNeg: '--c-track-neg',
  trackPlain: '--c-track-plain',
  error: '--c-error',
  missing: '--c-missing',
  matrixFrame: '--c-matrix-frame',
}

/** Read the palette from the CSS variables of `el` (missing ones keep the dark value). */
export function readPalette(name: ThemeName, get: (cssVar: string) => string): Palette {
  const out: Palette = { ...DARK, name }
  for (const [k, v] of Object.entries(VARS) as [Exclude<keyof Palette, 'name'>, string][]) {
    const val = get(v).trim()
    if (val) out[k] = val
  }
  return out
}

let current: Palette = DARK

/** The palette of the applied theme (canvas drawing reads this). */
export function palette(): Palette {
  return current
}

/** Apply a theme to the document and return its palette. */
export function applyTheme(name: ThemeName): Palette {
  if (typeof document === 'undefined') return (current = { ...DARK, name })
  document.documentElement.dataset.theme = name
  const cs = getComputedStyle(document.documentElement)
  current = readPalette(name, (v) => cs.getPropertyValue(v))
  return current
}

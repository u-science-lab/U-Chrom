import { describe, expect, it } from 'vitest'
import { DARK, loadThemeChoice, readPalette, resolveTheme, saveThemeChoice, THEME_CHOICES } from './theme'

/** In-memory storage; `broken` throws like blocked storage in private mode. */
function memoryStorage(broken = false) {
  const m = new Map<string, string>()
  return {
    getItem(k: string) {
      if (broken) throw new Error('SecurityError')
      return m.get(k) ?? null
    },
    setItem(k: string, v: string) {
      if (broken) throw new Error('QuotaExceeded')
      m.set(k, v)
    },
  }
}

describe('theme resolution', () => {
  it('System follows the OS preference; the others are fixed', () => {
    expect(resolveTheme('system', true)).toBe('dark')
    expect(resolveTheme('system', false)).toBe('light')
    for (const prefersDark of [true, false]) {
      expect(resolveTheme('dark', prefersDark)).toBe('dark')
      expect(resolveTheme('light', prefersDark)).toBe('light')
      expect(resolveTheme('paper', prefersDark)).toBe('paper')
    }
  })
  it('offers System first (the default), then Dark / Light / Paper', () => {
    expect(THEME_CHOICES.map((c) => c.value)).toEqual(['system', 'dark', 'light', 'paper'])
  })
})

describe('theme persistence', () => {
  it('round-trips a choice', () => {
    const st = memoryStorage()
    expect(loadThemeChoice(st)).toBe('system') // nothing saved yet
    saveThemeChoice('light', st)
    expect(loadThemeChoice(st)).toBe('light')
    saveThemeChoice('paper', st)
    expect(loadThemeChoice(st)).toBe('paper')
  })
  it('ignores junk and falls back to System when storage throws or is missing', () => {
    const st = memoryStorage()
    st.setItem('uchrom.browser.theme', 'neon')
    expect(loadThemeChoice(st)).toBe('system')
    const broken = memoryStorage(true)
    expect(loadThemeChoice(broken)).toBe('system')
    expect(() => saveThemeChoice('dark', broken)).not.toThrow()
    expect(loadThemeChoice(null)).toBe('system')
  })
})

describe('drawing palette', () => {
  it('reads the --c-* variables; missing ones keep the dark defaults', () => {
    const vars: Record<string, string> = { '--viewport-bg': ' #ffffff ', '--c-strong': '#111418', '--c-text': '' }
    const p = readPalette('paper', (v) => vars[v] ?? '')
    expect(p.name).toBe('paper')
    expect(p.viewportBg).toBe('#ffffff')
    expect(p.strong).toBe('#111418')
    expect(p.text).toBe(DARK.text) // empty → default
    expect(p.context).toBe(DARK.context)
  })
})

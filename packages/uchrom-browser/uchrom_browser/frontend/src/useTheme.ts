import { useStore } from './store'
import type { Palette } from './theme'

/**
 * The current theme's drawing palette.  Canvas effects list it in their
 * dependencies so they redraw when the theme changes (its identity changes
 * on every switch).
 */
export function useTheme(): Palette {
  return useStore((s) => s.palette)
}

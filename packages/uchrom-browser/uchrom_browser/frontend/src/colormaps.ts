/**
 * Colormaps and colour scales of matrix displays (Genome matrix rows and
 * the Matrix view).  LUTs are theme-independent data colours (matplotlib /
 * HiGlass stops, linearly interpolated); only the missing-value colour
 * comes from the theme.
 */

import type { RGB } from './colors'

export type ColormapName = 'fall' | 'viridis' | 'magma' | 'inferno' | 'plasma' | 'blues' | 'reds' | 'ylorrd' | 'greys' | 'rdbu_r'

const u8 = (rows: number[][]): RGB[] => rows.map(([r, g, b]) => [r / 255, g / 255, b / 255])

/** Stops (0 → 1) of each colormap. */
export const COLORMAPS: { name: ColormapName; label: string; stops: RGB[]; diverging?: boolean }[] = [
  {
    // HiGlass "fall": white → yellow → orange → red → black (the usual Hi-C map)
    name: 'fall',
    label: 'fall (HiGlass)',
    stops: u8([[255, 255, 255], [255, 255, 204], [255, 237, 160], [254, 217, 118], [254, 178, 76], [253, 141, 60], [252, 78, 42], [227, 26, 28], [189, 0, 38], [128, 0, 38], [0, 0, 0]]),
  },
  {
    name: 'viridis',
    label: 'viridis',
    stops: u8([[68, 1, 84], [71, 45, 123], [59, 82, 139], [44, 114, 142], [33, 145, 140], [39, 173, 129], [92, 200, 99], [170, 220, 50], [253, 231, 37]]),
  },
  {
    name: 'magma',
    label: 'magma',
    stops: u8([[0, 0, 4], [28, 16, 68], [79, 18, 123], [129, 37, 129], [181, 54, 122], [229, 80, 100], [251, 135, 97], [254, 194, 135], [252, 253, 191]]),
  },
  {
    name: 'inferno',
    label: 'inferno',
    stops: u8([[0, 0, 4], [31, 12, 72], [85, 15, 109], [136, 34, 106], [186, 54, 85], [227, 89, 51], [249, 140, 10], [249, 201, 50], [252, 255, 164]]),
  },
  {
    name: 'plasma',
    label: 'plasma',
    stops: u8([[13, 8, 135], [76, 2, 161], [126, 3, 168], [170, 35, 149], [204, 71, 120], [230, 108, 92], [248, 149, 64], [253, 197, 39], [240, 249, 33]]),
  },
  {
    name: 'blues',
    label: 'Blues',
    stops: u8([[247, 251, 255], [222, 235, 247], [198, 219, 239], [157, 202, 225], [106, 174, 214], [65, 145, 198], [32, 112, 180], [8, 80, 155], [8, 48, 107]]),
  },
  {
    name: 'reds',
    label: 'Reds',
    stops: u8([[255, 245, 240], [254, 224, 210], [252, 187, 161], [252, 146, 114], [251, 106, 74], [239, 59, 44], [203, 24, 29], [165, 15, 21], [103, 0, 13]]),
  },
  {
    name: 'ylorrd',
    label: 'YlOrRd',
    stops: u8([[255, 255, 204], [255, 237, 160], [254, 217, 118], [254, 178, 76], [253, 141, 60], [252, 78, 42], [227, 26, 28], [189, 0, 38], [128, 0, 38]]),
  },
  {
    name: 'greys',
    label: 'greys',
    stops: u8([[255, 255, 255], [240, 240, 240], [217, 217, 217], [189, 189, 189], [150, 150, 150], [115, 115, 115], [82, 82, 82], [37, 37, 37], [0, 0, 0]]),
  },
  {
    // diverging, for signed data (O/E-like): blue → white → red
    name: 'rdbu_r',
    label: 'RdBu_r (diverging)',
    diverging: true,
    stops: u8([[5, 48, 97], [33, 102, 172], [67, 147, 195], [146, 197, 222], [247, 247, 247], [244, 165, 130], [214, 96, 77], [178, 24, 43], [103, 0, 31]]),
  },
]

const BY_NAME = new Map(COLORMAPS.map((c) => [c.name, c]))
export const isColormap = (v: unknown): v is ColormapName => typeof v === 'string' && BY_NAME.has(v as ColormapName)

/** Colour at t ∈ [0, 1] (clamped; NaN → 0), optionally reversed. */
export function cmap(name: ColormapName, t: number, reverse = false): RGB {
  const stops = (BY_NAME.get(name) ?? BY_NAME.get('viridis')!).stops
  let x = Math.min(1, Math.max(0, Number.isFinite(t) ? t : 0))
  if (reverse) x = 1 - x
  const c = x * (stops.length - 1)
  const i = Math.min(stops.length - 2, Math.floor(c))
  const f = c - i
  const a = stops[i]
  const b = stops[i + 1]
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]
}

/** CSS linear-gradient of a colormap (previews in the inspector). */
export function cmapGradient(name: ColormapName, reverse = false, n = 9): string {
  const css = (c: RGB) => `rgb(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)})`
  return `linear-gradient(to right, ${Array.from({ length: n }, (_, i) => css(cmap(name, i / (n - 1), reverse))).join(', ')})`
}

/** What a matrix holds (decides the defaults). */
export type MatrixKind = 'contacts' | 'distance' | 'frequency' | 'ratio'

/** A colour scale; `min` / `max` null = auto (percentile clip). */
export interface ColorScale {
  cmap: ColormapName
  reverse: boolean
  log: boolean
  min: number | null
  max: number | null
}

/** Stored per row / pane: only what the user changed (absent → defaults). */
export type ColorScaleSetting = Partial<ColorScale>

/**
 * Defaults (and the look before these settings existed): contacts fall on
 * a log scale; distances viridis reversed so near = bright; contact
 * frequency viridis, linear.
 */
export function defaultColorScale(kind: MatrixKind): ColorScale {
  if (kind === 'contacts') return { cmap: 'fall', reverse: false, log: true, min: null, max: null }
  if (kind === 'distance') return { cmap: 'viridis', reverse: true, log: false, min: null, max: null }
  if (kind === 'ratio') return { cmap: 'rdbu_r', reverse: false, log: false, min: null, max: null }
  return { cmap: 'viridis', reverse: false, log: false, min: null, max: null }
}

/** A stored setting over the defaults of `kind` (malformed fields ignored). */
export function resolveColorScale(kind: MatrixKind, s: ColorScaleSetting | undefined | null): ColorScale {
  const d = defaultColorScale(kind)
  if (!s) return d
  const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null)
  return {
    cmap: isColormap(s.cmap) ? s.cmap : d.cmap,
    reverse: typeof s.reverse === 'boolean' ? s.reverse : d.reverse,
    log: typeof s.log === 'boolean' ? s.log : d.log,
    min: num(s.min),
    max: num(s.max),
  }
}

/** Keep a well-formed stored setting (undefined when empty / malformed). */
export function parseColorScale(raw: unknown): ColorScaleSetting | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const r = raw as Record<string, unknown>
  const out: ColorScaleSetting = {}
  if (isColormap(r.cmap)) out.cmap = r.cmap
  if (typeof r.reverse === 'boolean') out.reverse = r.reverse
  if (typeof r.log === 'boolean') out.log = r.log
  if (typeof r.min === 'number' && Number.isFinite(r.min)) out.min = r.min
  if (typeof r.max === 'number' && Number.isFinite(r.max)) out.max = r.max
  return Object.keys(out).length ? out : undefined
}

/** Quantile of the finite values passing `keep` (q ∈ [0, 1]); NaN when none. */
function quantileOf(data: ArrayLike<number>, q: number, keep: (v: number) => boolean = () => true): number {
  const v: number[] = []
  for (let i = 0; i < data.length; i++) if (Number.isFinite(data[i]) && keep(data[i])) v.push(data[i])
  if (!v.length) return NaN
  v.sort((a, b) => a - b)
  return v[Math.min(v.length - 1, Math.max(0, Math.round(q * (v.length - 1))))]
}

/**
 * Automatic range in data units: contacts [0, p99 of the positive counts];
 * distances [p1, p99]; frequencies [0, max]; log2 ratios [p2, p98].  A diverging map over data of
 * both signs gets a range symmetric around 0.
 */
export function autoRange(data: ArrayLike<number>, kind: MatrixKind, diverging = false): [number, number] {
  let lo: number
  let hi: number
  if (kind === 'contacts') {
    lo = 0
    hi = quantileOf(data, 0.99, (v) => v > 0)
  } else if (kind === 'frequency') {
    lo = 0
    hi = quantileOf(data, 1)
  } else if (kind === 'ratio') {
    lo = quantileOf(data, 0.02)
    hi = quantileOf(data, 0.98)
  } else {
    lo = quantileOf(data, 0.01)
    hi = quantileOf(data, 0.99)
  }
  if (!Number.isFinite(lo)) lo = 0
  if (!Number.isFinite(hi) || hi <= lo) hi = lo + 1
  if (diverging && lo < 0 && hi > 0) {
    const m = Math.max(-lo, hi)
    return [-m, m]
  }
  return [lo, hi]
}

/** The range used: manual min / max where set, else automatic. */
export function effectiveRange(auto: [number, number], s: Pick<ColorScale, 'min' | 'max'>): [number, number] {
  const lo = s.min ?? auto[0]
  let hi = s.max ?? auto[1]
  if (!(hi > lo)) hi = lo + (Math.abs(lo) || 1) * 1e-6 + 1e-12
  return [lo, hi]
}

/** Position of a value in the range: linear, or log (log1p of the offset from the range start). */
export function scalePos(v: number, range: [number, number], log: boolean): number {
  const [lo, hi] = range
  if (!Number.isFinite(v)) return NaN
  const t = log ? Math.log1p(Math.max(0, v - lo)) / Math.log1p(hi - lo) : (v - lo) / (hi - lo)
  return Math.min(1, Math.max(0, t))
}

/** Value at position t (inverse of scalePos) — colour-bar ticks. */
export function scaleValue(t: number, range: [number, number], log: boolean): number {
  const [lo, hi] = range
  return log ? lo + Math.expm1(t * Math.log1p(hi - lo)) : lo + t * (hi - lo)
}

/** Colour of one value (non-finite → `missing`). */
export function scaleColor(v: number, s: ColorScale, range: [number, number], missing: RGB): RGB {
  if (!Number.isFinite(v)) return missing
  return cmap(s.cmap, scalePos(v, range, s.log), s.reverse)
}

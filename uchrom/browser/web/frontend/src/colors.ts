import type { ColorMode, Geometry } from './types'

export type RGB = [number, number, number]

/** matplotlib tab20 */
export const TAB20 = [
  '#1f77b4', '#aec7e8', '#ff7f0e', '#ffbb78', '#2ca02c', '#98df8a', '#d62728', '#ff9896',
  '#9467bd', '#c5b0d5', '#8c564b', '#c49c94', '#e377c2', '#f7b6d2', '#7f7f7f', '#c7c7c7',
  '#bcbd22', '#dbdb8d', '#17becf', '#9edae5',
]

/** Distinct, bright-on-dark palette for chromosomes (stable per name). */
const CHROM_PALETTE = [
  '#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231', '#911eb4', '#46f0f0', '#f032e6',
  '#bcf60c', '#fabebe', '#008080', '#e6beff', '#9a6324', '#fffac8', '#800000', '#aaffc3',
  '#808000', '#ffd8b1', '#6b8cff', '#ff6f91', '#00c2a8', '#c9a0ff', '#ffa600', '#7fdbff',
]

export function hexToRgb(hex: string): RGB {
  let h = hex.trim().replace(/^#/, '')
  if (h.length === 3) h = h.split('').map((c) => c + c).join('')
  if (!/^[0-9a-fA-F]{6}$/.test(h)) throw new Error(`bad colour "${hex}"`)
  const n = parseInt(h, 16)
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
}

/** Natural rank of common chromosome names; unknown names fall back to a hash. */
function chromRank(name: string): number {
  const base = name.replace(/^chr/i, '')
  if (/^\d+$/.test(base)) return parseInt(base, 10) - 1
  // chr1–22 take palette slots 0–21, so X/Y get the two remaining slots.
  const special: Record<string, number> = { x: 22, y: 23, m: 24, mt: 24 }
  const k = base.toLowerCase()
  if (k in special) return special[k]
  let h = 2166136261
  for (let i = 0; i < name.length; i++) {
    h ^= name.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0) + 1000
}

export function chromColor(name: string): string {
  return CHROM_PALETTE[chromRank(name) % CHROM_PALETTE.length]
}

/** HSV → RGB, all in [0, 1]. */
function hsv(h: number, s: number, v: number): RGB {
  const i = Math.floor(h * 6)
  const f = h * 6 - i
  const p = v * (1 - s)
  const q = v * (1 - f * s)
  const t = v * (1 - (1 - f) * s)
  switch (((i % 6) + 6) % 6) {
    case 0: return [v, t, p]
    case 1: return [q, v, p]
    case 2: return [p, v, t]
    case 3: return [p, q, v]
    case 4: return [t, p, v]
    default: return [v, p, q]
  }
}

/** Rainbow along the polymer: t=0 violet/blue → t=1 red (like matplotlib "rainbow"). */
export function rainbow(t: number): RGB {
  const c = Math.min(1, Math.max(0, t))
  return hsv((1 - c) * 0.75, 0.85, 1)
}

/**
 * Per-vertex RGB colours (length 3·N) for a geometry.
 *
 * - rainbow: several chromosomes (or `chromColors`) → one colour per chromosome; a single
 *   chromosome → hue along genomic position, scaled by the dataset-wide
 *   `chrom_extent` so a sub-region keeps its parent's colours.
 * - trace: tab20 by order of first appearance of each trace_id.
 * - custom: one colour.
 */
export function vertexColors(geom: Geometry, mode: ColorMode, custom: string, chromColors = false): Float32Array {
  const { header, starts, offsets } = geom
  const n = header.n_points
  const out = new Float32Array(3 * n)
  const fill = (from: number, to: number, rgb: RGB) => {
    for (let i = from; i < to; i++) {
      out[3 * i] = rgb[0]
      out[3 * i + 1] = rgb[1]
      out[3 * i + 2] = rgb[2]
    }
  }
  if (mode === 'custom') {
    fill(0, n, hexToRgb(custom))
    return out
  }
  if (mode === 'trace') {
    const order = new Map<string, number>()
    header.segments.forEach((seg, s) => {
      if (!order.has(seg.trace_id)) order.set(seg.trace_id, order.size)
      fill(offsets[s], offsets[s + 1], hexToRgb(TAB20[order.get(seg.trace_id)! % TAB20.length]))
    })
    return out
  }
  const chroms = new Set(header.segments.map((s) => s.chrom))
  // `chromColors`: the layer spans several chromosomes even if the display
  // filter left one, so keep the legend's per-chromosome colours.
  if (chroms.size > 1 || chromColors) {
    header.segments.forEach((seg, s) => fill(offsets[s], offsets[s + 1], hexToRgb(chromColor(seg.chrom))))
    return out
  }
  header.segments.forEach((seg, s) => {
    const ext = header.chrom_extent[seg.chrom] ?? [seg.start, seg.end]
    const span = Math.max(1, ext[1] - ext[0])
    for (let i = offsets[s]; i < offsets[s + 1]; i++) {
      const rgb = rainbow((starts[i] - ext[0]) / span)
      out[3 * i] = rgb[0]
      out[3 * i + 1] = rgb[1]
      out[3 * i + 2] = rgb[2]
    }
  })
  return out
}

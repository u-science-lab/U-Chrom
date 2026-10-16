/**
 * Small helpers for writing SVG by hand (vector export of the panes): number
 * formatting, escaping, and CSS colours split into an opaque colour and an
 * opacity (SVG 1.1 readers — Illustrator, svg2pdf — do not take rgba()).
 */

/** Coordinates with at most 2 decimals, no trailing zeros. */
export function num(v: number): string {
  if (!Number.isFinite(v)) return '0'
  const r = Math.round(v * 100) / 100
  return Object.is(r, -0) ? '0' : String(r)
}

const ESC: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
export function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ESC[c])
}

export interface Paint {
  /** opaque colour, or 'none' */
  color: string
  opacity: number
}

const hex2 = (v: number) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')

/** A CSS colour → opaque colour + opacity (unknown forms pass through at opacity 1). */
export function paint(css: string, alpha = 1): Paint {
  const s = css.trim().toLowerCase()
  if (!s || s === 'transparent' || s === 'none') return { color: 'none', opacity: 0 }
  let m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)\s*(?:[,/]\s*([\d.]+%?)\s*)?\)$/.exec(s)
  if (m) {
    const a = m[4] === undefined ? 1 : m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4])
    return { color: `#${hex2(+m[1])}${hex2(+m[2])}${hex2(+m[3])}`, opacity: a * alpha }
  }
  m = /^#([0-9a-f]{3,8})$/.exec(s)
  if (m) {
    const h = m[1]
    if (h.length === 3 || h.length === 4) {
      const a = h.length === 4 ? parseInt(h[3] + h[3], 16) / 255 : 1
      return { color: `#${h[0]}${h[0]}${h[1]}${h[1]}${h[2]}${h[2]}`, opacity: a * alpha }
    }
    if (h.length === 6) return { color: `#${h}`, opacity: alpha }
    if (h.length === 8) return { color: `#${h.slice(0, 6)}`, opacity: (parseInt(h.slice(6), 16) / 255) * alpha }
  }
  return { color: css.trim(), opacity: alpha }
}

/** Linear-light 0-1 channel → sRGB 0-1 (three.js vertex colours are linear). */
export function linearToSrgb(c: number): number {
  return c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055
}

/** sRGB 0-1 triple → '#rrggbb'. */
export function hexColor(r: number, g: number, b: number): string {
  return `#${hex2(r * 255)}${hex2(g * 255)}${hex2(b * 255)}`
}

/** One SVG element: geometry attributes plus presentation attributes (groupable). */
export interface SvgEl {
  tag: string
  /** geometry attributes, already serialised (`cx="1" cy="2"`) */
  geom: string
  /** presentation attributes shared by runs of elements (fill, stroke, opacity, …) */
  style: Record<string, string>
  /** text content (escaped on output) */
  text?: string
  /** pre-serialised markup (images), emitted as is */
  raw?: string
}

function attrs(style: Record<string, string>): string {
  return Object.entries(style)
    .map(([k, v]) => ` ${k}="${esc(v)}"`)
    .join('')
}

/**
 * Serialise elements; runs of at least three consecutive elements with the
 * same presentation attributes share one `<g>` (one colour of a scatter
 * plot is one group — compact and easy to restyle in a vector editor).
 */
export function serialize(els: SvgEl[]): string {
  const out: string[] = []
  const key = (e: SvgEl) => (e.raw !== undefined ? '\u0000raw' : `${e.tag}|${JSON.stringify(e.style)}`)
  for (let i = 0; i < els.length; ) {
    let j = i + 1
    const k = key(els[i])
    while (j < els.length && key(els[j]) === k) j++
    const run = els.slice(i, j)
    if (run[0].raw !== undefined) out.push(...run.map((e) => e.raw!))
    else if (run.length >= 3) {
      out.push(`<g${attrs(run[0].style)}>`)
      for (const e of run) out.push(one(e, {}))
      out.push('</g>')
    } else for (const e of run) out.push(one(e, e.style))
    i = j
  }
  return out.join('\n')
}

function one(e: SvgEl, style: Record<string, string>): string {
  if (e.raw !== undefined) return e.raw
  const a = `<${e.tag} ${e.geom}${attrs(style)}`
  return e.text !== undefined ? `${a}>${esc(e.text)}</${e.tag}>` : `${a}/>`
}

/** A standalone SVG document of `w` × `h` CSS pixels. */
export function svgDocument(w: number, h: number, body: string, opts: { title?: string; desc?: string; defs?: string } = {}): string {
  return [
    `<?xml version="1.0" encoding="UTF-8"?>`,
    `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="${num(w)}" height="${num(h)}" viewBox="0 0 ${num(w)} ${num(h)}">`,
    opts.title ? `<title>${esc(opts.title)}</title>` : '',
    opts.desc ? `<desc>${esc(opts.desc)}</desc>` : '',
    opts.defs ? `<defs>${opts.defs}</defs>` : '',
    body,
    `</svg>`,
  ]
    .filter(Boolean)
    .join('\n')
}

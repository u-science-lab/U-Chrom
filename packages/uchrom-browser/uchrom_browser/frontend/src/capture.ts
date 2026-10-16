/**
 * "Save image (PNG)" of one pane: its content only (no header).  Every
 * canvas in the pane body (WebGL — the renderer keeps its drawing buffer —
 * and 2-D) is composited at its on-screen place and resolution, SVGs are
 * rasterised, and the HTML overlays that carry information (axis labels,
 * badges, legends, swatches) are drawn on top as text / boxes.  Hover tips
 * and controls are left out.
 */

import { fmtBp } from './filters'
import { datasetChroms, GENOME } from './genome'
import { describeGroup, resolveScope, type Scope } from './groups'
import { activeSavedGroups, activeView, fieldKey, useStore } from './store'
import { palette } from './theme'
import { resolveLocus } from './useLocus'
import { PANE_LABEL, type Pane } from './workspace'
import type { Vector3dResult } from './render/vector3d'
import { esc, num, paint, serialize, svgDocument } from './svg'
import { recordCanvases } from './vectorcapture'

/** File formats of "Save image": a PNG of the screen, or editable vector graphics. */
export type CaptureFormat = 'png' | 'svg' | 'pdf'
export const CAPTURE_MIME: Record<CaptureFormat, string> = { png: 'image/png', svg: 'image/svg+xml', pdf: 'application/pdf' }

/** Characters kept in a filename part; anything else becomes '-'. */
export function safePart(s: string): string {
  return (
    s
      .trim()
      .replace(/[^A-Za-z0-9._+-]+/g, '-')
      .replace(/-{2,}/g, '-')
      .replace(/^[-.]+|-+$/g, '') || 'x'
  )
}

const pad = (n: number) => String(n).padStart(2, '0')

/** 2026-09-24 15:30:12 → "20260924-153012" (local time). */
export function timestamp(d: Date): string {
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

/**
 * `uchrom_<dataset>_<viewtype>_<scope or locus>_<timestamp>.<png|svg|pdf>`.
 * Genome-coordinate views name the locus (and a cell / group scope after
 * it); the others name their scope ("all" for every cell).
 */
export function captureFilename(o: {
  dataset: string
  type: Pane['type']
  scope?: string | null
  locus?: { chrom: string; start: number; end: number } | null
  date: Date
  ext?: CaptureFormat
}): string {
  const parts = ['uchrom', o.dataset, PANE_LABEL[o.type].toLowerCase()]
  const locus = o.locus ? `${o.locus.chrom === GENOME ? 'genome' : o.locus.chrom}-${fmtBp(o.locus.start)}-${fmtBp(o.locus.end)}` : null
  if (locus) parts.push(locus)
  if (o.scope || !locus) parts.push(o.scope || 'all')
  parts.push(timestamp(o.date))
  return `${parts.map(safePart).join('_')}.${o.ext ?? 'png'}`
}

/** Filename part for a pane's scope: cell id, group name, or null for every cell. */
function scopeName(scope: Scope): string | null {
  if (scope.kind === 'all') return null
  if (scope.kind === 'cell') return `cell-${scope.cell}`
  const s = useStore.getState()
  const ds = s.datasets.find((d) => d.id === s.activeDatasetId)
  const info = describeGroup(scope.group, {
    fields: ds?.cell_fields ?? [],
    saved: activeSavedGroups(s),
    selection: activeView(s).selection,
    values: (f) => (ds ? s.cellValues[fieldKey(ds.id, f)] : undefined),
  })
  return info?.name ?? scope.group
}

/** The filename a pane would be saved under now. */
export function paneFilename(pane: Pane, date = new Date(), ext: CaptureFormat = 'png'): string {
  const s = useStore.getState()
  const ds = s.datasets.find((d) => d.id === s.activeDatasetId)
  const v = activeView(s)
  const genomic = pane.type === 'genome' || pane.type === 'matrix'
  return captureFilename({
    dataset: ds?.name ?? 'data',
    type: pane.type,
    scope: scopeName(resolveScope(pane.scope, v)),
    locus: genomic ? resolveLocus(v.locus, datasetChroms(ds)) : null,
    date,
    ext,
  })
}

/** First non-transparent background colour from `el` up. */
function backgroundOf(el: HTMLElement | null): string {
  for (let e = el; e; e = e.parentElement) {
    const bg = getComputedStyle(e).backgroundColor
    if (bg && bg !== 'transparent' && !/rgba\(.*,\s*0\)$/.test(bg)) return bg
  }
  return palette().viewportBg
}

const SKIP = '.embedding-tip, .gv-cross, .gv-row-loading, .gv-resize, [data-capture="skip"], button, input, select, textarea, label'

function visible(el: Element): boolean {
  const cs = getComputedStyle(el)
  if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return false
  const r = el.getBoundingClientRect()
  return r.width > 0 && r.height > 0
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('cannot rasterise an SVG'))
    img.src = url
  })
}

/**
 * Per-pane "render now" callbacks (3-D views): a capture draws a fresh
 * frame first — the render loop pauses in background tabs, and the
 * drawing buffer must hold the current view.
 */
const renderHooks = new Map<string, () => void>()
export function registerRenderHook(paneId: string, render: (() => void) | null) {
  if (render) renderHooks.set(paneId, render)
  else renderHooks.delete(paneId)
}

/** Composite a pane body into one canvas at device resolution. */
export async function composePane(body: HTMLElement): Promise<HTMLCanvasElement> {
  const pane = body.dataset.pane
  if (pane) renderHooks.get(pane)?.()
  const box = body.getBoundingClientRect()
  const scale = window.devicePixelRatio || 1
  const out = document.createElement('canvas')
  out.width = Math.max(1, Math.round(box.width * scale))
  out.height = Math.max(1, Math.round(box.height * scale))
  const g = out.getContext('2d')
  if (!g) throw new Error('no 2-D canvas context')
  g.scale(scale, scale)
  g.fillStyle = backgroundOf(body.querySelector<HTMLElement>('canvas')?.parentElement ?? body)
  g.fillRect(0, 0, box.width, box.height)
  const at = (r: DOMRect) => ({ x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height })

  // one pass in DOM order, so later overlays land on top: canvases (WebGL
  // needs preserveDrawingBuffer, set by the 3-D view) and SVGs as images;
  // other elements as their background box (not containers of a canvas,
  // whose background would hide it) and their own text
  const opaque = (c: string) => !!c && c !== 'transparent' && !/rgba\(.*,\s*0\)$/.test(c)
  for (const el of body.querySelectorAll<HTMLElement | SVGSVGElement>('*')) {
    if (el.closest(SKIP) || (el instanceof SVGElement && !(el instanceof SVGSVGElement)) || !visible(el)) continue
    const r = at(el.getBoundingClientRect())
    if (el instanceof HTMLCanvasElement) {
      g.drawImage(el, r.x, r.y, r.w, r.h)
      continue
    }
    if (el instanceof SVGSVGElement) {
      const xml = new XMLSerializer().serializeToString(el)
      const url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml' }))
      try {
        g.drawImage(await loadImage(url), r.x, r.y, r.w, r.h)
      } finally {
        URL.revokeObjectURL(url)
      }
      continue
    }
    if (el.closest('svg')) continue
    const cs = getComputedStyle(el)
    if (opaque(cs.backgroundColor) && !el.querySelector('canvas, svg')) {
      g.fillStyle = cs.backgroundColor
      const rad = Math.min(parseFloat(cs.borderTopLeftRadius) || 0, r.w / 2, r.h / 2)
      g.beginPath()
      g.roundRect(r.x, r.y, r.w, r.h, rad)
      g.fill()
    }
    for (const node of el.childNodes) {
      if (node.nodeType !== Node.TEXT_NODE || !node.textContent?.trim()) continue
      const range = document.createRange()
      range.selectNodeContents(node)
      const tr = at(range.getBoundingClientRect())
      if (!tr.w) continue
      g.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`
      g.fillStyle = cs.color
      g.textBaseline = 'middle'
      g.textAlign = 'left'
      g.fillText(node.textContent.replace(/\s+/g, ' ').trim(), tr.x, tr.y + tr.h / 2)
    }
  }
  return out
}

/**
 * Per-pane vector exporters of WebGL views (3-D): the canvas they draw and
 * a function projecting the current scene to SVG elements.
 */
export interface VectorHook {
  canvas: HTMLCanvasElement
  build(width: number, height: number): Vector3dResult
}
const vectorHooks = new Map<string, VectorHook>()
export function registerVectorHook(paneId: string, hook: VectorHook | null) {
  if (hook) vectorHooks.set(paneId, hook)
  else vectorHooks.delete(paneId)
}

/** Split a CSS function's arguments at top-level commas. */
function splitArgs(s: string): string[] {
  const out: string[] = []
  let depth = 0
  let cur = ''
  for (const ch of s) {
    if (ch === '(') depth++
    if (ch === ')') depth--
    if (ch === ',' && depth === 0) {
      out.push(cur.trim())
      cur = ''
    } else cur += ch
  }
  if (cur.trim()) out.push(cur.trim())
  return out
}

/** A CSS `linear-gradient(…)` → an SVG <linearGradient> (objectBoundingBox), or null. */
export function cssGradient(bg: string, id: string): string | null {
  const m = /^linear-gradient\((.*)\)$/.exec(bg.trim())
  if (!m) return null
  const args = splitArgs(m[1])
  const DIR: Record<string, number> = { 'to top': 0, 'to right': 90, 'to bottom': 180, 'to left': 270 }
  let angle = 180
  if (args.length && (DIR[args[0]] !== undefined || /^-?[\d.]+deg$/.test(args[0]))) {
    const a = args.shift()!
    angle = DIR[a] ?? parseFloat(a)
  }
  const stops = args.map((a) => {
    const sm = /^(.*?)(?:\s+(-?[\d.]+)%)?$/.exec(a)!
    return { color: sm[1].trim(), at: sm[2] === undefined ? null : parseFloat(sm[2]) / 100 }
  })
  if (stops.length < 2) return null
  stops.forEach((st, i) => {
    if (st.at === null) st.at = i / (stops.length - 1)
  })
  const rad = (angle * Math.PI) / 180
  const dx = Math.sin(rad) / 2
  const dy = -Math.cos(rad) / 2
  const stopEls = stops
    .map((st) => {
      const p = paint(st.color)
      return `<stop offset="${num(st.at!)}" stop-color="${esc(p.color)}"${p.opacity < 1 ? ` stop-opacity="${num(p.opacity)}"` : ''}/>`
    })
    .join('')
  return `<linearGradient id="${id}" x1="${num(0.5 - dx)}" y1="${num(0.5 - dy)}" x2="${num(0.5 + dx)}" y2="${num(0.5 + dy)}">${stopEls}</linearGradient>`
}

/** Fill / opacity attributes of a CSS colour. */
function fillAttrs(css: string, attr = 'fill'): string {
  const p = paint(css)
  return ` ${attr}="${esc(p.color)}"${p.opacity < 1 && p.color !== 'none' ? ` ${attr}-opacity="${num(p.opacity)}"` : ''}`
}

/** An inline <svg> of the page (axis key, icons) with its CSS styles written out as attributes. */
function inlineSvg(el: SVGSVGElement, r: { x: number; y: number; w: number; h: number }): string {
  const clone = el.cloneNode(true) as SVGSVGElement
  const src = [el, ...el.querySelectorAll('*')]
  const dst = [clone, ...clone.querySelectorAll('*')]
  src.forEach((s, i) => {
    const d = dst[i]
    const cs = getComputedStyle(s)
    if (s instanceof SVGGraphicsElement && !(s instanceof SVGSVGElement) && !(s instanceof SVGGElement)) {
      for (const a of ['fill', 'stroke'] as const) {
        const v = cs.getPropertyValue(a)
        const p = paint(v === 'currentcolor' ? cs.color : v)
        d.setAttribute(a, p.color)
        if (p.opacity < 1 && p.color !== 'none') d.setAttribute(`${a}-opacity`, num(p.opacity))
      }
      if (cs.stroke !== 'none') d.setAttribute('stroke-width', cs.strokeWidth)
      if (s instanceof SVGTextElement) {
        // a text halo (stroke painted under the fill via CSS paint-order) would cover the
        // letters in readers without paint-order: dropped
        d.setAttribute('stroke', 'none')
        d.removeAttribute('stroke-opacity')
        d.removeAttribute('stroke-width')
        d.setAttribute('font-size', cs.fontSize)
        d.setAttribute('font-family', cs.fontFamily)
        if (cs.fontWeight !== '400') d.setAttribute('font-weight', cs.fontWeight)
      }
    }
    d.removeAttribute('class')
    d.removeAttribute('style')
  })
  clone.setAttribute('x', num(r.x))
  clone.setAttribute('y', num(r.y))
  clone.setAttribute('width', num(r.w))
  clone.setAttribute('height', num(r.h))
  clone.removeAttribute('aria-hidden')
  return new XMLSerializer().serializeToString(clone)
}

/**
 * Compose a pane body into an SVG document of its on-screen size: the same
 * DOM pass as the PNG, but the 2-D canvases come from their recorded draw
 * calls (vectorcapture.ts), the 3-D view from its projected scene, page
 * SVGs inline, HTML text as <text> and coloured boxes as <rect>.  A canvas
 * without a vector source is embedded as pixels (and noted).
 */
export async function composePaneSvg(body: HTMLElement): Promise<{ svg: string; width: number; height: number; notes: string[] }> {
  const pane = body.dataset.pane
  if (pane) renderHooks.get(pane)?.()
  const recs = await recordCanvases()
  const box = body.getBoundingClientRect()
  const W = Math.max(1, box.width)
  const H = Math.max(1, box.height)
  const at = (r: DOMRect) => ({ x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height })
  const parts: string[] = []
  const defs: string[] = []
  const notes = new Set<string>()
  let nid = 0
  parts.push(`<rect x="0" y="0" width="${num(W)}" height="${num(H)}"${fillAttrs(backgroundOf(body.querySelector<HTMLElement>('canvas')?.parentElement ?? body))}/>`)
  const opaque = (c: string) => !!c && c !== 'transparent' && !/rgba\(.*,\s*0\)$/.test(c)
  const clipped = (r: { x: number; y: number; w: number; h: number }, content: string, id?: string) => {
    const cid = `clip${nid++}`
    defs.push(`<clipPath id="${cid}"><rect x="0" y="0" width="${num(r.w)}" height="${num(r.h)}"/></clipPath>`)
    return `<g${id ? ` id="${id}"` : ''} transform="translate(${num(r.x)} ${num(r.y)})" clip-path="url(#${cid})">\n${content}\n</g>`
  }
  for (const el of body.querySelectorAll<HTMLElement | SVGSVGElement>('*')) {
    if (el.closest(SKIP) || (el instanceof SVGElement && !(el instanceof SVGSVGElement)) || !visible(el)) continue
    const r = at(el.getBoundingClientRect())
    if (el instanceof HTMLCanvasElement) {
      const hook = pane ? vectorHooks.get(pane) : undefined
      if (hook && hook.canvas === el) {
        const res = hook.build(r.w, r.h)
        res.notes.forEach((n) => notes.add(n))
        parts.push(clipped(r, serialize(res.elements), 'view-3d'))
        continue
      }
      const rec = recs.get(el)
      if (rec) {
        rec.unsupported.forEach((u) => notes.add(`Not reproduced as vectors: canvas ${u}`))
        parts.push(clipped(r, serialize(rec.elements)))
        continue
      }
      let href = ''
      try {
        href = el.toDataURL('image/png')
      } catch {
        // tainted canvas: left out
      }
      if (href) {
        parts.push(`<image x="${num(r.x)}" y="${num(r.y)}" width="${num(r.w)}" height="${num(r.h)}" preserveAspectRatio="none" xlink:href="${href}" href="${href}"/>`)
        notes.add('A canvas without a vector drawing was embedded as pixels.')
      }
      continue
    }
    if (el instanceof SVGSVGElement) {
      parts.push(inlineSvg(el, r))
      continue
    }
    if (el.closest('svg')) continue
    const cs = getComputedStyle(el)
    if (!el.querySelector('canvas, svg')) {
      const rad = Math.min(parseFloat(cs.borderTopLeftRadius) || 0, r.w / 2, r.h / 2)
      const rx = rad ? ` rx="${num(rad)}"` : ''
      const geom = `x="${num(r.x)}" y="${num(r.y)}" width="${num(r.w)}" height="${num(r.h)}"${rx}`
      if (opaque(cs.backgroundColor)) parts.push(`<rect ${geom}${fillAttrs(cs.backgroundColor)}/>`)
      if (cs.backgroundImage && cs.backgroundImage !== 'none') {
        const id = `grad${nid++}`
        const g = cssGradient(cs.backgroundImage, id)
        if (g) {
          defs.push(g)
          parts.push(`<rect ${geom} fill="url(#${id})"/>`)
        }
      }
    }
    for (const node of el.childNodes) {
      if (node.nodeType !== Node.TEXT_NODE || !node.textContent?.trim()) continue
      const range = document.createRange()
      range.selectNodeContents(node)
      const tr = at(range.getBoundingClientRect())
      if (!tr.w) continue
      const size = parseFloat(cs.fontSize) || 11
      const weight = cs.fontWeight !== '400' && cs.fontWeight !== 'normal' ? ` font-weight="${esc(cs.fontWeight)}"` : ''
      const italic = cs.fontStyle !== 'normal' ? ` font-style="${esc(cs.fontStyle)}"` : ''
      parts.push(
        `<text x="${num(tr.x)}" y="${num(tr.y + tr.h / 2 + 0.35 * size)}" font-size="${num(size)}" font-family="${esc(cs.fontFamily)}"${weight}${italic}${fillAttrs(cs.color)}>${esc(node.textContent.replace(/\s+/g, ' ').trim())}</text>`,
      )
    }
  }
  const s = useStore.getState()
  const ds = s.datasets.find((d) => d.id === s.activeDatasetId)
  const desc = [`Exported from the U-Chrom web browser${ds ? ` (dataset ${ds.name})` : ''} on ${new Date().toISOString()}.`, ...notes].join(' ')
  return { svg: svgDocument(W, H, parts.join('\n'), { title: ds?.name, desc, defs: defs.join('\n') }), width: W, height: H, notes: [...notes] }
}

/** Characters of the views' labels outside Latin-1, spelled with Latin-1 for the PDF standard fonts. */
const PDF_SUBST: Record<string, string> = { '≥': '>=', '≤': '<=', '…': '...', '−': '-', '–': '-', '—': '-', '→': '->', '←': '<-', '‘': "'", '’': "'", '“': '"', '”': '"', '≈': '~', '✕': 'x' }

/** Label text as the PDF standard fonts can show it. */
export function pdfText(s: string): string {
  return s.replace(/[≥≤…−–—→←‘’“”≈✕]/g, (c) => PDF_SUBST[c])
}

/** CSS px → PDF points (96 px = 72 pt), so a figure keeps its on-screen size. */
const PT_PER_PX = 0.75

/**
 * SVG document → PDF (jsPDF + svg2pdf.js, loaded on first use).  Text stays
 * text, in Helvetica (the PDF standard fonts cover Latin-1: other characters
 * are dropped, and noted).
 */
export async function svgToPdf(svg: string, width: number, height: number): Promise<{ blob: Blob; notes: string[] }> {
  const [{ jsPDF }, { svg2pdf }] = await Promise.all([import('jspdf'), import('svg2pdf.js')])
  const notes: string[] = []
  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
  let dropped = false
  for (const t of doc.querySelectorAll('text')) {
    const orig = t.textContent ?? ''
    const txt = pdfText(orig)
    const kept = txt.replace(/[^\u0000-\u00ff]/gu, '').trim()
    if (kept !== txt.trim()) dropped = true
    if (kept !== orig.trim()) t.textContent = kept
    t.setAttribute('font-family', 'helvetica')
  }
  for (const g of doc.querySelectorAll('[font-family]')) g.setAttribute('font-family', 'helvetica')
  if (dropped) notes.push('Characters outside Latin-1 (e.g. emoji) were left out of the PDF text; the SVG keeps them.')
  const w = width * PT_PER_PX
  const h = height * PT_PER_PX
  const pdf = new jsPDF({ orientation: w >= h ? 'landscape' : 'portrait', unit: 'pt', format: [w, h], compress: true })
  // svg2pdf reads computed styles: the SVG has to be in the document
  const host = document.createElement('div')
  host.style.cssText = 'position:fixed;left:-100000px;top:0;width:0;height:0;overflow:hidden'
  host.appendChild(document.importNode(doc.documentElement, true))
  document.body.appendChild(host)
  try {
    await svg2pdf(host.firstElementChild as Element, pdf, { x: 0, y: 0, width: w, height: h })
  } finally {
    host.remove()
  }
  return { blob: pdf.output('blob'), notes }
}

function toBlob(cv: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => cv.toBlob((b) => (b ? resolve(b) : reject(new Error('PNG encoding failed'))), 'image/png'))
}

export interface Capture {
  blob: Blob
  filename: string
  format: CaptureFormat
  /** image size: device pixels (PNG) or CSS pixels (SVG / PDF) */
  width: number
  height: number
  /** what the vector file does not reproduce exactly */
  notes: string[]
}

/** Pane body element → PNG / SVG / PDF blob + filename (no download). */
export async function capturePane(body: HTMLElement, pane: Pane, format: CaptureFormat = 'png'): Promise<Capture> {
  const filename = paneFilename(pane, new Date(), format)
  if (format === 'png') {
    const cv = await composePane(body)
    return { blob: await toBlob(cv), filename, format, width: cv.width, height: cv.height, notes: [] }
  }
  const { svg, width, height, notes } = await composePaneSvg(body)
  if (format === 'svg') return { blob: new Blob([svg], { type: CAPTURE_MIME.svg }), filename, format, width, height, notes }
  const pdf = await svgToPdf(svg, width, height)
  return { blob: pdf.blob, filename, format, width, height, notes: [...notes, ...pdf.notes] }
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

/** Save a pane as PNG, SVG or PDF (browser download); resolves with the filename and the notes. */
export async function savePane(body: HTMLElement, pane: Pane, format: CaptureFormat = 'png'): Promise<{ filename: string; notes: string[] }> {
  const { blob, filename, notes } = await capturePane(body, pane, format)
  download(blob, filename)
  return { filename, notes }
}

/** Save a pane as PNG (browser download). */
export async function savePanePng(body: HTMLElement, pane: Pane): Promise<string> {
  return (await savePane(body, pane, 'png')).filename
}

/**
 * Scripting hook (console / tests): capture a pane by id without
 * downloading; `url: true` adds an object URL of the file to look at.
 */
export async function capturePaneById(paneId: string, opts: { url?: boolean; format?: CaptureFormat } = {}) {
  const pane = useStore.getState().workspace.panes.find((p) => p.id === paneId)
  const body = document.querySelector<HTMLElement>(`.pane-body[data-pane="${paneId}"]`)
  if (!pane || !body) throw new Error(`no pane ${paneId}`)
  const { blob, filename, width, height, notes } = await capturePane(body, pane, opts.format ?? 'png')
  return { filename, bytes: blob.size, width, height, notes, ...(opts.url ? { url: URL.createObjectURL(blob) } : {}) }
}

declare global {
  interface Window {
    uchrom?: { capturePane: typeof capturePaneById; composePane: typeof composePane; composePaneSvg: typeof composePaneSvg }
  }
}
if (typeof window !== 'undefined') window.uchrom = { ...(window.uchrom ?? {}), capturePane: capturePaneById, composePane, composePaneSvg }

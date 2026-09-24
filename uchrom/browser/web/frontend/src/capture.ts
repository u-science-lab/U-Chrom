/**
 * "Save image (PNG)" of one pane: its content only (no header).  Every
 * canvas in the pane body (WebGL — the renderer keeps its drawing buffer —
 * and 2-D) is composited at its on-screen place and resolution, SVGs are
 * rasterised, and the HTML overlays that carry information (axis labels,
 * badges, legends, swatches) are drawn on top as text / boxes.  Hover tips
 * and controls are left out.
 */

import { fmtBp } from './filters'
import { datasetChroms } from './genome'
import { describeGroup, resolveScope, type Scope } from './groups'
import { activeSavedGroups, activeView, fieldKey, useStore } from './store'
import { resolveLocus } from './useLocus'
import { PANE_LABEL, type Pane } from './workspace'

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
 * `uchrom_<dataset>_<viewtype>_<scope or locus>_<timestamp>.png`.
 * Genome-coordinate views name the locus (and a cell / group scope after
 * it); the others name their scope ("all" for every cell).
 */
export function captureFilename(o: {
  dataset: string
  type: Pane['type']
  scope?: string | null
  locus?: { chrom: string; start: number; end: number } | null
  date: Date
}): string {
  const parts = ['uchrom', o.dataset, PANE_LABEL[o.type].toLowerCase()]
  const locus = o.locus ? `${o.locus.chrom}-${fmtBp(o.locus.start)}-${fmtBp(o.locus.end)}` : null
  if (locus) parts.push(locus)
  if (o.scope || !locus) parts.push(o.scope || 'all')
  parts.push(timestamp(o.date))
  return `${parts.map(safePart).join('_')}.png`
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
export function paneFilename(pane: Pane, date = new Date()): string {
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
  })
}

/** First non-transparent background colour from `el` up. */
function backgroundOf(el: HTMLElement | null): string {
  for (let e = el; e; e = e.parentElement) {
    const bg = getComputedStyle(e).backgroundColor
    if (bg && bg !== 'transparent' && !/rgba\(.*,\s*0\)$/.test(bg)) return bg
  }
  return '#1b1d21'
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

function toBlob(cv: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => cv.toBlob((b) => (b ? resolve(b) : reject(new Error('PNG encoding failed'))), 'image/png'))
}

/** Pane body element → PNG blob + filename (no download). */
export async function capturePane(body: HTMLElement, pane: Pane): Promise<{ blob: Blob; filename: string; width: number; height: number }> {
  const cv = await composePane(body)
  return { blob: await toBlob(cv), filename: paneFilename(pane), width: cv.width, height: cv.height }
}

/** Save a pane as PNG (browser download). */
export async function savePanePng(body: HTMLElement, pane: Pane): Promise<string> {
  const { blob, filename } = await capturePane(body, pane)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
  return filename
}

/**
 * Scripting hook (console / tests): capture a pane by id without
 * downloading; `url: true` adds an object URL of the PNG to look at.
 */
export async function capturePaneById(paneId: string, opts: { url?: boolean } = {}) {
  const pane = useStore.getState().workspace.panes.find((p) => p.id === paneId)
  const body = document.querySelector<HTMLElement>(`.pane-body[data-pane="${paneId}"]`)
  if (!pane || !body) throw new Error(`no pane ${paneId}`)
  const { blob, filename, width, height } = await capturePane(body, pane)
  return { filename, bytes: blob.size, width, height, ...(opts.url ? { url: URL.createObjectURL(blob) } : {}) }
}

declare global {
  interface Window {
    uchrom?: { capturePane: typeof capturePaneById; composePane: typeof composePane }
  }
}
if (typeof window !== 'undefined') window.uchrom = { ...(window.uchrom ?? {}), capturePane: capturePaneById, composePane }

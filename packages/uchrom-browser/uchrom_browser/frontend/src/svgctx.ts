/**
 * SvgContext2D: records the Canvas 2-D calls of one frame as SVG elements.
 *
 * The 2-D panes (matrix, genome rows, stats, embedding / spatial) draw with
 * a CanvasRenderingContext2D; during a vector capture their context is a
 * tee (see vectorcapture.ts) that also feeds this recorder, so the SVG is
 * drawn by the same code as the screen.  Covered: paths (moveTo / lineTo /
 * arc / quadratic and cubic curves / rect), fill / stroke, rectangles, text
 * (kept as <text>), line dashes, globalAlpha, save / restore and transforms.
 * putImageData / drawImage (heat-map pixels, section images) become
 * embedded PNG <image>s.  Coordinates are written in CSS pixels: the device
 * pixel ratio the canvas transform carries is divided out.
 */

import { esc, num, paint, type SvgEl } from './svg'

type Matrix = [number, number, number, number, number, number]

interface State {
  m: Matrix
  fillStyle: string
  strokeStyle: string
  lineWidth: number
  lineDash: number[]
  lineCap: string
  lineJoin: string
  globalAlpha: number
  font: string
  textAlign: string
  textBaseline: string
  smoothing: boolean
}

/** Turns pixels into a PNG data URL (needs a DOM; injectable for tests). */
export interface ImageEncoder {
  imageData(data: ImageData): string | null
  source(src: CanvasImageSource, sx: number, sy: number, sw: number, sh: number): string | null
}

const domEncoder: ImageEncoder = {
  imageData(data) {
    const c = document.createElement('canvas')
    c.width = data.width
    c.height = data.height
    c.getContext('2d')?.putImageData(data, 0, 0)
    return c.toDataURL('image/png')
  },
  source(src, sx, sy, sw, sh) {
    const c = document.createElement('canvas')
    c.width = Math.max(1, Math.round(sw))
    c.height = Math.max(1, Math.round(sh))
    const g = c.getContext('2d')
    if (!g) return null
    try {
      g.drawImage(src, sx, sy, sw, sh, 0, 0, c.width, c.height)
      return c.toDataURL('image/png')
    } catch {
      // a cross-origin image taints the canvas: link it instead
      return src instanceof HTMLImageElement ? src.currentSrc || src.src : null
    }
  },
}

/** Natural pixel size of an image source. */
function sourceSize(src: CanvasImageSource): [number, number] {
  const s = src as { naturalWidth?: number; naturalHeight?: number; videoWidth?: number; videoHeight?: number; width?: number | { baseVal: { value: number } }; height?: number | { baseVal: { value: number } } }
  if (s.naturalWidth) return [s.naturalWidth, s.naturalHeight ?? 0]
  if (s.videoWidth) return [s.videoWidth, s.videoHeight ?? 0]
  const w = typeof s.width === 'number' ? s.width : s.width?.baseVal.value ?? 0
  const h = typeof s.height === 'number' ? s.height : s.height?.baseVal.value ?? 0
  return [w, h]
}

const BASELINE: Record<string, number> = { top: 0.8, hanging: 0.8, middle: 0.35, alphabetic: 0, ideographic: -0.2, bottom: -0.2 }
const ANCHOR: Record<string, string> = { left: 'start', start: 'start', center: 'middle', right: 'end', end: 'end' }

/** '11px -apple-system, "Segoe UI", sans-serif' → parts (size in px). */
export function parseFont(font: string): { style: string; weight: string; size: number; family: string } {
  const m = /^\s*((?:(?:italic|oblique|normal|bold|bolder|lighter|small-caps|\d{3})\s+)*)([\d.]+)px(?:\s*\/\s*[^\s]+)?\s+(.+)$/i.exec(font)
  if (!m) return { style: 'normal', weight: 'normal', size: 10, family: 'sans-serif' }
  const words = m[1].trim().split(/\s+/).filter(Boolean)
  const style = words.find((w) => /^(italic|oblique)$/i.test(w)) ?? 'normal'
  const weight = words.find((w) => /^(bold|bolder|lighter|\d{3})$/i.test(w)) ?? 'normal'
  return { style, weight, size: parseFloat(m[2]), family: m[3].trim() }
}

const TAU = 2 * Math.PI

export class SvgContext2D {
  readonly elements: SvgEl[] = []
  /** Canvas methods called that this recorder does not reproduce. */
  readonly unsupported = new Set<string>()
  private s: State
  private stack: State[] = []
  private d: string[] = []
  /** the current path is exactly one full circle (cx, cy, r in output space) */
  private circle: { cx: number; cy: number; r: number } | null = null
  private pathOps = 0
  private open = false
  private pathId = 0
  /** the last element was the fill of the current path (a stroke may join it) */
  private lastFill: { el: SvgEl; path: number } | null = null
  /** CSS pixels per canvas unit after the device-pixel transform */
  private readonly out: number

  /** @param dpr device pixels per CSS pixel of the canvas (divided out of the canvas transform) */
  constructor(dpr = 1, private readonly encoder: ImageEncoder = domEncoder) {
    this.out = 1 / dpr
    this.s = {
      m: [1, 0, 0, 1, 0, 0],
      fillStyle: '#000000',
      strokeStyle: '#000000',
      lineWidth: 1,
      lineDash: [],
      lineCap: 'butt',
      lineJoin: 'miter',
      globalAlpha: 1,
      font: '10px sans-serif',
      textAlign: 'start',
      textBaseline: 'alphabetic',
      smoothing: true,
    }
  }

  // ---- state ---------------------------------------------------------------
  set fillStyle(v: unknown) {
    if (typeof v === 'string') this.s.fillStyle = v
    else this.unsupported.add('fillStyle (gradient / pattern)')
  }
  get fillStyle(): string {
    return this.s.fillStyle
  }
  set strokeStyle(v: unknown) {
    if (typeof v === 'string') this.s.strokeStyle = v
    else this.unsupported.add('strokeStyle (gradient / pattern)')
  }
  get strokeStyle(): string {
    return this.s.strokeStyle
  }
  set lineWidth(v: number) {
    if (v > 0 && Number.isFinite(v)) this.s.lineWidth = v
  }
  get lineWidth(): number {
    return this.s.lineWidth
  }
  set lineCap(v: string) {
    this.s.lineCap = v
  }
  set lineJoin(v: string) {
    this.s.lineJoin = v
  }
  set globalAlpha(v: number) {
    if (v >= 0 && v <= 1) this.s.globalAlpha = v
  }
  get globalAlpha(): number {
    return this.s.globalAlpha
  }
  set font(v: string) {
    this.s.font = v
  }
  get font(): string {
    return this.s.font
  }
  set textAlign(v: string) {
    this.s.textAlign = v
  }
  set textBaseline(v: string) {
    this.s.textBaseline = v
  }
  set imageSmoothingEnabled(v: boolean) {
    this.s.smoothing = v
  }
  setLineDash(d: number[]) {
    this.s.lineDash = d.filter((x) => Number.isFinite(x) && x >= 0)
  }
  save() {
    this.stack.push({ ...this.s, m: [...this.s.m] as Matrix, lineDash: [...this.s.lineDash] })
  }
  restore() {
    const s = this.stack.pop()
    if (s) this.s = s
  }

  // ---- transforms ----------------------------------------------------------
  setTransform(a: number | DOMMatrix2DInit, b = 0, c = 0, d = 1, e = 0, f = 0) {
    if (typeof a === 'object') this.s.m = [a.a ?? 1, a.b ?? 0, a.c ?? 0, a.d ?? 1, a.e ?? 0, a.f ?? 0]
    else this.s.m = [a, b, c, d, e, f]
  }
  resetTransform() {
    this.s.m = [1, 0, 0, 1, 0, 0]
  }
  transform(a: number, b: number, c: number, d: number, e: number, f: number) {
    const [A, B, C, D, E, F] = this.s.m
    this.s.m = [A * a + C * b, B * a + D * b, A * c + C * d, B * c + D * d, A * e + C * f + E, B * e + D * f + F]
  }
  translate(x: number, y: number) {
    this.transform(1, 0, 0, 1, x, y)
  }
  scale(x: number, y: number) {
    this.transform(x, 0, 0, y, 0, 0)
  }
  rotate(t: number) {
    this.transform(Math.cos(t), Math.sin(t), -Math.sin(t), Math.cos(t), 0, 0)
  }

  /** canvas coordinates → output (CSS px) */
  private T(x: number, y: number): [number, number] {
    const [a, b, c, d, e, f] = this.s.m
    return [(a * x + c * y + e) * this.out, (b * x + d * y + f) * this.out]
  }
  /** uniform scale of the current transform (output px per canvas unit) */
  private get k(): number {
    const [a, b, c, d] = this.s.m
    return Math.sqrt(Math.abs(a * d - b * c)) * this.out
  }
  private get axisAligned(): boolean {
    const [, b, c] = this.s.m
    return Math.abs(b) < 1e-9 && Math.abs(c) < 1e-9
  }
  private get mirrored(): boolean {
    const [a, b, c, d] = this.s.m
    return a * d - b * c < 0
  }

  // ---- paths ---------------------------------------------------------------
  beginPath() {
    this.d = []
    this.circle = null
    this.pathOps = 0
    this.open = false
    this.pathId++
  }
  moveTo(x: number, y: number) {
    const [X, Y] = this.T(x, y)
    this.d.push(`M${num(X)} ${num(Y)}`)
    this.open = true
    this.pathOps++
    this.circle = null
  }
  lineTo(x: number, y: number) {
    const [X, Y] = this.T(x, y)
    this.d.push(`${this.open ? 'L' : 'M'}${num(X)} ${num(Y)}`)
    this.open = true
    this.pathOps++
    this.circle = null
  }
  closePath() {
    if (this.open) this.d.push('Z')
    this.circle = null
  }
  rect(x: number, y: number, w: number, h: number) {
    this.moveTo(x, y)
    this.lineTo(x + w, y)
    this.lineTo(x + w, y + h)
    this.lineTo(x, y + h)
    this.closePath()
  }
  quadraticCurveTo(cx: number, cy: number, x: number, y: number) {
    const [CX, CY] = this.T(cx, cy)
    const [X, Y] = this.T(x, y)
    this.d.push(`Q${num(CX)} ${num(CY)} ${num(X)} ${num(Y)}`)
    this.pathOps++
    this.circle = null
  }
  bezierCurveTo(c1x: number, c1y: number, c2x: number, c2y: number, x: number, y: number) {
    const [A, B] = this.T(c1x, c1y)
    const [C, D] = this.T(c2x, c2y)
    const [X, Y] = this.T(x, y)
    this.d.push(`C${num(A)} ${num(B)} ${num(C)} ${num(D)} ${num(X)} ${num(Y)}`)
    this.pathOps++
    this.circle = null
  }
  arc(cx: number, cy: number, r: number, start: number, end: number, ccw = false) {
    if (!(r >= 0)) return
    let span = ccw ? start - end : end - start
    const full = span >= TAU - 1e-9 || span <= -TAU + 1e-9
    if (!full) span = ((span % TAU) + TAU) % TAU
    const R = r * this.k
    const at = (t: number) => this.T(cx + r * Math.cos(t), cy + r * Math.sin(t))
    const [X0, Y0] = at(start)
    const firstOp = this.pathOps === 0
    this.d.push(`${this.open ? 'L' : 'M'}${num(X0)} ${num(Y0)}`)
    this.open = true
    // canvas clockwise (y down) is SVG sweep 1; a mirroring transform flips it
    const sweep = (ccw ? 0 : 1) ^ (this.mirrored ? 1 : 0)
    if (full) {
      const [Xm, Ym] = at(start + (ccw ? -Math.PI : Math.PI))
      this.d.push(`A${num(R)} ${num(R)} 0 0 ${sweep} ${num(Xm)} ${num(Ym)}`, `A${num(R)} ${num(R)} 0 0 ${sweep} ${num(X0)} ${num(Y0)}`)
    } else if (span > 0) {
      const [X1, Y1] = at(ccw ? start - span : start + span)
      this.d.push(`A${num(R)} ${num(R)} 0 ${span > Math.PI ? 1 : 0} ${sweep} ${num(X1)} ${num(Y1)}`)
    }
    this.pathOps++
    if (full && firstOp) {
      const [CX, CY] = this.T(cx, cy)
      this.circle = { cx: CX, cy: CY, r: R }
    } else this.circle = null
  }

  private paintStyle(kind: 'fill' | 'stroke'): Record<string, string> | null {
    const p = paint(kind === 'fill' ? this.s.fillStyle : this.s.strokeStyle, this.s.globalAlpha)
    if (p.color === 'none' || p.opacity <= 0) return null
    const st: Record<string, string> = {}
    if (kind === 'fill') {
      st.fill = p.color
      if (p.opacity < 1) st['fill-opacity'] = num1(p.opacity)
      return st
    }
    st.fill = 'none'
    st.stroke = p.color
    if (p.opacity < 1) st['stroke-opacity'] = num1(p.opacity)
    st['stroke-width'] = num(this.s.lineWidth * this.k)
    if (this.s.lineCap !== 'butt') st['stroke-linecap'] = this.s.lineCap
    if (this.s.lineJoin !== 'miter') st['stroke-linejoin'] = this.s.lineJoin
    if (this.s.lineDash.length) st['stroke-dasharray'] = this.s.lineDash.map((v) => num(v * this.k)).join(' ')
    return st
  }

  private pathEl(style: Record<string, string>): SvgEl {
    if (this.circle) return { tag: 'circle', geom: `cx="${num(this.circle.cx)}" cy="${num(this.circle.cy)}" r="${num(this.circle.r)}"`, style }
    return { tag: 'path', geom: `d="${this.d.join('')}"`, style }
  }

  fill() {
    const st = this.paintStyle('fill')
    this.lastFill = null
    if (!st || !this.d.length) return
    const el = this.pathEl(st)
    this.elements.push(el)
    this.lastFill = { el, path: this.pathId }
  }
  stroke() {
    const st = this.paintStyle('stroke')
    if (!st || !this.d.length) return
    // the stroke of a path just filled joins that element (one dot = one circle)
    const last = this.lastFill
    if (last && last.path === this.pathId && this.elements[this.elements.length - 1] === last.el) {
      const { fill: _fill, ...rest } = st
      Object.assign(last.el.style, rest)
      this.lastFill = null
      return
    }
    this.elements.push(this.pathEl(st))
  }
  clip() {
    this.unsupported.add('clip')
  }

  // ---- rectangles ----------------------------------------------------------
  private rectEl(x: number, y: number, w: number, h: number, style: Record<string, string>): SvgEl {
    if (this.axisAligned) {
      const [X0, Y0] = this.T(x, y)
      const [X1, Y1] = this.T(x + w, y + h)
      return { tag: 'rect', geom: `x="${num(Math.min(X0, X1))}" y="${num(Math.min(Y0, Y1))}" width="${num(Math.abs(X1 - X0))}" height="${num(Math.abs(Y1 - Y0))}"`, style }
    }
    const pts = [this.T(x, y), this.T(x + w, y), this.T(x + w, y + h), this.T(x, y + h)]
    return { tag: 'path', geom: `d="M${pts.map(([X, Y]) => `${num(X)} ${num(Y)}`).join('L')}Z"`, style }
  }
  fillRect(x: number, y: number, w: number, h: number) {
    const st = this.paintStyle('fill')
    this.lastFill = null
    if (st && w && h) this.elements.push(this.rectEl(x, y, w, h, st))
  }
  strokeRect(x: number, y: number, w: number, h: number) {
    const st = this.paintStyle('stroke')
    if (!st) return
    // the stroke of the square just filled at the same place joins it (square dots)
    const prev = this.elements[this.elements.length - 1]
    const el = this.rectEl(x, y, w, h, st)
    if (prev && prev.tag === el.tag && prev.geom === el.geom && prev.style.fill && prev.style.fill !== 'none' && !prev.style.stroke) {
      const { fill: _fill, ...rest } = st
      Object.assign(prev.style, rest)
      return
    }
    this.elements.push(el)
  }
  clearRect(_x: number, _y: number, _w: number, _h: number) {
    // frames start on a cleared canvas; clearing part of a drawing is not reproduced
    if (this.elements.length) this.unsupported.add('clearRect')
  }
  roundRect(x: number, y: number, w: number, h: number, _r?: number) {
    this.rect(x, y, w, h)
  }

  // ---- text ----------------------------------------------------------------
  fillText(text: string, x: number, y: number) {
    const p = paint(this.s.fillStyle, this.s.globalAlpha)
    if (p.color === 'none' || p.opacity <= 0 || !text) return
    const f = parseFont(this.s.font)
    const dy = (BASELINE[this.s.textBaseline] ?? 0) * f.size
    const style: Record<string, string> = { fill: p.color, 'font-family': f.family, 'font-size': '' }
    if (p.opacity < 1) style['fill-opacity'] = num1(p.opacity)
    if (f.weight !== 'normal') style['font-weight'] = f.weight
    if (f.style !== 'normal') style['font-style'] = f.style
    const anchor = ANCHOR[this.s.textAlign] ?? 'start'
    if (anchor !== 'start') style['text-anchor'] = anchor
    let geom: string
    if (this.axisAligned && !this.mirrored) {
      const [X, Y] = this.T(x, y + dy)
      style['font-size'] = num(f.size * this.k)
      geom = `x="${num(X)}" y="${num(Y)}"`
    } else {
      // rotated text (axis titles): keep the canvas transform on the element
      const o = this.out
      const [a, b, c, d, e, g] = this.s.m
      style['font-size'] = num(f.size)
      geom = `x="${num(x)}" y="${num(y + dy)}" transform="matrix(${[a * o, b * o, c * o, d * o, e * o, g * o].map((v) => +v.toFixed(5)).join(' ')})"`
    }
    this.lastFill = null
    this.elements.push({ tag: 'text', geom, style, text })
  }
  strokeText(_text: string, _x: number, _y: number) {
    this.unsupported.add('strokeText')
  }

  // ---- images --------------------------------------------------------------
  private image(href: string | null, x: number, y: number, w: number, h: number) {
    if (!href || !w || !h) return
    const o = this.out
    const [a, b, c, d, e, f] = this.s.m
    const op = this.s.globalAlpha < 1 ? ` opacity="${num1(this.s.globalAlpha)}"` : ''
    const smooth = this.s.smoothing ? '' : ` style="image-rendering:pixelated;image-rendering:optimizeSpeed"`
    // negative sizes mirror the image (canvas allows them, SVG does not)
    const sx = w < 0 ? -1 : 1
    const sy = h < 0 ? -1 : 1
    const flip = sx < 0 || sy < 0 ? ` transform="translate(${num(x)} ${num(y)}) scale(${sx} ${sy}) translate(${num(-x)} ${num(-y)})"` : ''
    const geom = `x="${num(x)}" y="${num(y)}" width="${num(Math.abs(w))}" height="${num(Math.abs(h))}"`
    const mat = [a * o, b * o, c * o, d * o, e * o, f * o].map((v) => +v.toFixed(6)).join(' ')
    this.lastFill = null
    this.elements.push({
      tag: 'image',
      geom: '',
      style: {},
      raw: `<g transform="matrix(${mat})"${op}><image ${geom}${flip} preserveAspectRatio="none"${smooth} xlink:href="${esc(href)}" href="${esc(href)}"/></g>`,
    })
  }
  drawImage(src: CanvasImageSource, ...a: number[]) {
    const [nw, nh] = sourceSize(src)
    let sx = 0, sy = 0, sw = nw, sh = nh, dx: number, dy: number, dw = nw, dh = nh
    if (a.length === 2) [dx, dy] = a
    else if (a.length === 4) [dx, dy, dw, dh] = a
    else if (a.length === 8) [sx, sy, sw, sh, dx, dy, dw, dh] = a
    else return
    this.image(this.encoder.source(src, sx, sy, sw, sh), dx, dy, dw, dh)
  }
  putImageData(data: ImageData, dx: number, dy: number) {
    // putImageData ignores the transform and alpha: device pixels at (dx, dy)
    const o = this.out
    const href = this.encoder.imageData(data)
    if (!href) return
    this.lastFill = null
    this.elements.push({
      tag: 'image',
      geom: '',
      style: {},
      raw: `<image x="${num(dx * o)}" y="${num(dy * o)}" width="${num(data.width * o)}" height="${num(data.height * o)}" preserveAspectRatio="none" style="image-rendering:pixelated;image-rendering:optimizeSpeed" xlink:href="${esc(href)}" href="${esc(href)}"/>`,
    })
  }

  // ---- no visual effect ----------------------------------------------------
  measureText(text: string): TextMetrics {
    // the tee answers with the real context; standalone: an estimate
    return { width: text.length * parseFont(this.s.font).size * 0.55 } as TextMetrics
  }
  getLineDash(): number[] {
    return [...this.s.lineDash]
  }
}

/** Opacity with 3 decimals. */
function num1(v: number): string {
  return String(Math.round(v * 1000) / 1000)
}

/** Methods / properties a tee forwards to the recorder (others are reported unsupported when they draw). */
export const RECORDED = new Set([
  'fillStyle', 'strokeStyle', 'lineWidth', 'lineCap', 'lineJoin', 'globalAlpha', 'font', 'textAlign', 'textBaseline', 'imageSmoothingEnabled',
  'setLineDash', 'save', 'restore', 'setTransform', 'resetTransform', 'transform', 'translate', 'scale', 'rotate',
  'beginPath', 'moveTo', 'lineTo', 'closePath', 'rect', 'quadraticCurveTo', 'bezierCurveTo', 'arc', 'fill', 'stroke', 'clip',
  'fillRect', 'strokeRect', 'clearRect', 'roundRect', 'fillText', 'strokeText', 'drawImage', 'putImageData',
])
/** Calls with no drawing effect the tee passes to the canvas only. */
export const PASSIVE = new Set(['measureText', 'getLineDash', 'getTransform', 'isPointInPath', 'isPointInStroke', 'getImageData', 'createImageData', 'getContextAttributes', 'canvas'])

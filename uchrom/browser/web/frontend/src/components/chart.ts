/** Minimal canvas chart primitives shared by the stats / tracks / matrix panes. */

export const CHART = {
  axis: 'rgba(216,218,223,0.55)',
  grid: 'rgba(216,218,223,0.08)',
  text: '#b9bdc4',
  muted: '#8f949c',
  accent: '#5c9ded',
  font: '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
}

export interface Box {
  x: number
  y: number
  w: number
  h: number
}

/** Axes with ticks, tick labels, grid lines and axis titles around `box`. */
export function drawAxes(
  g: CanvasRenderingContext2D,
  box: Box,
  x: { ticks: number[]; pos: (v: number) => number; fmt: (v: number) => string; label?: string },
  y: { ticks: number[]; pos: (v: number) => number; fmt: (v: number) => string; label?: string },
) {
  g.save()
  g.font = CHART.font
  g.lineWidth = 1
  // grid
  g.strokeStyle = CHART.grid
  for (const t of y.ticks) {
    const py = Math.round(y.pos(t)) + 0.5
    if (py < box.y - 1 || py > box.y + box.h + 1) continue
    g.beginPath()
    g.moveTo(box.x, py)
    g.lineTo(box.x + box.w, py)
    g.stroke()
  }
  // axis lines
  g.strokeStyle = CHART.axis
  g.beginPath()
  g.moveTo(box.x + 0.5, box.y)
  g.lineTo(box.x + 0.5, box.y + box.h + 0.5)
  g.lineTo(box.x + box.w, box.y + box.h + 0.5)
  g.stroke()
  // x ticks
  g.fillStyle = CHART.text
  g.textAlign = 'center'
  g.textBaseline = 'top'
  for (const t of x.ticks) {
    const px = Math.round(x.pos(t)) + 0.5
    if (px < box.x - 1 || px > box.x + box.w + 1) continue
    g.beginPath()
    g.moveTo(px, box.y + box.h)
    g.lineTo(px, box.y + box.h + 4)
    g.stroke()
    g.fillText(x.fmt(t), px, box.y + box.h + 6)
  }
  // y ticks
  g.textAlign = 'right'
  g.textBaseline = 'middle'
  for (const t of y.ticks) {
    const py = Math.round(y.pos(t)) + 0.5
    if (py < box.y - 1 || py > box.y + box.h + 1) continue
    g.beginPath()
    g.moveTo(box.x - 4, py)
    g.lineTo(box.x, py)
    g.stroke()
    g.fillText(y.fmt(t), box.x - 6, py)
  }
  g.fillStyle = CHART.muted
  if (x.label) {
    g.textAlign = 'center'
    g.textBaseline = 'bottom'
    g.fillText(x.label, box.x + box.w / 2, box.y + box.h + 34)
  }
  if (y.label) {
    g.translate(box.x - 44, box.y + box.h / 2)
    g.rotate(-Math.PI / 2)
    g.textAlign = 'center'
    g.textBaseline = 'top'
    g.fillText(y.label, 0, 0)
  }
  g.restore()
}

/** Horizontal colour ramp with end labels. */
export function drawColorRamp(g: CanvasRenderingContext2D, box: Box, color: (t: number) => string, lo: string, hi: string, title?: string) {
  const steps = Math.max(2, Math.floor(box.w))
  for (let i = 0; i < steps; i++) {
    g.fillStyle = color(i / (steps - 1))
    g.fillRect(box.x + (i * box.w) / steps, box.y, box.w / steps + 1, box.h)
  }
  g.save()
  g.font = CHART.font
  g.fillStyle = CHART.text
  g.textBaseline = 'top'
  g.textAlign = 'left'
  g.fillText(lo, box.x, box.y + box.h + 3)
  g.textAlign = 'right'
  g.fillText(hi, box.x + box.w, box.y + box.h + 3)
  if (title) {
    g.textAlign = 'left'
    g.textBaseline = 'bottom'
    g.fillStyle = CHART.muted
    g.fillText(title, box.x, box.y - 3)
  }
  g.restore()
}

export const rgb = (c: [number, number, number], a = 1) =>
  a >= 1 ? `rgb(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)})` : `rgba(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)},${a})`

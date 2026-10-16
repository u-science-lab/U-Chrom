/**
 * Vector capture pass.  A vector export asks every 2-D pane to draw one
 * more frame (`useCaptureEpoch` is a dependency of their draw effects);
 * during that pass `recordable()` hands the draw code a tee context that
 * paints the canvas as usual and records the same calls into an
 * SvgContext2D, kept per canvas.  Outside a pass `recordable()` returns
 * the plain context: no cost on normal frames.
 */

import { create } from 'zustand'
import { PASSIVE, RECORDED, SvgContext2D } from './svgctx'

/** Bumped by each capture pass; the 2-D panes redraw when it changes. */
export const useCaptureEpoch = create<{ epoch: number }>(() => ({ epoch: 0 }))

let active = false
const recordings = new Map<HTMLCanvasElement, SvgContext2D>()

/** A tee over `g` that also records into an SvgContext2D for `cv` (during a capture pass only). */
export function recordable(cv: HTMLCanvasElement, g: CanvasRenderingContext2D): CanvasRenderingContext2D {
  if (!active) return g
  const cssW = parseFloat(cv.style.width) || cv.clientWidth || cv.width
  const rec = new SvgContext2D(cssW ? cv.width / cssW : 1)
  recordings.set(cv, rec) // the latest frame of this canvas wins
  return teeContext(g, rec)
}

/** Forward every call / assignment to `g`; mirror the drawing ones into `rec`. */
export function teeContext(g: CanvasRenderingContext2D, rec: SvgContext2D): CanvasRenderingContext2D {
  const r = rec as unknown as Record<string, unknown>
  return new Proxy(g, {
    get(target, prop) {
      const v = (target as unknown as Record<PropertyKey, unknown>)[prop]
      if (typeof v !== 'function') return v
      const name = String(prop)
      return (...args: unknown[]) => {
        if (RECORDED.has(name)) (r[name] as (...a: unknown[]) => void).apply(rec, args)
        else if (!PASSIVE.has(name)) rec.unsupported.add(name)
        return (v as (...a: unknown[]) => unknown).apply(target, args)
      }
    },
    set(target, prop, value) {
      ;(target as unknown as Record<PropertyKey, unknown>)[prop] = value
      const name = String(prop)
      // the canvas normalises what it accepts (colours to #rrggbb / rgba()); record that
      if (RECORDED.has(name)) r[name] = (target as unknown as Record<PropertyKey, unknown>)[prop]
      return true
    },
  })
}

const frame = () => new Promise<void>((res) => requestAnimationFrame(() => res()))

/**
 * Run one capture pass: every mounted 2-D pane redraws through a recording
 * context.  Resolves with the recordings by canvas (frames that drew nothing
 * this pass — no data yet — are absent; their canvas is embedded as pixels).
 */
export async function recordCanvases(): Promise<Map<HTMLCanvasElement, SvgContext2D>> {
  recordings.clear()
  active = true
  try {
    useCaptureEpoch.setState((s) => ({ epoch: s.epoch + 1 }))
    // React commits, then runs the effects after paint
    await frame()
    await frame()
    await new Promise((res) => setTimeout(res, 0))
  } finally {
    active = false
  }
  const out = new Map(recordings)
  recordings.clear()
  return out
}

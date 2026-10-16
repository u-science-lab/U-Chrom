import { useEffect, useState, type RefObject } from 'react'
import { recordable } from '../vectorcapture'

/** Content size of an element, updated on resize. */
export function useSize(ref: RefObject<HTMLElement | null>): { w: number; h: number } {
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () => setSize({ w: el.clientWidth, h: el.clientHeight })
    const ro = new ResizeObserver(update)
    ro.observe(el)
    update()
    return () => ro.disconnect()
  }, [ref])
  return size
}

/** Size a canvas for crisp drawing at devicePixelRatio; returns its 2-D context. */
export function prepareCanvas(cv: HTMLCanvasElement, w: number, h: number): CanvasRenderingContext2D | null {
  const dpr = window.devicePixelRatio || 1
  cv.width = Math.max(1, Math.round(w * dpr))
  cv.height = Math.max(1, Math.round(h * dpr))
  cv.style.width = `${w}px`
  cv.style.height = `${h}px`
  const g = cv.getContext('2d')
  if (!g) return null
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.clearRect(0, 0, w, h)
  // during a vector export the frame is also recorded as SVG
  return recordable(cv, g)
}

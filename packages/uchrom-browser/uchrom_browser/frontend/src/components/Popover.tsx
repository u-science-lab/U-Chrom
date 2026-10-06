import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import { createPortal } from 'react-dom'

export interface Rect {
  left: number
  top: number
  right: number
  bottom: number
}

export interface Placement {
  left: number
  top: number
  /** height the popover may use (its content scrolls beyond) */
  maxHeight: number
  /** opened above the anchor (not enough room below) */
  above: boolean
}

/**
 * Where a popover of `size` goes next to `anchor` inside a `view` (both in
 * viewport px): below the anchor, flipped above when there is more room
 * there; left-aligned with the anchor, right-aligned when it would overflow
 * to the right; always clamped `margin` px inside the view.  Pure — tested.
 */
export function placePopover(anchor: Rect, size: { width: number; height: number }, view: { width: number; height: number }, margin = 8, gap = 2): Placement {
  const below = view.height - margin - (anchor.bottom + gap)
  const aboveRoom = anchor.top - gap - margin
  const above = size.height > below && aboveRoom > below
  const maxHeight = Math.max(80, above ? aboveRoom : below)
  const h = Math.min(size.height, maxHeight)
  let top = above ? anchor.top - gap - h : anchor.bottom + gap
  top = Math.max(margin, Math.min(top, view.height - margin - h))
  let left = anchor.left
  if (left + size.width > view.width - margin) left = anchor.right - size.width // right-align to the anchor
  left = Math.max(margin, Math.min(left, view.width - margin - size.width))
  return { left, top, maxHeight, above }
}

/**
 * A menu / picker floating above everything: rendered in a portal on
 * <body> with `position: fixed`, placed next to `anchor` by placePopover,
 * re-placed on scroll (capture phase: inner scrolling panels count) and
 * resize; closes on an outside click or Esc.
 */
export function Popover({
  anchor,
  open,
  onClose,
  className = '',
  children,
}: {
  anchor: RefObject<HTMLElement | null>
  open: boolean
  onClose(): void
  className?: string
  children: React.ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<Placement | null>(null)
  const place = useCallback(() => {
    const a = anchor.current
    const el = ref.current
    if (!a || !el) return
    const r = a.getBoundingClientRect()
    // natural size: measure without the height limit
    el.style.maxHeight = 'none'
    const size = { width: el.offsetWidth, height: el.scrollHeight }
    const next = placePopover(r, size, { width: window.innerWidth, height: window.innerHeight })
    el.style.maxHeight = `${next.maxHeight}px`
    setPos((p) => (p && p.left === next.left && p.top === next.top && p.maxHeight === next.maxHeight && p.above === next.above ? p : next))
  }, [anchor])
  useLayoutEffect(() => {
    if (open) place()
    else setPos(null)
  }, [open, place, children])
  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node
      if (ref.current?.contains(t) || anchor.current?.contains(t)) return
      onClose()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('pointerdown', onDown, true)
    window.addEventListener('keydown', onKey, true)
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('pointerdown', onDown, true)
      window.removeEventListener('keydown', onKey, true)
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, onClose, place, anchor])
  if (!open) return null
  return createPortal(
    <div
      ref={ref}
      className={`popover ${className}`}
      style={pos ? { left: pos.left, top: pos.top, maxHeight: pos.maxHeight } : { left: -9999, top: 0, visibility: 'hidden' }}
      data-above={pos?.above ? '' : undefined}
    >
      {children}
    </div>,
    document.body,
  )
}

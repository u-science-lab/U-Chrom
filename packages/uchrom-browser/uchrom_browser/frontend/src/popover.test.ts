import { describe, expect, it } from 'vitest'
import { placePopover } from './components/Popover'

const view = { width: 1000, height: 700 }
const at = (left: number, top: number, w = 120, h = 24) => ({ left, top, right: left + w, bottom: top + h })

describe('popover placement', () => {
  it('opens below the anchor, left-aligned', () => {
    const p = placePopover(at(100, 100), { width: 280, height: 300 }, view)
    expect(p).toEqual({ left: 100, top: 126, maxHeight: 700 - 8 - 126, above: false })
  })
  it('flips above when there is more room above (bottom-most inspector row)', () => {
    const p = placePopover(at(700, 640), { width: 280, height: 400 }, view)
    expect(p.above).toBe(true)
    expect(p.top).toBe(640 - 2 - 400)
    expect(p.maxHeight).toBe(640 - 2 - 8)
  })
  it('stays below and scrolls when below is roomier, even if it does not fit', () => {
    const p = placePopover(at(100, 200), { width: 280, height: 900 }, view)
    expect(p.above).toBe(false)
    expect(p.maxHeight).toBe(700 - 8 - 226)
    expect(p.top).toBe(226)
  })
  it('right-aligns to the anchor when it would overflow to the right', () => {
    const p = placePopover(at(900, 100, 90), { width: 280, height: 100 }, view)
    expect(p.left).toBe(990 - 280)
  })
  it('clamps within the viewport with an 8 px margin (left and right)', () => {
    expect(placePopover(at(2, 100, 10), { width: 280, height: 100 }, view).left).toBe(8)
    const narrow = { width: 300, height: 700 }
    const p = placePopover(at(250, 100, 40), { width: 290, height: 100 }, narrow)
    expect(p.left).toBe(8) // wider than the space: pinned to the left margin
  })
})

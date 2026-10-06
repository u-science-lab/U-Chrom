import { describe, expect, it } from 'vitest'
import { DEFAULT_SIDEBARS, parseSidebars, sidebarKey } from './sidebars'

describe('side bars', () => {
  it('parses the stored choice; junk opens both', () => {
    expect(parseSidebars({ left: false, right: true })).toEqual({ left: false, right: true })
    expect(parseSidebars({ left: 'no' })).toEqual(DEFAULT_SIDEBARS)
    expect(parseSidebars(null)).toEqual(DEFAULT_SIDEBARS)
  })
  it('Ctrl / Cmd + [ / ] toggle the left / right bar, not while typing', () => {
    const body = { tagName: 'BODY' } as unknown as EventTarget
    const input = { tagName: 'INPUT' } as unknown as EventTarget
    expect(sidebarKey({ key: '[', ctrlKey: true, metaKey: false, altKey: false, target: body })).toBe('left')
    expect(sidebarKey({ key: ']', ctrlKey: false, metaKey: true, altKey: false, target: body })).toBe('right')
    expect(sidebarKey({ key: '[', ctrlKey: false, metaKey: false, altKey: false, target: body })).toBeNull()
    expect(sidebarKey({ key: '[', ctrlKey: true, metaKey: false, altKey: false, target: input })).toBeNull()
  })
})

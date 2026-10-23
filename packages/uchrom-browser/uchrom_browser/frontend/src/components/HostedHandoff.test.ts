import { describe, expect, it } from 'vitest'
import { isCatalogResponseCurrent, isHandoffDialogEscape, trapHandoffDialogTab } from './HostedHandoff'

describe('hosted handoff dialog helpers', () => {
  it('ignores catalog responses from an older request or dataset', () => {
    expect(isCatalogResponseCurrent(2, 2, '/data/a.zarr', '/data/a.zarr')).toBe(true)
    expect(isCatalogResponseCurrent(1, 2, '/data/a.zarr', '/data/a.zarr')).toBe(false)
    expect(isCatalogResponseCurrent(2, 2, '/data/a.zarr', '/data/b.zarr')).toBe(false)
  })

  it('recognizes Escape as the modal close key', () => {
    expect(isHandoffDialogEscape('Escape')).toBe(true)
    expect(isHandoffDialogEscape('Enter')).toBe(false)
  })

  it('cycles Tab within the modal focusables', () => {
    const focused: string[] = []
    const close = { focus: () => focused.push('close') }
    const question = { focus: () => focused.push('question') }
    const done = { focus: () => focused.push('done') }
    let prevented = false
    expect(trapHandoffDialogTab({ key: 'Tab', shiftKey: false, preventDefault: () => { prevented = true } }, [close, question, done], done)).toBe(true)
    expect(prevented).toBe(true)
    expect(focused).toEqual(['close'])
    expect(trapHandoffDialogTab({ key: 'Tab', shiftKey: true, preventDefault: () => {} }, [close, question, done], close)).toBe(true)
    expect(focused).toEqual(['close', 'done'])
  })
})

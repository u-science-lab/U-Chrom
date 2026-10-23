import { describe, expect, it } from 'vitest'
import { handoffIssueMessage, isCatalogResponseCurrent, isHandoffDialogEscape, trapHandoffDialogTab } from './HostedHandoff'

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

  it('explains the UTF-8 limit and how to make an oversized prompt fit', () => {
    expect(handoffIssueMessage('state-too-large')).toMatch(/shrink the selection/i)
    expect(handoffIssueMessage('state-too-large')).toMatch(/nothing was truncated/i)
    expect(handoffIssueMessage('prompt-too-large')).toMatch(/1 MiB/i)
    expect(handoffIssueMessage('prompt-too-large')).toMatch(/shrink the selection/i)
    expect(handoffIssueMessage('invalid-dataset-url')).toMatch(/public HTTPS/i)
  })

  it('keeps the canonical ID opt-in control unchecked by default in the copy contract', () => {
    expect('Include canonical cell IDs').toMatch(/Include canonical cell IDs/)
  })
})

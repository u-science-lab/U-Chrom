import { describe, expect, it } from 'vitest'
import { handoffPrompt } from '../handoff'
import { DEFAULT_VIEW } from '../store'
import { defaultWorkspace } from '../workspace'
import { handoffIssueMessage, isCatalogResponseCurrent, isHandoffDialogEscape, trapHandoffDialogTab, hostedHandoffPayload } from './HostedHandoff'

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

  it('keeps canonical IDs summary-only by default, includes them when checked, and removes them when unchecked', () => {
    const view = { ...DEFAULT_VIEW, selection: { id: 'g1', cells: ['c1', 'c2'] } }
    const workspace = defaultWorkspace(false)

    const defaultPayload = hostedHandoffPayload(view, workspace)
    expect(defaultPayload.includeCellIds).toBe(false)
    expect(defaultPayload.state.selection).toEqual({ count: 2, source: 'lasso' })
    expect(handoffPrompt('https://atlas.example/data.zarr', '', defaultPayload.state)).not.toContain('"cells"')

    const optedInPayload = hostedHandoffPayload(view, workspace, true)
    expect(optedInPayload.includeCellIds).toBe(true)
    expect(optedInPayload.state.selection).toEqual({ count: 2, cells: ['c1', 'c2'], source: 'lasso' })
    expect(handoffPrompt('https://atlas.example/data.zarr', '', optedInPayload.state)).toContain('"cells": [')

    const optedOutPayload = hostedHandoffPayload(view, workspace, false)
    expect(optedOutPayload.includeCellIds).toBe(false)
    expect(optedOutPayload.state.selection).toEqual({ count: 2, source: 'lasso' })
    expect(handoffPrompt('https://atlas.example/data.zarr', '', optedOutPayload.state)).not.toContain('"cells"')
  })
})

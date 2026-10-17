import { describe, expect, it } from 'vitest'
import { initialPanel } from './OpenDialog'

describe('the panel the Open dialog shows first', () => {
  it('a hosted server, which cannot list its folders: always the atlas', () => {
    expect(initialPanel(true, null)).toBe('atlas')
    expect(initialPanel(true, 'files')).toBe('atlas')
  })
  it('a local server: the panel used last time, the folders the first time', () => {
    expect(initialPanel(false, null)).toBe('files')
    expect(initialPanel(false, 'atlas')).toBe('atlas')
    expect(initialPanel(false, 'files')).toBe('files')
  })
})

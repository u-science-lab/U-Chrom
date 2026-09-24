import { describe, expect, it } from 'vitest'
import { bundleOf, isStaleServer } from './serverBundle'

describe('server bundle check', () => {
  it('extracts the bundle name from a script URL', () => {
    expect(bundleOf('./assets/index-BBNzwumu.js')).toBe('index-BBNzwumu.js')
    expect(bundleOf('/assets/index-abc.js?v=1')).toBe('index-abc.js')
    expect(bundleOf('/src/main.tsx')).toBeNull()
    expect(bundleOf(null)).toBeNull()
  })
  it('flags only a known mismatch', () => {
    expect(isStaleServer('index-a.js', 'index-b.js')).toBe(true)
    expect(isStaleServer('index-a.js', 'index-a.js')).toBe(false)
    expect(isStaleServer(null, 'index-b.js')).toBe(false)   // dev server
    expect(isStaleServer('index-a.js', undefined)).toBe(false) // older server without the field
  })
})

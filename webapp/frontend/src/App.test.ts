import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const appSource = readFileSync(resolve(__dirname, 'App.tsx'), 'utf8')

describe('App layout', () => {
  it('does not render the global genomic chromosome footer', () => {
    expect(appSource).not.toContain('GenomicNavBar')
  })
})

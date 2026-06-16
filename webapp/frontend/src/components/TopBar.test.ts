import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const topBarSource = readFileSync(resolve(__dirname, 'TopBar.tsx'), 'utf8')

describe('TopBar branding', () => {
  it('shows only the U-Chrom brand name without the product subtitle', () => {
    expect(topBarSource).toContain('U-Chrom')
    expect(topBarSource).not.toContain('Data Portal')
  })
})

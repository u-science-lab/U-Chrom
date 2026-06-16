import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve(__dirname, 'Structure3DPanel.tsx'), 'utf8')

describe('Structure3DPanel analysis annotations', () => {
  it('requests annotated bins and carries annotations into BinInfo', () => {
    expect(source).toContain('sessionApiUrl')
    expect(source).toContain('annotations=true')
    expect(source).toContain('annotations?: Record<string, unknown>')
  })

  it('can color structure segments by projected analysis annotation fields', () => {
    expect(source).toContain('annotationColor')
    expect(source).toContain('structureColorBy')
    expect(source).toContain('function annotationKey')
    expect(source).toContain('annotationKey(s, structureColorBy)')
  })
})

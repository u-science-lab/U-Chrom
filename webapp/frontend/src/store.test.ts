import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const storeSource = readFileSync(resolve(__dirname, 'store.ts'), 'utf8')

describe('view hydration', () => {
  it('clears stale generated views when a conversation snapshot has no views', () => {
    expect(storeSource).toContain('if (views.length === 0)')
    expect(storeSource).toContain('activeGoslingSpec: null')
    expect(storeSource).toContain('goslingArtifacts: []')
    expect(storeSource).toContain('activeComponentTree: null')
  })
})

describe('protocol and analysis metadata state', () => {
  it('stores negotiated protocol and analysis result metadata', () => {
    expect(storeSource).toContain('protocol: null')
    expect(storeSource).toContain('setProtocol:')
    expect(storeSource).toContain('analysisResults: {}')
    expect(storeSource).toContain('setAnalysisResult:')
  })
})

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const wsSource = readFileSync(resolve(__dirname, 'ws.ts'), 'utf8')

describe('WSClient conversation id tracking', () => {
  it('updates the reconnect conversation id from conversation snapshots', () => {
    expect(wsSource).toContain("type === 'conversation.snapshot'")
    expect(wsSource).toContain('this.conversationId = id')
    expect(wsSource).toContain('localStorage.setItem(CONVERSATION_KEY, id)')
  })
})

describe('session-aware API helpers', () => {
  it('exports helpers that append the current session id to REST API URLs', () => {
    expect(wsSource).toContain('export function getSessionId()')
    expect(wsSource).toContain('export function sessionApiUrl(')
    expect(wsSource).toContain("url.searchParams.set('session_id', getSessionId())")
  })
})

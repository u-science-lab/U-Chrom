import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { buildChatMessagesFromSnapshot } from '../conversationHistory'

describe('conversation history hydration', () => {
  it('hydrates user assistant and tool rows from a conversation snapshot', () => {
    const messages = buildChatMessagesFromSnapshot([
      {
        id: 'm-user',
        role: 'user',
        content: 'load data',
        events: [],
      },
      {
        id: 'm-assistant',
        role: 'assistant',
        content: 'Loaded.',
        events: [
          {
            id: 'e-start',
            type: 'tool_call_start',
            payload: {
              tool_use_id: 'tool-1',
              tool_name: 'load_data',
            },
          },
          {
            id: 'e-result',
            type: 'tool_call_result',
            payload: {
              tool_use_id: 'tool-1',
              tool_name: 'load_data',
              status: 'ok',
              summary: 'Loaded example.h5cd',
            },
          },
        ],
      },
    ])

    expect(messages).toEqual([
      { id: 'm-user', role: 'user', content: 'load data' },
      { id: 'm-assistant', role: 'assistant', content: 'Loaded.' },
      {
        id: 'tool-tool-1',
        role: 'tool',
        toolUseId: 'tool-1',
        toolName: 'load_data',
        status: 'ok',
        summary: 'Loaded example.h5cd',
      },
    ])
  })
})

describe('ChatPanel conversation controls', () => {
  const source = readFileSync(resolve(__dirname, 'ChatPanel.tsx'), 'utf8')

  it('listens for snapshots and exposes load/new commands', () => {
    expect(source).toContain("ws.onMessage('conversation.snapshot'")
    expect(source).toContain("ws.onMessage('conversation.updated'")
    expect(source).toContain("ws.send('conversation.load'")
    expect(source).toContain("ws.send('conversation.new'")
  })
})

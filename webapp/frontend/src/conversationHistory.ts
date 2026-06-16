export type ChatMessage =
  | { id: string; role: 'user' | 'assistant'; content: string }
  | {
      id: string
      role: 'tool'
      toolUseId: string
      toolName: string
      status: 'loading' | 'ok' | 'error'
      summary?: string
    }

export interface ConversationEvent {
  id?: string
  type: string
  payload?: Record<string, unknown>
}

export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant'
  content?: string
  events?: ConversationEvent[]
}

export interface ConversationSummary {
  id: string
  title: string
  data_name?: string | null
  updated_at?: string
  message_count?: number
  last_message?: string
}

export function buildChatMessagesFromSnapshot(
  snapshotMessages: ConversationMessage[] = [],
): ChatMessage[] {
  const rows: ChatMessage[] = []
  const toolRows = new Map<string, Extract<ChatMessage, { role: 'tool' }>>()

  for (const message of snapshotMessages) {
    rows.push({
      id: message.id,
      role: message.role,
      content: message.content || '',
    })

    for (const event of message.events || []) {
      const payload = event.payload || {}
      const toolUseId = String(payload.tool_use_id || '')
      if (!toolUseId) continue
      const existing = toolRows.get(toolUseId)
      const toolName = String(payload.tool_name || existing?.toolName || 'tool')

      if (event.type === 'tool_call_start') {
        const row: Extract<ChatMessage, { role: 'tool' }> = {
          id: `tool-${toolUseId}`,
          role: 'tool',
          toolUseId,
          toolName,
          status: existing?.status || 'loading',
          summary: existing?.summary,
        }
        toolRows.set(toolUseId, row)
        if (!existing) rows.push(row)
      }

      if (event.type === 'tool_call_result') {
        const status = payload.status === 'error' ? 'error' : 'ok'
        const row: Extract<ChatMessage, { role: 'tool' }> = {
          id: `tool-${toolUseId}`,
          role: 'tool',
          toolUseId,
          toolName,
          status,
          summary: typeof payload.summary === 'string' ? payload.summary : undefined,
        }
        toolRows.set(toolUseId, row)
        const index = rows.findIndex(m => m.role === 'tool' && m.toolUseId === toolUseId)
        if (index >= 0) rows[index] = row
        else rows.push(row)
      }
    }
  }

  return rows
}

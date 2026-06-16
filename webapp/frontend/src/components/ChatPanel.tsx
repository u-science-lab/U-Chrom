import { useState, useEffect, useRef, useCallback } from 'react'
import { ws } from '../ws'
import { ARTIFACT_HANDLERS } from '../artifactHandlers'
import { useAppStore } from '../store'
import {
  buildChatMessagesFromSnapshot,
  type ChatMessage,
  type ConversationMessage,
  type ConversationSummary,
} from '../conversationHistory'

// A chat entry is either a text bubble (user / assistant) or a tool-call
// indicator that moves through three states: loading → ok / error (mirrors the
// Vercel AI SDK tool-part lifecycle input-available → output-available/-error).
export default function ChatPanel() {
  const [messages, setMessages] = useState<Array<ChatMessage>>([])
  const [input, setInput] = useState('')
  const [wsConnected, setWsConnected] = useState(false)
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string>('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Per-streaming-message scratch: message_id -> { index -> accumulated text }.
  // Deltas append to the block at `index`; the bubble content is the blocks
  // joined in index order. This keeps one stable bubble per message_id instead
  // of spawning a new bubble per delta.
  const streamingRef = useRef<Record<string, Record<number, string>>>({})

  const pushAssistant = useCallback((content: string) => {
    setMessages(prev => [...prev, {
      id: `${Date.now()}-${Math.random()}`,
      role: 'assistant',
      content,
    }])
  }, [])

  // Render the accumulated blocks for a streaming message into one string.
  const renderStreaming = useCallback((messageId: string): string => {
    const blocks = streamingRef.current[messageId] || {}
    return Object.keys(blocks)
      .map(Number)
      .sort((a, b) => a - b)
      .map(i => blocks[i])
      .join('')
  }, [])

  useEffect(() => {
    const offStatus = ws.onStatus(setWsConnected)

    const offConversationSnapshot = ws.onMessage('conversation.snapshot', (msg) => {
      const conversation = msg.conversation as { id?: string } | undefined
      const id = conversation?.id || ''
      setActiveConversationId(id)
      try {
        if (id) localStorage.setItem('uchrom_conversation_id', id)
      } catch { /* ignore */ }
      setConversations((msg.conversations as ConversationSummary[] | undefined) || [])
      setMessages(buildChatMessagesFromSnapshot(
        (msg.messages as ConversationMessage[] | undefined) || [],
      ))
      const views = msg.views as Array<{
        view_id: string; view_type: string; state: Record<string, unknown>; title?: string
      }> | undefined
      useAppStore.getState().hydrateViews(views || [])
    })

    const offConversationList = ws.onMessage('conversation.list', (msg) => {
      setConversations((msg.conversations as ConversationSummary[] | undefined) || [])
    })

    const offConversationUpdated = ws.onMessage('conversation.updated', (msg) => {
      setConversations((msg.conversations as ConversationSummary[] | undefined) || [])
    })

    // Streaming lifecycle: message_start creates an empty assistant bubble keyed
    // by message_id; agent_message_delta appends text in-place at its index;
    // message_stop finalizes (no further mutation expected).
    const offStart = ws.onMessage('message_start', (msg) => {
      const messageId = msg.message_id as string
      if (!messageId) return
      streamingRef.current[messageId] = {}
      setMessages(prev => {
        if (prev.some(m => m.id === messageId)) return prev
        return [...prev, { id: messageId, role: 'assistant', content: '' }]
      })
    })

    const offDelta = ws.onMessage('agent_message_delta', (msg) => {
      const messageId = msg.message_id as string | undefined
      const text = (msg.text as string) ?? ''
      // No message_id (legacy/degraded transport): fall back to a fresh bubble.
      if (!messageId) {
        if (text) pushAssistant(text)
        return
      }
      const index = (msg.index as number) ?? 0
      const blocks = streamingRef.current[messageId] || (streamingRef.current[messageId] = {})
      blocks[index] = (blocks[index] || '') + text
      const content = renderStreaming(messageId)
      setMessages(prev => {
        const exists = prev.some(m => m.id === messageId)
        if (!exists) {
          // Delta arrived before message_start (out-of-order): create the bubble.
          return [...prev, { id: messageId, role: 'assistant', content }]
        }
        return prev.map(m => m.id === messageId ? { ...m, content } : m)
      })
    })

    const offStop = ws.onMessage('message_stop', (msg) => {
      const messageId = msg.message_id as string | undefined
      if (messageId) delete streamingRef.current[messageId]
    })

    // Fallback: agent_message is only emitted on forced stop (>10 tool rounds).
    const offText = ws.onMessage('agent_message', (msg) => {
      pushAssistant((msg.text as string) || (msg.content as string) || '')
    })

    const offArtifact = ws.onMessage('agent_artifact', (msg) => {
      const handler = ARTIFACT_HANDLERS[msg.artifact_type as string]
      if (handler) {
        handler(msg, { pushAssistant })
      }
    })

    // Plain text artifacts (e.g. "Data loaded", analysis results)
    const offTextArtifact = ws.onMessage('artifact', (msg) => {
      if (msg.artifact_type === 'text' && msg.content) {
        pushAssistant(msg.content as string)
      }
    })

    // Backend view-state snapshot (after a resumed reconnect) — rebuild views.
    const offSnapshot = ws.onMessage('view.snapshot', (msg) => {
      const views = msg.views as Array<{
        view_id: string; view_type: string; state: Record<string, unknown>; title?: string
      }> | undefined
      if (views && views.length) useAppStore.getState().hydrateViews(views)
    })

    // Agent is blocking in query_user_interaction(wait=true): remember the
    // interaction_id so any view's next ui_event echoes it back (precise resolve),
    // and surface a hint so the user knows to act (e.g. pick a spot in 3D).
    const offAwait = ws.onMessage('await_interaction', (msg) => {
      const id = (msg.interaction_id as string) || null
      useAppStore.getState().setPendingInteractionId(id)
      if (id) pushAssistant('[Waiting for you to interact — brush a region, or click a spot in the 3D Structure view…]')
    })
    const offAwaitDone = ws.onMessage('await_interaction_done', () => {
      useAppStore.getState().setPendingInteractionId(null)
    })

    // Tool-call lifecycle (Vercel AI SDK tool-part states). tool_call_start adds
    // a "⚙️ 正在调用 {tool}…" loading row keyed by tool_use_id; tool_call_result
    // settles it to ✓ done or ✗ error (with an optional one-line summary).
    const offToolStart = ws.onMessage('tool_call_start', (msg) => {
      const toolUseId = msg.tool_use_id as string | undefined
      if (!toolUseId) return
      const toolName = (msg.tool_name as string) || 'tool'
      setMessages(prev => {
        if (prev.some(m => m.role === 'tool' && m.toolUseId === toolUseId)) return prev
        return [...prev, {
          id: `tool-${toolUseId}`,
          role: 'tool',
          toolUseId,
          toolName,
          status: 'loading',
        }]
      })
    })

    const offToolResult = ws.onMessage('tool_call_result', (msg) => {
      const toolUseId = msg.tool_use_id as string | undefined
      if (!toolUseId) return
      const status = (msg.status as string) === 'error' ? 'error' : 'ok'
      const summary = (msg.summary as string) || undefined
      const toolName = (msg.tool_name as string) || undefined
      setMessages(prev => {
        const exists = prev.some(m => m.role === 'tool' && m.toolUseId === toolUseId)
        if (!exists) {
          // Result without a start (out-of-order/missed): synthesize a settled row.
          return [...prev, {
            id: `tool-${toolUseId}`,
            role: 'tool',
            toolUseId,
            toolName: toolName || 'tool',
            status,
            summary,
          }]
        }
        return prev.map(m =>
          m.role === 'tool' && m.toolUseId === toolUseId
            ? { ...m, status, summary, toolName: toolName || m.toolName }
            : m
        )
      })
    })

    return () => {
      offStatus(); offConversationSnapshot(); offConversationList(); offConversationUpdated()
      offStart(); offDelta(); offStop()
      offText(); offArtifact(); offTextArtifact(); offSnapshot()
      offAwait(); offAwaitDone(); offToolStart(); offToolResult()
    }
  }, [pushAssistant, renderStreaming])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    if (!input.trim() || !ws.connected) return
    setMessages(prev => [...prev, { id: `${Date.now()}-${Math.random()}`, role: 'user', content: input }])
    ws.send('user_message', { text: input })
    setInput('')
  }

  const handleLoadConversation = (id: string) => {
    if (!id || id === activeConversationId || !ws.connected) return
    ws.send('conversation.load', { conversation_id: id })
  }

  const handleNewConversation = () => {
    if (!ws.connected) return
    setMessages([])
    ws.send('conversation.new', {})
  }

  return (
    <div className="h-full flex flex-col bg-bg-primary">
      <div className="px-4 py-2 border-b border-border-primary bg-bg-secondary flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-accent-green' : 'bg-gray-300'}`} />
        <span className="text-xs text-text-secondary">{wsConnected ? 'Connected' : 'Disconnected'}</span>
        <div className="ml-auto flex items-center gap-2 min-w-0">
          <select
            value={activeConversationId}
            onChange={(e) => handleLoadConversation(e.target.value)}
            disabled={!wsConnected}
            className="max-w-[180px] px-2 py-1 text-xs border border-border-primary rounded bg-bg-primary text-text-primary disabled:opacity-50"
            title="Conversation history"
          >
            {activeConversationId && !conversations.some(c => c.id === activeConversationId) && (
              <option value={activeConversationId}>Current</option>
            )}
            {conversations.length === 0 && <option value="">No history</option>}
            {conversations.map(conversation => (
              <option key={conversation.id} value={conversation.id}>
                {conversation.title || conversation.data_name || 'Conversation'}
              </option>
            ))}
          </select>
          <button
            onClick={handleNewConversation}
            disabled={!wsConnected}
            className="px-2 py-1 text-xs border border-border-primary rounded text-text-secondary hover:text-text-primary disabled:opacity-50"
            title="New conversation"
          >
            New
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg) => {
          if (msg.role === 'tool') {
            // Tool-call indicator row: loading / ok / error.
            const icon = msg.status === 'loading' ? '⚙️' : msg.status === 'ok' ? '✓' : '✗'
            const label =
              msg.status === 'loading'
                ? `正在调用 ${msg.toolName}…`
                : msg.status === 'ok'
                ? `${msg.toolName} 完成`
                : `${msg.toolName} 失败`
            const tone =
              msg.status === 'loading'
                ? 'text-text-secondary'
                : msg.status === 'ok'
                ? 'text-accent-green'
                : 'text-red-500'
            return (
              <div key={msg.id} className="flex justify-start">
                <div className="max-w-[85%] px-3 py-1.5 rounded-lg text-xs bg-bg-secondary border border-border-primary">
                  <div className={`flex items-center gap-1.5 font-mono ${tone}`}>
                    <span className={msg.status === 'loading' ? 'animate-pulse' : ''}>{icon}</span>
                    <span>{label}</span>
                  </div>
                  {msg.summary && (
                    <div className="mt-1 text-text-secondary whitespace-pre-wrap break-words">{msg.summary}</div>
                  )}
                </div>
              </div>
            )
          }
          return (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] px-3 py-2 rounded-lg text-sm ${
                msg.role === 'user' ? 'bg-accent-blue text-white' : 'bg-bg-tertiary text-text-primary'
              }`}>
                {msg.content}
              </div>
            </div>
          )
        })}
        <div ref={messagesEndRef} />
      </div>

      <div className="px-4 py-3 border-t border-border-primary">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
            placeholder="Ask to visualize genomic data..."
            rows={2}
            className="flex-1 px-3 py-2 text-sm border border-border-primary rounded resize-none focus:outline-none focus:ring-2 focus:ring-accent-blue"
          />
          <button
            onClick={handleSend}
            disabled={!wsConnected || !input.trim()}
            className="px-4 py-2 bg-accent-blue text-white text-sm rounded hover:bg-blue-600 disabled:opacity-50 transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}

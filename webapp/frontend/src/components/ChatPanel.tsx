import { useState, useEffect, useRef, useCallback } from 'react'
import { ws } from '../ws'
import { ARTIFACT_HANDLERS } from '../artifactHandlers'
import { useAppStore } from '../store'

export default function ChatPanel() {
  const [messages, setMessages] = useState<Array<{ id: string; role: 'user' | 'assistant'; content: string }>>([])
  const [input, setInput] = useState('')
  const [wsConnected, setWsConnected] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const pushAssistant = useCallback((content: string) => {
    setMessages(prev => [...prev, {
      id: `${Date.now()}-${Math.random()}`,
      role: 'assistant',
      content,
    }])
  }, [])

  useEffect(() => {
    const offStatus = ws.onStatus(setWsConnected)

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

    return () => { offStatus(); offText(); offArtifact(); offTextArtifact(); offSnapshot() }
  }, [pushAssistant])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    if (!input.trim() || !ws.connected) return
    setMessages(prev => [...prev, { id: `${Date.now()}-${Math.random()}`, role: 'user', content: input }])
    ws.send('user_message', { text: input })
    setInput('')
  }

  return (
    <div className="h-full flex flex-col bg-bg-primary">
      <div className="px-4 py-2 border-b border-border-primary bg-bg-secondary flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-accent-green' : 'bg-gray-300'}`} />
        <span className="text-xs text-text-secondary">{wsConnected ? 'Connected' : 'Disconnected'}</span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] px-3 py-2 rounded-lg text-sm ${
              msg.role === 'user' ? 'bg-accent-blue text-white' : 'bg-bg-tertiary text-text-primary'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
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

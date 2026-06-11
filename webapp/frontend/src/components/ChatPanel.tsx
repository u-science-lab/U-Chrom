import { useState, useEffect, useRef } from 'react'
import { useAppStore, type GoslingArtifact } from '../store'
import { ws } from '../ws'

export default function ChatPanel() {
  const [messages, setMessages] = useState<Array<{ id: string; role: 'user' | 'assistant'; content: string }>>([])
  const [input, setInput] = useState('')
  const [wsConnected, setWsConnected] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { addGoslingArtifact, applyGoslingPatch, setActiveGoslingSpec } = useAppStore()

  useEffect(() => {
    const offStatus = ws.onStatus(setWsConnected)

    const offText = ws.onMessage('agent_message', (msg) => {
      setMessages(prev => [...prev, {
        id: `${Date.now()}-${Math.random()}`,
        role: 'assistant',
        content: (msg.text as string) || (msg.content as string) || '',
      }])
    })

    const offArtifact = ws.onMessage('agent_artifact', (msg) => {
      if (msg.artifact_type === 'gosling_spec' && msg.spec) {
        const artifact: GoslingArtifact = {
          id: (msg.artifact_id as string) || `viz_${Date.now()}`,
          title: (msg.title as string) || 'Genomic Visualization',
          spec: msg.spec as object,
          createdAt: Date.now(),
          active: false,
        }
        addGoslingArtifact(artifact)
        setActiveGoslingSpec(artifact.spec, artifact.id)
        setMessages(prev => [...prev, {
          id: `${Date.now()}-${Math.random()}`,
          role: 'assistant',
          content: `[Visualization: ${artifact.title}]`,
        }])
      } else if (msg.artifact_type === 'gosling_patch' && msg.target_id && msg.patch) {
        applyGoslingPatch(msg.target_id as string, msg.patch as { op: string; path: string; value: unknown })
      } else if (msg.artifact_type === 'select_cells') {
        // Agent-driven cell selection → cross-panel highlight
        const ids = (msg.cell_ids as string[]) || []
        useAppStore.getState().highlightCells(ids)
        useAppStore.getState().setActiveTab('embedding')
        setMessages(prev => [...prev, {
          id: `${Date.now()}-${Math.random()}`,
          role: 'assistant',
          content: `[Selected ${ids.length} cell(s)]`,
        }])
      } else if (msg.artifact_type === 'color_embedding') {
        useAppStore.getState().setActiveTab('embedding')
        setMessages(prev => [...prev, {
          id: `${Date.now()}-${Math.random()}`,
          role: 'assistant',
          content: `[Colored embedding by ${msg.color_by as string}]`,
        }])
      } else if (msg.artifact_type === 'show_structure') {
        const cellId = msg.cell_id as string
        if (cellId) useAppStore.getState().highlightCells([cellId])
        useAppStore.getState().setActiveTab('structure3d')
        setMessages(prev => [...prev, {
          id: `${Date.now()}-${Math.random()}`,
          role: 'assistant',
          content: `[Showing 3D structure for ${cellId}]`,
        }])
      } else if (msg.artifact_type === 'color_structure') {
        useAppStore.getState().setActiveTab('structure3d')
        setMessages(prev => [...prev, {
          id: `${Date.now()}-${Math.random()}`,
          role: 'assistant',
          content: `[Colored 3D structure by ${msg.color_by as string}]`,
        }])
      } else if (msg.artifact_type === 'export_view') {
        const fmt = (msg.format as 'png' | 'pdf') || 'png'
        useAppStore.getState().requestExport(fmt)
        setMessages(prev => [...prev, {
          id: `${Date.now()}-${Math.random()}`,
          role: 'assistant',
          content: `[Exporting current view as ${fmt.toUpperCase()}]`,
        }])
      } else if (msg.artifact_type === 'analysis_result') {
        // Bump dataVersion so panels re-fetch derived data (TAD/loop/compartment)
        useAppStore.getState().bumpDataVersion()
        const at = msg.analysis_type as string
        const chrom = msg.chrom as string
        setMessages(prev => [...prev, {
          id: `${Date.now()}-${Math.random()}`,
          role: 'assistant',
          content: `[${at} analysis complete on ${chrom}]`,
        }])
      }
    })

    // Plain text artifacts (e.g. "Data loaded", analysis results)
    const offTextArtifact = ws.onMessage('artifact', (msg) => {
      if (msg.artifact_type === 'text' && msg.content) {
        setMessages(prev => [...prev, {
          id: `${Date.now()}-${Math.random()}`,
          role: 'assistant',
          content: msg.content as string,
        }])
      }
    })

    return () => { offStatus(); offText(); offArtifact(); offTextArtifact() }
  }, [addGoslingArtifact, applyGoslingPatch, setActiveGoslingSpec])

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

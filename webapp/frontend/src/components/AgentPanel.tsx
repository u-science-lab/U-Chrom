import { useEffect, useRef, useState } from 'react'
import { ws } from '../ws'
import { useAppStore, PanelType } from '../store'
import FigurePreview from './FigurePreview'

interface Message {
  role: 'user' | 'agent'
  text: string
  isError?: boolean
  figure?: { preview: string; path: string; format: string; params?: any }
}

export default function AgentPanel() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const setViewport = useAppStore(s => s.setViewport)
  const setCellSelection = useAppStore(s => s.setCellSelection)
  const addPanel = useAppStore(s => s.addPanel)
  const setHighlightRegions = useAppStore(s => s.setHighlightRegions)
  const setColormapConfig = useAppStore(s => s.setColormapConfig)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const offToken = ws.onMessage('agent_token', (p: any) => {
      if (p.token) {
        setMessages(prev => {
          const last = prev[prev.length - 1]
          if (last?.role === 'agent' && !last.isError) {
            return [...prev.slice(0, -1), { role: 'agent', text: last.text + p.token }]
          }
          return [...prev, { role: 'agent', text: p.token }]
        })
      }
      if (p.done) setStreaming(false)
    })
    const offVp = ws.onMessage('agent_viewport_update', (p: any) => {
      setViewport({ chrom: p.chrom, start: p.start, end: p.end })
    })
    const offCells = ws.onMessage('agent_cell_selection', (p: any) => {
      setCellSelection({ mode: p.mode ?? 'cell_type', ids: p.ids ?? [], label: p.label ?? '' })
    })
    const offHighlight = ws.onMessage('agent_highlight_region', (p: any) => {
      const regions = p.regions || [p]  // Support both single region and array
      setHighlightRegions(regions)
      setMessages(prev => [...prev, {
        role: 'agent', text: `Highlighted ${regions.length} region(s)`
      }])
    })
    const offColormap = ws.onMessage('agent_set_colormap', (p: any) => {
      setColormapConfig(p)
      setMessages(prev => [...prev, {
        role: 'agent', text: `Changed colormap to ${p.scheme}`
      }])
    })
    const offArt = ws.onMessage('agent_artifact', (p: any) => {
      const { artifact_type, payload } = p
      if (artifact_type === 'add_panel' && payload?.type) {
        addPanel(payload.type as PanelType)
        setMessages(prev => [...prev, {
          role: 'agent', text: `Added panel: ${payload.label ?? payload.type}`
        }])
      } else if (artifact_type === 'text_block') {
        setMessages(prev => [...prev, {
          role: 'agent', text: payload?.content ?? '',
          isError: payload?.format === 'error'
        }])
      } else if (artifact_type === 'highlight_region') {
        // Handle highlight_region artifact from Python code
        const regions = payload?.regions || []
        setHighlightRegions(regions)
        setMessages(prev => [...prev, {
          role: 'agent', text: `Highlighted ${regions.length} region(s)`
        }])
      } else if (artifact_type === 'set_colormap') {
        // Handle set_colormap artifact from Python code
        setColormapConfig(payload)
        setMessages(prev => [...prev, {
          role: 'agent', text: `Changed colormap to ${payload?.scheme ?? 'default'}`
        }])
      } else if (artifact_type === 'figure') {
        // Handle figure export
        setMessages(prev => [...prev, {
          role: 'agent',
          text: `Generated figure: ${payload?.path?.split('/').pop() ?? 'figure.pdf'}`,
          figure: {
            preview: payload?.preview ?? '',
            path: payload?.path ?? '',
            format: payload?.format ?? 'pdf',
            params: payload?.params,
          }
        }])
      } else if (artifact_type === 'data') {
        // Handle structured data
        console.log('Data artifact:', payload)
        setMessages(prev => [...prev, {
          role: 'agent', text: `Analysis complete: ${payload?.type ?? 'data'}`
        }])
      }
    })
    return () => { offToken(); offVp(); offCells(); offHighlight(); offColormap(); offArt() }
  }, [setViewport, setCellSelection, addPanel, setHighlightRegions, setColormapConfig])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  function send() {
    const text = input.trim()
    if (!text || streaming) return
    setMessages(prev => [...prev, { role: 'user', text }])
    setStreaming(true)
    setInput('')
    ws.send('agent_message', { session_id: 'main', text })
  }

  async function captureAndAnalyze() {
    if (streaming || capturing) return
    setCapturing(true)
    try {
      // Find MainCanvas element
      const canvas = document.querySelector('canvas')
      if (!canvas) {
        setMessages(prev => [...prev, { role: 'agent', text: 'No canvas found to capture', isError: true }])
        return
      }

      // Capture canvas as base64
      const dataUrl = canvas.toDataURL('image/png')
      const base64 = dataUrl.split(',')[1]

      setMessages(prev => [...prev, { role: 'user', text: '📸 Analyze current view' }])
      setStreaming(true)

      // Send multimodal query
      ws.send('multimodal_query', {
        session_id: 'main',
        image: base64,
        prompt: 'Analyze this 3D chromatin structure visualization. Identify any notable patterns, anomalies, or regions of interest. Suggest next steps for exploration.'
      })
    } catch (error) {
      setMessages(prev => [...prev, { role: 'agent', text: `Screenshot error: ${error}`, isError: true }])
    } finally {
      setCapturing(false)
    }
  }

  return (
    <div style={{ width: 320, flexShrink: 0, display: 'flex', flexDirection: 'column',
                  background: '#1e1e2e', borderLeft: '1px solid #313244', height: '100%' }}>
      <div style={{ padding: '8px 12px', borderBottom: '1px solid #313244',
                    color: '#cdd6f4', fontSize: 13, fontWeight: 600 }}>Agent</div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '90%' }}>
            <div style={{
              background: m.role === 'user' ? '#45475a' : m.isError ? '#3d1a1a' : '#313244',
              color: m.isError ? '#f38ba8' : '#cdd6f4',
              borderRadius: 8, padding: '6px 10px',
              fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>{m.text}</div>
            {m.figure && (
              <FigurePreview
                preview={m.figure.preview}
                path={m.figure.path}
                format={m.figure.format}
                params={m.figure.params}
              />
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div style={{ display: 'flex', borderTop: '1px solid #313244', padding: 6, gap: 6 }}>
        <button onClick={captureAndAnalyze} disabled={streaming || capturing}
          title="Capture canvas and ask AI to analyze"
          style={{ background: (streaming || capturing) ? '#45475a' : '#f9e2af', border: 'none',
                   borderRadius: 6, padding: '6px 10px', color: '#1e1e2e',
                   fontSize: 12, cursor: (streaming || capturing) ? 'default' : 'pointer' }}>
          {capturing ? '⏳' : '📸'}
        </button>
        <input value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
          placeholder="Ask about the data..."
          style={{ flex: 1, background: '#313244', border: 'none', borderRadius: 6,
                   padding: '6px 8px', color: '#cdd6f4', fontSize: 12, outline: 'none' }} />
        <button onClick={send} disabled={streaming}
          style={{ background: streaming ? '#45475a' : '#89b4fa', border: 'none',
                   borderRadius: 6, padding: '6px 10px', color: '#1e1e2e',
                   fontSize: 12, cursor: streaming ? 'default' : 'pointer' }}>
          {streaming ? '…' : '↵'}
        </button>
      </div>
    </div>
  )
}


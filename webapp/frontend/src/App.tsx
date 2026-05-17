import React, { useRef, useState } from 'react'
import DataTree from './components/DataTree'
import MainCanvas from './components/MainCanvas'
import AgentPanel from './components/AgentPanel'
import GenomicNavBar from './components/GenomicNavBar'
import FigureComposer from './components/FigureComposer'
import { useAppStore } from './store'

const s: Record<string, React.CSSProperties> = {
  root: { display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'sans-serif' },
  topBar: { height: 40, background: '#1e1e2e', color: '#cdd6f4', display: 'flex', alignItems: 'center', padding: '0 12px', flexShrink: 0, gap: 8 },
  middle: { display: 'flex', flex: 1, overflow: 'hidden' },
  btn: { background: '#89b4fa', color: '#1e1e2e', border: 'none', borderRadius: 4, padding: '4px 10px', cursor: 'pointer', fontWeight: 600, fontSize: 12 },
  btnSm: { background: '#313244', color: '#cdd6f4', border: '1px solid #45475a', borderRadius: 4, padding: '4px 8px', cursor: 'pointer', fontSize: 12 },
}

export default function App() {
  const [showComposer, setShowComposer] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const { viewport, cellSelection, panels, setViewport, setCellSelection } = useAppStore()

  function saveSession() {
    const state = { version: 1, viewport, cellSelection, panels, timestamp: Date.now() }
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `uchrom-session-${new Date().toISOString().slice(0,10)}.uchromfig`
    a.click()
  }

  function loadSession(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const state = JSON.parse(ev.target?.result as string)
        if (state.viewport) setViewport(state.viewport)
        if (state.cellSelection) setCellSelection(state.cellSelection)
        // panels restore requires addPanel — handled via store reset
        if (state.panels) useAppStore.setState({ panels: state.panels })
      } catch { /* ignore malformed */ }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  return (
    <div style={s.root}>
      <div style={s.topBar}>
        <span style={{ fontWeight: 700, marginRight: 4 }}>U-Chrom</span>
        <button style={s.btn} onClick={() => setShowComposer(true)}>Figure Composer</button>
        <button style={s.btnSm} onClick={saveSession}>Save Session</button>
        <button style={s.btnSm} onClick={() => fileRef.current?.click()}>Load Session</button>
        <input ref={fileRef} type="file" accept=".uchromfig,.json" style={{ display: 'none' }} onChange={loadSession} />
      </div>
      <div style={s.middle}>
        <DataTree />
        <MainCanvas />
        <AgentPanel />
      </div>
      <GenomicNavBar />
      {showComposer && <FigureComposer onClose={() => setShowComposer(false)} />}
    </div>
  )
}

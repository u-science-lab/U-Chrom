import React, { useState } from 'react'
import DataTree from './components/DataTree'
import MainCanvas from './components/MainCanvas'
import AgentPanel from './components/AgentPanel'
import GenomicNavBar from './components/GenomicNavBar'
import FigureComposer from './components/FigureComposer'

const s: Record<string, React.CSSProperties> = {
  root: { display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'sans-serif' },
  topBar: { height: 40, background: '#1e1e2e', color: '#cdd6f4', display: 'flex', alignItems: 'center', padding: '0 12px', flexShrink: 0, gap: 12 },
  middle: { display: 'flex', flex: 1, overflow: 'hidden' },
  bottomBar: { height: 36, background: '#1e1e2e', color: '#cdd6f4', flexShrink: 0 },
  btn: { background: '#89b4fa', color: '#1e1e2e', border: 'none', borderRadius: 4, padding: '4px 10px', cursor: 'pointer', fontWeight: 600, fontSize: 13 },
}

export default function App() {
  const [showComposer, setShowComposer] = useState(false)
  return (
    <div style={s.root}>
      <div style={s.topBar}>
        <span>TopMenuBar</span>
        <button style={s.btn} onClick={() => setShowComposer(true)}>Figure Composer</button>
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

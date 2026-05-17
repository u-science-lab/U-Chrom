import React from 'react'
import DataTree from './components/DataTree'
import MainCanvas from './components/MainCanvas'
import AgentPanel from './components/AgentPanel'
import GenomicNavBar from './components/GenomicNavBar'

const s: Record<string, React.CSSProperties> = {
  root: { display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'sans-serif' },
  topBar: { height: 40, background: '#1e1e2e', color: '#cdd6f4', display: 'flex', alignItems: 'center', padding: '0 12px', flexShrink: 0 },
  middle: { display: 'flex', flex: 1, overflow: 'hidden' },
  bottomBar: { height: 36, background: '#1e1e2e', color: '#cdd6f4', flexShrink: 0 },
}

export default function App() {
  return (
    <div style={s.root}>
      <div style={s.topBar}>TopMenuBar</div>
      <div style={s.middle}>
        <DataTree />
        <MainCanvas />
        <AgentPanel />
      </div>
      <GenomicNavBar />
    </div>
  )
}

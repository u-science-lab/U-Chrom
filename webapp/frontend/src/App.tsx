/*
 * Manual Testing Guide for Share Link Feature:
 *
 * 1. Start the frontend: cd webapp/frontend && npm start
 * 2. In the browser, adjust the viewer state:
 *    - Change genomic viewport (navigate to different region)
 *    - Select cells (via DataTree or cell type filter)
 *    - Add/remove panels (right-click MainCanvas, add Structure3D/IGV Browser/etc.)
 * 3. Click the "Share" button in the top bar
 *    - Button text should change to "Copied!" for 2 seconds
 * 4. Open a new browser tab/window and paste the URL
 *    - Verify viewport matches (genomic region)
 *    - Verify cell selection matches (selected cells/filter)
 *    - Verify panels match (same panel layout and types)
 * 5. Edge cases:
 *    - Load a share link with no hash → should show default state
 *    - Load a share link with malformed hash → should show default state + console warning
 *    - Share link after loading a session file → should encode current state
 */

import React, { useEffect, useRef, useState } from 'react'
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
  const [copied, setCopied] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const { viewport, cellSelection, panels, setViewport, setCellSelection } = useAppStore()

  // Restore state from URL hash on mount
  useEffect(() => {
    const hash = window.location.hash.slice(1)
    if (!hash) return
    try {
      const state = JSON.parse(decodeURIComponent(hash))
      if (state.viewport) setViewport(state.viewport)
      if (state.cellSelection) setCellSelection(state.cellSelection)
      if (state.panels && Array.isArray(state.panels)) {
        useAppStore.setState({ panels: state.panels })
      }
    } catch {
      console.warn('Failed to parse state from URL hash')
    }
  }, [setViewport, setCellSelection])

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
        if (state.panels) useAppStore.setState({ panels: state.panels })
      } catch { /* ignore malformed */ }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  function shareLink() {
    const state = { viewport, cellSelection, panels }
    const encoded = encodeURIComponent(JSON.stringify(state))
    const url = `${window.location.origin}${window.location.pathname}#${encoded}`
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div style={s.root}>
      <div style={s.topBar}>
        <span style={{ fontWeight: 700, marginRight: 4 }}>U-Chrom</span>
        <button style={s.btn} onClick={() => setShowComposer(true)}>Figure Composer</button>
        <button style={s.btnSm} onClick={saveSession}>Save Session</button>
        <button style={s.btnSm} onClick={() => fileRef.current?.click()}>Load Session</button>
        <button style={s.btnSm} onClick={shareLink}>{copied ? 'Copied!' : 'Share'}</button>
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

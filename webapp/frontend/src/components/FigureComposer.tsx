import React, { useState } from 'react'

interface Panel { id: number; type: string; label: string }
interface Style {
  sizePreset: string
  fontSize: number
  colormap: string
  colorbarMin: number
  colorbarMax: number
}

const SIZE_PRESETS = ['Nature 单栏 89mm', 'Nature 双栏 183mm', 'Science 双栏 174mm']
const COLORMAPS = ['RdBu', 'Blues', 'Reds', 'Viridis']

const s: Record<string, React.CSSProperties> = {
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 },
  modal: { background: '#1e1e2e', color: '#cdd6f4', width: '90vw', height: '85vh', display: 'flex', flexDirection: 'column', borderRadius: 8, overflow: 'hidden' },
  header: { padding: '8px 16px', background: '#181825', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 },
  body: { display: 'flex', flex: 1, overflow: 'hidden' },
  canvas: { flex: '0 0 70%', padding: 16, overflowY: 'auto', borderRight: '1px solid #313244' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 },
  slot: { background: '#313244', borderRadius: 6, padding: 12, minHeight: 120, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', position: 'relative' },
  removeBtn: { position: 'absolute', top: 4, right: 6, background: 'none', border: 'none', color: '#f38ba8', cursor: 'pointer', fontSize: 16 },
  sidebar: { flex: '0 0 30%', padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16 },
  label: { fontSize: 12, color: '#a6adc8', marginBottom: 4, display: 'block' },
  input: { background: '#313244', border: '1px solid #45475a', color: '#cdd6f4', borderRadius: 4, padding: '4px 8px', width: '100%', boxSizing: 'border-box' as const },
  row: { display: 'flex', gap: 8 },
  btn: { background: '#89b4fa', color: '#1e1e2e', border: 'none', borderRadius: 4, padding: '6px 12px', cursor: 'pointer', fontWeight: 600 },
  btnSm: { background: '#313244', color: '#cdd6f4', border: '1px solid #45475a', borderRadius: 4, padding: '4px 10px', cursor: 'pointer' },
}

let nextId = 5

export default function FigureComposer({ onClose }: { onClose: () => void }) {
  const [panels, setPanels] = useState<Panel[]>([
    { id: 1, type: '', label: 'Panel A' },
    { id: 2, type: '', label: 'Panel B' },
    { id: 3, type: '', label: 'Panel C' },
    { id: 4, type: '', label: 'Panel D' },
  ])
  const [style, setStyle] = useState<Style>({
    sizePreset: SIZE_PRESETS[0],
    fontSize: 7,
    colormap: 'RdBu',
    colorbarMin: 0,
    colorbarMax: 1,
  })

  function addPanel() {
    setPanels(p => [...p, { id: nextId++, type: '', label: `Panel ${String.fromCharCode(64 + nextId - 1)}` }])
  }

  function removePanel(id: number) {
    setPanels(p => p.filter(x => x.id !== id))
  }

  async function exportSVG() {
    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ figure_state: { panels, style }, format: 'svg' }),
    })
    if (!res.ok) return
    const { url } = await res.json()
    const a = document.createElement('a')
    a.href = url
    a.download = 'figure.svg'
    a.click()
  }

  function saveFig() {
    const blob = new Blob([JSON.stringify({ panels, style }, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'figure.uchromfig'
    a.click()
  }

  return (
    <div style={s.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={s.modal}>
        <div style={s.header}>
          <span style={{ fontWeight: 600 }}>Figure Composer</span>
          <div style={s.row}>
            <button style={s.btnSm} onClick={addPanel}>Add Panel</button>
            <button style={s.btn} onClick={exportSVG}>Export SVG</button>
            <button style={s.btnSm} onClick={saveFig}>Save .uchromfig</button>
            <button style={{ ...s.btnSm, marginLeft: 8 }} onClick={onClose}>✕</button>
          </div>
        </div>
        <div style={s.body}>
          <div style={s.canvas}>
            <div style={s.grid}>
              {panels.map(p => (
                <div key={p.id} style={s.slot}>
                  <button style={s.removeBtn} onClick={() => removePanel(p.id)}>✕</button>
                  <span style={{ color: '#6c7086', fontSize: 13 }}>{p.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div style={s.sidebar}>
            <div>
              <span style={s.label}>Size Preset</span>
              {SIZE_PRESETS.map(p => (
                <label key={p} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, fontSize: 13 }}>
                  <input type="radio" name="sizePreset" value={p} checked={style.sizePreset === p}
                    onChange={() => setStyle(s => ({ ...s, sizePreset: p }))} />
                  {p}
                </label>
              ))}
            </div>
            <div>
              <span style={s.label}>Font Size</span>
              <input style={s.input} type="number" value={style.fontSize}
                onChange={e => setStyle(s => ({ ...s, fontSize: +e.target.value }))} />
            </div>
            <div>
              <span style={s.label}>Colormap</span>
              <select style={s.input} value={style.colormap}
                onChange={e => setStyle(s => ({ ...s, colormap: e.target.value }))}>
                {COLORMAPS.map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <span style={s.label}>Colorbar Range</span>
              <div style={s.row}>
                <input style={s.input} type="number" placeholder="min" value={style.colorbarMin}
                  onChange={e => setStyle(s => ({ ...s, colorbarMin: +e.target.value }))} />
                <input style={s.input} type="number" placeholder="max" value={style.colorbarMax}
                  onChange={e => setStyle(s => ({ ...s, colorbarMax: +e.target.value }))} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

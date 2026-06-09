import { useState } from 'react'
import { Rnd } from 'react-rnd'
import { useAppStore } from '../store'

interface FigPanel { id: string; label: string; x: number; y: number; w: number; h: number }
interface Style { sizePreset: string; fontSize: number; colormap: string; vmin: number; vmax: number }

const PRESETS: Record<string, { w: number; h: number; label: string }> = {
  'nature-single': { w: 336, h: 280, label: 'Nature 单栏 89mm' },
  'nature-double': { w: 692, h: 460, label: 'Nature 双栏 183mm' },
  'science-double': { w: 658, h: 440, label: 'Science 双栏 174mm' },
}
const COLORMAPS = ['RdBu', 'Blues', 'Reds', 'Viridis']

let _id = 0
function uid() { return `fp${++_id}` }

export default function FigureComposer({ onClose }: { onClose: () => void }) {
  const storePanels = useAppStore(s => s.panels)
  const [preset, setPreset] = useState('nature-double')
  const [style, setStyle] = useState<Style>({ sizePreset: preset, fontSize: 7, colormap: 'RdBu', vmin: -2, vmax: 2 })
  const [panels, setPanels] = useState<FigPanel[]>(() =>
    storePanels.map((p, i) => ({
      id: uid(), label: p.label,
      x: (i % 2) * 340 + 8, y: Math.floor(i / 2) * 200 + 8, w: 320, h: 180,
    }))
  )

  const canvas = PRESETS[preset]

  function addPanel() {
    setPanels(p => [...p, { id: uid(), label: 'New Panel', x: 8, y: 8, w: 200, h: 150 }])
  }

  async function exportSvg() {
    // Build panels with image captures
    const panelsWithImages = await Promise.all(
      panels.map(async p => {
        // Simple capture placeholder - real screenshot would need html2canvas
        return { ...p, image: undefined }
      })
    )

    const r = await fetch('/api/figure_render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        panels: panelsWithImages,
        style: { ...style, sizePreset: preset }
      }),
    })
    const { url } = await r.json()
    if (url) {
      const a = document.createElement('a')
      a.href = url
      a.download = 'figure.svg'
      a.click()
    }
  }

  function saveFig() {
    const blob = new Blob([JSON.stringify({ panels, style }, null, 2)], { type: 'application/json' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = 'figure.uchromfig'; a.click()
  }

  const s = {
    overlay: { position: 'fixed' as const, inset: 0, background: 'rgba(0,0,0,0.75)',
               display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 },
    modal: { background: '#1e1e2e', color: '#cdd6f4', width: '95vw', height: '90vh',
             display: 'flex', flexDirection: 'column' as const, borderRadius: 8, overflow: 'hidden' },
    header: { padding: '8px 14px', background: '#181825', display: 'flex',
              justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, gap: 8 },
    body: { display: 'flex', flex: 1, overflow: 'hidden' },
    canvasWrap: { flex: 1, overflow: 'auto', background: '#11111b', padding: 24 },
    sidebar: { width: 220, flexShrink: 0, padding: 12, overflowY: 'auto' as const,
               borderLeft: '1px solid #313244', display: 'flex', flexDirection: 'column' as const, gap: 12 },
    label: { fontSize: 11, color: '#a6adc8', marginBottom: 3, display: 'block' },
    input: { background: '#313244', border: '1px solid #45475a', color: '#cdd6f4',
             borderRadius: 4, padding: '4px 7px', width: '100%', boxSizing: 'border-box' as const, fontSize: 12 },
    btn: { background: '#89b4fa', color: '#1e1e2e', border: 'none', borderRadius: 4,
           padding: '5px 10px', cursor: 'pointer', fontWeight: 600, fontSize: 12 },
    btnSm: { background: '#313244', color: '#cdd6f4', border: '1px solid #45475a',
             borderRadius: 4, padding: '4px 8px', cursor: 'pointer', fontSize: 11 },
  }

  return (
    <div style={s.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={s.modal}>
        <div style={s.header}>
          <span style={{ fontWeight: 600 }}>Figure Composer</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={s.btnSm} onClick={addPanel}>+ Panel</button>
            <button style={s.btnSm} onClick={saveFig}>Save .uchromfig</button>
            <button style={s.btn} onClick={exportSvg}>Export SVG</button>
            <button style={{ ...s.btnSm, color: '#f38ba8' }} onClick={onClose}>✕</button>
          </div>
        </div>
        <div style={s.body}>
          <div style={s.canvasWrap}>
            <div style={{ position: 'relative', width: canvas.w, height: canvas.h,
                          background: '#fff', boxShadow: '0 2px 16px rgba(0,0,0,0.4)',
                          flexShrink: 0 }}>
              {panels.map(p => (
                <Rnd key={p.id}
                  position={{ x: p.x, y: p.y }} size={{ width: p.w, height: p.h }}
                  bounds="parent" minWidth={80} minHeight={60}
                  onDragStop={(_, d) => setPanels(ps => ps.map(pp => pp.id === p.id ? { ...pp, x: d.x, y: d.y } : pp))}
                  onResizeStop={(_, __, ref, ___, pos) => setPanels(ps => ps.map(pp =>
                    pp.id === p.id ? { ...pp, w: parseInt(ref.style.width), h: parseInt(ref.style.height), ...pos } : pp
                  ))}>
                  <div style={{ width: '100%', height: '100%', border: '1px solid #89b4fa',
                                background: 'rgba(137,180,250,0.06)', borderRadius: 2,
                                display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                    <div style={{ background: '#313244', color: '#cdd6f4', fontSize: 10,
                                  padding: '2px 6px', display: 'flex', justifyContent: 'space-between' }}>
                      <span>{p.label}</span>
                      <button onClick={() => setPanels(ps => ps.filter(pp => pp.id !== p.id))}
                        style={{ background: 'none', border: 'none', color: '#f38ba8',
                                 cursor: 'pointer', fontSize: 11, padding: 0 }}>✕</button>
                    </div>
                    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                  color: '#6c7086', fontSize: 10 }}>{p.label}</div>
                  </div>
                </Rnd>
              ))}
            </div>
          </div>
          <div style={s.sidebar}>
            <div>
              <span style={s.label}>Canvas size</span>
              {Object.entries(PRESETS).map(([k, v]) => (
                <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 6,
                                        fontSize: 11, color: '#cdd6f4', marginBottom: 4, cursor: 'pointer' }}>
                  <input type="radio" checked={preset === k} onChange={() => setPreset(k)} />
                  {v.label}
                </label>
              ))}
            </div>
            <div>
              <span style={s.label}>Font size (pt)</span>
              <input type="number" style={s.input} value={style.fontSize} min={5} max={14}
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
              <span style={s.label}>Colorbar range</span>
              <div style={{ display: 'flex', gap: 6 }}>
                <input type="number" style={{ ...s.input, width: '50%' }} value={style.vmin}
                  onChange={e => setStyle(s => ({ ...s, vmin: +e.target.value }))} />
                <input type="number" style={{ ...s.input, width: '50%' }} value={style.vmax}
                  onChange={e => setStyle(s => ({ ...s, vmax: +e.target.value }))} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

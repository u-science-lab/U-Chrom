import { useEffect, useState } from 'react'
import { useAppStore } from '../store'
import { ws } from '../ws'

const CHROM_SIZES: Record<string, number> = {
  chr1: 195471971, chr2: 182113224, chr3: 160039680, chr4: 156508116,
  chr5: 151834684, chr6: 149736546, chr7: 145441459, chr8: 129401213,
  chr9: 124595110, chr10: 130694993, chr11: 122082543, chr12: 120129022,
  chr13: 120421639, chr14: 124902244, chr15: 104043685, chr16: 98207768,
  chr17: 94987271, chr18: 90702639, chr19: 61431566, chrX: 171031299,
}

const CHROMS = Object.keys(CHROM_SIZES)

function fmtRegion(chrom: string, start: number, end: number) {
  return `${chrom}:${start.toLocaleString()}-${end.toLocaleString()}`
}

function parseRegion(s: string): { chrom: string; start: number; end: number } | null {
  const m = s.replace(/,/g, '').match(/^(\w+):(\d+)-(\d+)$/)
  if (!m) return null
  const [, chrom, a, b] = m
  const start = parseInt(a), end = parseInt(b)
  if (start >= end) return null
  return { chrom, start, end }
}

export default function GenomicNavBar() {
  const { viewport, setViewport } = useAppStore()
  const [inputVal, setInputVal] = useState(fmtRegion(viewport.chrom, viewport.start, viewport.end))
  const [invalid, setInvalid] = useState(false)

  // Sync input when viewport changes externally
  useEffect(() => {
    setInputVal(fmtRegion(viewport.chrom, viewport.start, viewport.end))
    setInvalid(false)
  }, [viewport.chrom, viewport.start, viewport.end])

  // Send WS on every viewport change
  useEffect(() => {
    ws.send('update_viewport', { chrom: viewport.chrom, start: viewport.start, end: viewport.end })
  }, [viewport.chrom, viewport.start, viewport.end])

  function applyViewport(v: { chrom: string; start: number; end: number }) {
    const size = CHROM_SIZES[v.chrom] ?? v.end
    const start = Math.max(0, v.start)
    const end = Math.min(size, v.end)
    setViewport({ chrom: v.chrom, start, end })
  }

  function selectChrom(chrom: string) {
    applyViewport({ chrom, start: 0, end: CHROM_SIZES[chrom] ?? 1000000 })
  }

  function navigate(dir: -1 | 1) {
    const idx = CHROMS.indexOf(viewport.chrom)
    const next = CHROMS[idx + dir]
    if (next) selectChrom(next)
  }

  function commitInput() {
    const parsed = parseRegion(inputVal)
    if (!parsed) { setInvalid(true); return }
    setInvalid(false)
    applyViewport(parsed)
  }

  function zoom(factor: 0.5 | 2) {
    const { chrom, start, end } = viewport
    const mid = (start + end) / 2
    const half = ((end - start) * factor) / 2
    applyViewport({ chrom, start: Math.round(mid - half), end: Math.round(mid + half) })
  }

  const btnStyle: React.CSSProperties = {
    background: '#313244', border: 'none', color: '#cdd6f4', cursor: 'pointer',
    borderRadius: 4, padding: '2px 7px', fontSize: 13, lineHeight: '20px',
  }

  return (
    <div style={{
      height: 36, background: '#1e1e2e', borderTop: '1px solid #313244',
      display: 'flex', alignItems: 'center', padding: '0 8px', gap: 6,
      flexShrink: 0, overflow: 'hidden',
    }}>
      {/* Chromosome navigation */}
      <button style={btnStyle} onClick={() => navigate(-1)}>◀</button>
      <div style={{ display: 'flex', gap: 3, overflow: 'hidden', flexShrink: 1 }}>
        {CHROMS.map(c => (
          <button
            key={c}
            onClick={() => selectChrom(c)}
            style={{
              ...btnStyle,
              background: c === viewport.chrom ? '#89b4fa' : '#313244',
              color: c === viewport.chrom ? '#1e1e2e' : '#cdd6f4',
              padding: '2px 5px', fontSize: 11, whiteSpace: 'nowrap',
            }}
          >{c}</button>
        ))}
      </div>
      <button style={btnStyle} onClick={() => navigate(1)}>▶</button>

      {/* Region input */}
      <input
        value={inputVal}
        onChange={e => setInputVal(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && commitInput()}
        onBlur={commitInput}
        style={{
          background: '#181825', border: `1px solid ${invalid ? '#f38ba8' : '#45475a'}`,
          color: '#cdd6f4', borderRadius: 4, padding: '2px 8px', fontSize: 12,
          width: 220, outline: 'none', flexShrink: 0,
        }}
      />

      {/* Zoom controls */}
      <button style={btnStyle} onClick={() => zoom(0.5)}>+</button>
      <button style={btnStyle} onClick={() => zoom(2)}>−</button>
    </div>
  )
}

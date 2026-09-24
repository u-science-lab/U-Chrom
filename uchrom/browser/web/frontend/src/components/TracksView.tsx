import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchIntervals, fetchTracks } from '../api'
import { fmtBp } from '../filters'
import { niceTicks, panLocus, zoomLocus, type Locus } from '../genome'
import { activeView, useStore } from '../store'
import { fmtAxis, trackRange } from '../stats'
import { binIndexAt, resolveTracks } from '../tracks'
import type { IntervalTable, TrackData } from '../types'
import { useLocus } from '../useLocus'
import { updatePane, type Pane, type TrackAgg } from '../workspace'
import { CHART } from './chart'
import { prepareCanvas, useSize } from './useSize'

const AXIS_H = 24
const INTERVAL_H = 16
const POS = '#e8784f'
const NEG = '#4f8fe8'
const PLAIN = '#6aa4ef'

/** Pane-header controls: which tracks, aggregation, focused-cell filter. */
export function TracksControls({ pane }: { pane: Pane }) {
  // select the stable summary array; derive names outside the selector
  const infos = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.tracks)
  const names = useMemo(() => infos?.map((t) => t.name) ?? [], [infos])
  const focus = useStore((s) => activeView(s).focusCell)
  const setWorkspace = useStore((s) => s.setWorkspace)
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  if (!names.length) return null
  const selected = resolveTracks(pane.tracks, names)
  const set = (tracks: string[]) => setWorkspace((w) => updatePane(w, pane.id, { tracks }))
  const toggle = (t: string) => set(selected.includes(t) ? selected.filter((x) => x !== t) : [...selected, t])
  const shown = names.filter((n) => n.toLowerCase().includes(q.trim().toLowerCase()))
  return (
    <>
      <div className="pane-menu">
        <button onClick={() => setOpen(!open)} title="Choose tracks">
          Tracks ({selected.length}) ▾
        </button>
        {open && (
          <div className="pane-popup" onMouseLeave={() => setOpen(false)}>
            <input autoFocus placeholder="search tracks…" value={q} onChange={(e) => setQ(e.target.value)} />
            <ul>
              {shown.map((t) => (
                <li key={t} onClick={() => toggle(t)} className={selected.includes(t) ? 'on' : ''}>
                  <span className="tick">{selected.includes(t) ? '✓' : ''}</span>
                  {t}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <select value={pane.agg ?? 'mean'} onChange={(e) => setWorkspace((w) => updatePane(w, pane.id, { agg: e.target.value as TrackAgg }))} title="Aggregate spots in each bin">
        <option value="mean">mean</option>
        <option value="median">median</option>
        <option value="max">max</option>
      </select>
      <label className="check small" title={focus ? `Only spots of cell ${focus}` : 'Select a cell to restrict the tracks to it'}>
        <input
          type="checkbox"
          checked={pane.followFocus ?? true}
          onChange={(e) => setWorkspace((w) => updatePane(w, pane.id, { followFocus: e.target.checked }))}
        />{' '}
        focused cell
      </label>
    </>
  )
}

/**
 * Genome-browser style tracks: per-bin aggregates of spot tracks along the
 * shared locus, plus interval rows (TADs, loops).  Drag to pan, wheel to zoom.
 */
export function TracksView({ pane }: { pane: Pane }) {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const focus = useStore((s) => activeView(s).focusCell)
  const { locus, ext, setLocus } = useLocus()
  const boxRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const size = useSize(boxRef)
  const names = useMemo(() => ds?.tracks?.map((t) => t.name) ?? [], [ds])
  const selected = resolveTracks(pane.tracks, names)
  const cellId = (pane.followFocus ?? true) ? focus : null
  const agg = pane.agg ?? 'mean'
  const [data, setData] = useState<TrackData | null>(null)
  const [intervals, setIntervals] = useState<Record<string, IntervalTable>>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [hover, setHover] = useState<{ x: number; y: number; text: string } | null>(null)
  const key = selected.join(',')

  // fetch (debounced: pan / zoom update the locus continuously)
  useEffect(() => {
    if (!ds || !locus || !selected.length) return
    let live = true
    const t = setTimeout(() => {
      setLoading(true)
      fetchTracks(ds.id, selected, locus, { cellId, agg })
        .then((d) => live && (setData(d), setError(null)))
        .catch((e: Error) => live && setError(e.message))
        .finally(() => live && setLoading(false))
      for (const iv of ds.intervals ?? []) {
        fetchIntervals(ds.id, iv.key, locus)
          .then((tab) => live && setIntervals((m) => ({ ...m, [iv.key]: tab })))
          .catch(() => undefined)
      }
    }, 180)
    return () => {
      live = false
      clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ds?.id, key, locus?.chrom, locus?.start, locus?.end, cellId, agg])

  const ivKeys = (ds?.intervals ?? []).map((i) => i.key)
  const rowsTop = AXIS_H + ivKeys.length * INTERVAL_H + 4
  const rowH = selected.length ? Math.max(28, Math.min(90, (size.h - rowsTop - 4) / selected.length)) : 0

  // draw
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv || !size.w || !size.h || !locus) return
    const g = prepareCanvas(cv, size.w, size.h)
    if (!g) return
    const span = locus.end - locus.start
    const X = (bp: number) => ((bp - locus.start) / span) * size.w
    g.font = CHART.font
    // axis
    g.fillStyle = CHART.text
    g.strokeStyle = CHART.axis
    g.textBaseline = 'top'
    g.textAlign = 'center'
    for (const t of niceTicks(locus.start, locus.end, Math.max(2, Math.floor(size.w / 110)))) {
      const x = Math.round(X(t)) + 0.5
      g.beginPath()
      g.moveTo(x, AXIS_H - 6)
      g.lineTo(x, AXIS_H)
      g.stroke()
      g.fillText(fmtBp(t), x, 3)
    }
    g.beginPath()
    g.moveTo(0, AXIS_H + 0.5)
    g.lineTo(size.w, AXIS_H + 0.5)
    g.stroke()
    // interval rows
    ivKeys.forEach((k, r) => {
      const y = AXIS_H + 2 + r * INTERVAL_H
      g.fillStyle = CHART.muted
      g.textAlign = 'left'
      g.textBaseline = 'top'
      g.fillText(k, 4, y + 1)
      const tab = intervals[k]
      if (!tab) return
      const ci = (c: string) => tab.columns.indexOf(c)
      const [cs, ce, cc, cs2, ce2] = [ci('start'), ci('end'), ci('chrom'), ci('start2'), ci('end2')]
      for (const row of tab.rows) {
        if (cc >= 0 && row[cc] !== locus.chrom) continue
        const s = Number(row[cs])
        const e = Number(row[ce])
        if (cs2 >= 0 && ce2 >= 0 && row[cs2] !== null) {
          // pair (loop): arc between anchors
          const a = X((s + e) / 2)
          const b = X((Number(row[cs2]) + Number(row[ce2])) / 2)
          g.strokeStyle = '#d08bf0'
          g.beginPath()
          g.moveTo(a, y + INTERVAL_H - 2)
          g.quadraticCurveTo((a + b) / 2, y - 4, b, y + INTERVAL_H - 2)
          g.stroke()
        } else {
          g.fillStyle = 'rgba(92,157,237,0.35)'
          g.strokeStyle = 'rgba(92,157,237,0.9)'
          const x0 = X(s)
          const w = Math.max(1, X(e) - x0)
          g.fillRect(x0, y + 3, w, INTERVAL_H - 6)
          g.strokeRect(x0 + 0.5, y + 3.5, w - 1, INTERVAL_H - 7)
        }
      }
    })
    // track rows
    if (!data) return
    selected.forEach((name, r) => {
      const top = rowsTop + r * rowH
      const vals = data.values[name] ?? []
      const { lo, hi, diverging } = trackRange(vals)
      const base = top + rowH - 4
      const Y = (v: number) => base - ((v - lo) / (hi - lo || 1)) * (rowH - 16)
      const zero = Y(0)
      g.fillStyle = 'rgba(255,255,255,0.03)'
      g.fillRect(0, top, size.w, rowH - 2)
      for (let i = 0; i < data.bin_starts.length; i++) {
        const v = vals[i]
        if (typeof v !== 'number' || !Number.isFinite(v)) continue
        const x0 = X(data.bin_starts[i])
        const w = Math.max(1, X(data.bin_ends[i]) - x0)
        const y = Y(v)
        g.fillStyle = diverging ? (v >= 0 ? POS : NEG) : PLAIN
        g.fillRect(x0, Math.min(y, zero), w, Math.max(1, Math.abs(zero - y)))
      }
      if (diverging) {
        g.strokeStyle = 'rgba(255,255,255,0.18)'
        g.beginPath()
        g.moveTo(0, Math.round(zero) + 0.5)
        g.lineTo(size.w, Math.round(zero) + 0.5)
        g.stroke()
      }
      g.fillStyle = CHART.text
      g.textAlign = 'left'
      g.textBaseline = 'top'
      g.fillText(name, 4, top + 2)
      g.fillStyle = CHART.muted
      g.textAlign = 'right'
      g.fillText(`${fmtAxis(lo)} … ${fmtAxis(hi)}`, size.w - 4, top + 2)
    })
  }, [data, intervals, size.w, size.h, locus, key, rowH, rowsTop, ivKeys.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  // wheel zoom (non-passive so the page doesn't scroll)
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const onWheel = (e: WheelEvent) => {
      const l = currentLocus.current
      if (!l) return
      e.preventDefault()
      const rect = cv.getBoundingClientRect()
      const center = l.start + ((e.clientX - rect.left) / rect.width) * (l.end - l.start)
      setLocus(zoomLocus(l, Math.exp(e.deltaY * 0.0015), extRef.current, center))
    }
    cv.addEventListener('wheel', onWheel, { passive: false })
    return () => cv.removeEventListener('wheel', onWheel)
  }, [setLocus])
  const currentLocus = useRef<Locus | null>(null)
  currentLocus.current = locus
  const extRef = useRef(ext)
  extRef.current = ext

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!locus) return
    const start = { x: e.clientX, locus }
    const w = e.currentTarget.getBoundingClientRect().width
    const move = (ev: PointerEvent) => {
      const dx = ev.clientX - start.x
      setLocus(panLocus(start.locus, (-dx / w) * (start.locus.end - start.locus.start), extRef.current))
      setHover(null)
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!locus || !data || e.buttons) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const bp = locus.start + (x / rect.width) * (locus.end - locus.start)
    const r = Math.floor((y - rowsTop) / rowH)
    const i = binIndexAt(data.bin_starts, data.bin_ends, bp, ((locus.end - locus.start) / rect.width) * 2)
    if (r < 0 || r >= selected.length || i < 0) return setHover(null)
    const v = data.values[selected[r]]?.[i]
    setHover({
      x,
      y,
      text: `${selected[r]} · ${data.chrom}:${fmtBp(data.bin_starts[i])}-${fmtBp(data.bin_ends[i])} · ${v === null || v === undefined ? '—' : fmtAxis(v)} (${data.n_spots[i]} spots)`,
    })
  }

  let message: string | null = null
  if (!names.length) message = 'This dataset has no spot tracks (cd.tracks).'
  else if (!locus) message = 'No chromosomes to show.'
  return (
    <div ref={boxRef} className="genome-view">
      {message && <div className="muted pane-empty">{message}</div>}
      {error && <div className="error pane-error">{error}</div>}
      <canvas ref={canvasRef} onPointerDown={onPointerDown} onMouseMove={onMove} onMouseLeave={() => setHover(null)} style={{ cursor: 'grab' }} />
      {loading && <div className="pane-loading muted small">loading…</div>}
      {cellId && <div className="pane-badge small">cell {cellId}</div>}
      {hover && (
        <div className="embedding-tip" style={{ left: Math.min(hover.x + 12, size.w - 260), top: hover.y + 12 }}>
          {hover.text}
        </div>
      )}
    </div>
  )
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchContacts, fetchDistance, fetchIntervals, fetchTracks } from '../api'
import { fmtBp, parseGenomicNumber } from '../filters'
import { niceTicks, panLocus, zoomLocus, type Locus } from '../genome'
import {
  addRow,
  defaultRows,
  depthScale,
  moveRow,
  rasterTriangle,
  removeRow,
  resizeRow,
  resolveHeights,
  triangleBins,
  updateRow,
  type GenomeRow,
  type GenomeRowKind,
  type TriangleGeom,
} from '../genomeRows'
import { matrixColor, matrixPixels, matrixRange, scaleFor, type MatrixData } from '../matrix'
import { activeView, hasCoords, useStore } from '../store'
import { fmtAxis, trackRange } from '../stats'
import { binIndexAt } from '../tracks'
import type { DatasetSummary, IntervalTable, TrackData } from '../types'
import { useLocus } from '../useLocus'
import { updatePane, type DistanceStat, type Pane, type TrackAgg } from '../workspace'
import { CHART, drawColorRamp, rgb } from './chart'
import { prepareCanvas, useSize } from './useSize'

const AXIS_H = 26
const POS = '#e8784f'
const NEG = '#4f8fe8'
const PLAIN = '#6aa4ef'
const GUIDE = 'rgba(255,255,255,0.16)'
const STAT_LABEL: Record<DistanceStat, string> = { median: 'median distance', mean: 'mean distance', contact: 'contact frequency' }

// ---- matrix cache: (source, locus, params) → decoded matrix -------------------

const MATRIX_CACHE_SIZE = 32
const matrixCache = new Map<string, MatrixData>()
const inflight = new Map<string, Promise<MatrixData>>()

function cachedMatrix(key: string, load: () => Promise<MatrixData>): Promise<MatrixData> {
  const hit = matrixCache.get(key)
  if (hit) {
    matrixCache.delete(key) // LRU: most recent last
    matrixCache.set(key, hit)
    return Promise.resolve(hit)
  }
  let p = inflight.get(key)
  if (!p) {
    p = load()
      .then((m) => {
        matrixCache.set(key, m)
        while (matrixCache.size > MATRIX_CACHE_SIZE) matrixCache.delete(matrixCache.keys().next().value as string)
        return m
      })
      .finally(() => inflight.delete(key))
    inflight.set(key, p)
  }
  return p
}

// ---- rows of the pane (per dataset, defaults until edited) ------------------

function useGenomeRows(pane: Pane) {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const setWorkspace = useStore((s) => s.setWorkspace)
  const saved = ds ? pane.genomeRows?.[ds.name] : undefined
  const rows = useMemo(() => saved ?? defaultRows(ds, pane.tracks), [saved, ds, pane.tracks])
  /** edit the rows of the active dataset (materialises the defaults first) */
  const setRows = useCallback(
    (f: (rows: GenomeRow[]) => GenomeRow[]) => {
      if (!ds) return
      setWorkspace((w) => {
        const p = w.panes.find((x) => x.id === pane.id)
        if (!p) return w
        const cur = p.genomeRows?.[ds.name] ?? defaultRows(ds, p.tracks)
        return updatePane(w, pane.id, { genomeRows: { ...(p.genomeRows ?? {}), [ds.name]: f(cur) } })
      })
    },
    [ds, pane.id, setWorkspace],
  )
  const resetRows = useCallback(() => {
    if (!ds) return
    setWorkspace((w) => {
      const p = w.panes.find((x) => x.id === pane.id)
      if (!p?.genomeRows?.[ds.name]) return w
      const { [ds.name]: _drop, ...rest } = p.genomeRows // eslint-disable-line @typescript-eslint/no-unused-vars
      return updatePane(w, pane.id, { genomeRows: rest })
    })
  }, [ds, pane.id, setWorkspace])
  return { ds, rows, setRows, resetRows, customised: !!saved }
}

/** A new row of `kind`, preferring a source / track / table not shown yet. */
function newRow(kind: GenomeRowKind, rows: GenomeRow[], ds: DatasetSummary): Omit<GenomeRow, 'id'> {
  if (kind === 'matrix') {
    const used = new Set(rows.map((r) => r.source))
    const options = [...(ds.contact_maps ?? []).map((m) => m.key), ...(hasCoords(ds) ? ['distance'] : [])]
    return { kind, source: options.find((o) => !used.has(o)) ?? options[0] ?? null }
  }
  if (kind === 'track') {
    const used = new Set(rows.map((r) => r.track))
    const names = (ds.tracks ?? []).map((t) => t.name)
    return { kind, track: names.find((n) => !used.has(n)) ?? names[0] ?? null }
  }
  const used = new Set(rows.map((r) => r.key))
  const keys = (ds.intervals ?? []).map((i) => i.key)
  return { kind, key: keys.find((k) => !used.has(k)) ?? keys[0] ?? null }
}

/** Pane-header controls: add rows, track aggregation, reset. */
export function GenomeControls({ pane }: { pane: Pane }) {
  const { ds, rows, setRows, resetRows, customised } = useGenomeRows(pane)
  const focus = useStore((s) => activeView(s).focusCell)
  const setWorkspace = useStore((s) => s.setWorkspace)
  const [menu, setMenu] = useState(false)
  if (!ds) return null
  const can: Record<GenomeRowKind, boolean> = {
    matrix: (ds.contact_maps?.length ?? 0) > 0 || hasCoords(ds),
    track: (ds.tracks?.length ?? 0) > 0,
    intervals: (ds.intervals?.length ?? 0) > 0,
  }
  const add = (kind: GenomeRowKind) => {
    if (!can[kind]) return
    setRows((r) => addRow(r, newRow(kind, r, ds)))
    setMenu(false)
  }
  const label: Record<GenomeRowKind, string> = { matrix: 'Matrix triangle (Hi-C / 3-D distance)', track: 'Track', intervals: 'Intervals (TADs, loops…)' }
  return (
    <>
      <div className="pane-menu">
        <button onClick={() => setMenu(!menu)} title="Add a row">
          + Row ▾
        </button>
        {menu && (
          <div className="pane-popup" onMouseLeave={() => setMenu(false)}>
            <ul>
              {(['matrix', 'track', 'intervals'] as GenomeRowKind[]).map((k) => (
                <li key={k} className={can[k] ? '' : 'disabled'} onClick={() => add(k)} title={can[k] ? '' : 'Not available in this dataset'}>
                  {label[k]}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {rows.some((r) => r.kind === 'track') && (
        <>
          <select value={pane.agg ?? 'mean'} onChange={(e) => setWorkspace((w) => updatePane(w, pane.id, { agg: e.target.value as TrackAgg }))} title="Aggregate spots in each bin">
            <option value="mean">mean</option>
            <option value="median">median</option>
            <option value="max">max</option>
          </select>
          <label className="check small" title={focus ? `Tracks: only spots of cell ${focus}` : 'Tracks: select a cell to restrict them to it'}>
            <input type="checkbox" checked={pane.followFocus ?? true} onChange={(e) => setWorkspace((w) => updatePane(w, pane.id, { followFocus: e.target.checked }))} />{' '}
            focused cell
          </label>
        </>
      )}
      {customised && (
        <button onClick={resetRows} title="Back to the default rows for this dataset">
          Reset rows
        </button>
      )}
    </>
  )
}

type Describe = (x: number, y: number) => string | null

/**
 * Combined genome view: matrix triangles (Hi-C / 3-D distance), tracks and
 * intervals stacked on one genomic axis = the shared locus.  Drag pans,
 * wheel zooms, every row moves together; a crosshair follows the mouse.
 */
export function GenomeView({ pane }: { pane: Pane }) {
  const { ds, rows, setRows } = useGenomeRows(pane)
  const focus = useStore((s) => activeView(s).focusCell)
  const { locus, ext, setLocus } = useLocus()
  const boxRef = useRef<HTMLDivElement>(null)
  const rowsRef = useRef<HTMLDivElement>(null)
  const { w: W, h: rowsH } = useSize(rowsRef) // client width: excludes the scrollbar, so every row shares one axis
  const heights = useMemo(() => resolveHeights(rows, rowsH, W), [rows, rowsH, W])
  const [hover, setHover] = useState<{ x: number; y: number; text: string | null } | null>(null)
  const describers = useRef(new Map<string, Describe>())
  const register = useCallback((id: string, f: Describe | null) => {
    if (f) describers.current.set(id, f)
    else describers.current.delete(id)
  }, [])

  // tracks: one request for every track row
  const names = useMemo(() => new Set((ds?.tracks ?? []).map((t) => t.name)), [ds])
  const trackNames = [...new Set(rows.filter((r) => r.kind === 'track' && r.track && names.has(r.track)).map((r) => r.track!))]
  const trackKey = trackNames.join(',')
  const agg = pane.agg ?? 'mean'
  const trackCell = (pane.followFocus ?? true) ? focus : null
  const [tracks, setTracks] = useState<TrackData | null>(null)
  const [trackError, setTrackError] = useState<string | null>(null)
  useEffect(() => {
    if (!ds || !locus || !trackNames.length) return
    let live = true
    const t = setTimeout(() => {
      fetchTracks(ds.id, trackNames, locus, { cellId: trackCell, agg })
        .then((d) => live && (setTracks(d), setTrackError(null)))
        .catch((e: Error) => live && setTrackError(e.message))
    }, 180)
    return () => {
      live = false
      clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ds?.id, trackKey, locus?.chrom, locus?.start, locus?.end, trackCell, agg])

  // interval tables shown as rows (their boundaries also guide the matrix rows)
  const ivKeys = [...new Set(rows.filter((r) => r.kind === 'intervals' && r.key).map((r) => r.key!))]
  const ivKey = ivKeys.join(',')
  const [intervals, setIntervals] = useState<Record<string, IntervalTable>>({})
  useEffect(() => {
    if (!ds || !locus || !ivKeys.length) return
    let live = true
    const t = setTimeout(() => {
      for (const k of ivKeys) {
        fetchIntervals(ds.id, k, locus)
          .then((tab) => live && setIntervals((m) => ({ ...m, [k]: tab })))
          .catch(() => undefined)
      }
    }, 180)
    return () => {
      live = false
      clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ds?.id, ivKey, locus?.chrom, locus?.start, locus?.end])
  const guides = useMemo(() => {
    if (!locus) return []
    const out = new Set<number>()
    for (const k of ivKeys) {
      const tab = intervals[k]
      if (!tab) continue
      const c = (n: string) => tab.columns.indexOf(n)
      const [cs, ce, cc, cs2] = [c('start'), c('end'), c('chrom'), c('start2')]
      for (const row of tab.rows) {
        if (cc >= 0 && row[cc] !== locus.chrom) continue
        if (cs2 >= 0 && row[cs2] !== null) continue // loops: no boundaries
        for (const v of [Number(row[cs]), Number(row[ce])]) if (v > locus.start && v < locus.end) out.add(v)
      }
    }
    return [...out]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervals, ivKey, locus])

  // wheel zoom (non-passive so the page doesn't scroll); not over row tools
  const currentLocus = useRef<Locus | null>(null)
  currentLocus.current = locus
  const extRef = useRef(ext)
  extRef.current = ext
  useEffect(() => {
    const box = boxRef.current
    if (!box) return
    const onWheel = (e: WheelEvent) => {
      const l = currentLocus.current
      const rowsEl = rowsRef.current
      if (!l || !rowsEl || (e.target as HTMLElement).closest('.gv-tools')) return
      e.preventDefault()
      const rect = rowsEl.getBoundingClientRect()
      const center = l.start + ((e.clientX - rect.left) / rowsEl.clientWidth) * (l.end - l.start)
      setLocus(zoomLocus(l, Math.exp(e.deltaY * 0.0015), extRef.current, center))
    }
    box.addEventListener('wheel', onWheel, { passive: false })
    return () => box.removeEventListener('wheel', onWheel)
  }, [setLocus])

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!locus || e.button !== 0 || (e.target as HTMLElement).closest('.gv-tools, .gv-resize, select, input, button')) return
    const start = { x: e.clientX, locus }
    const w = rowsRef.current?.clientWidth || 1
    const move = (ev: PointerEvent) => {
      setLocus(panLocus(start.locus, (-(ev.clientX - start.x) / w) * (start.locus.end - start.locus.start), extRef.current))
      setHover(null)
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  const onMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const box = boxRef.current
    const rowsEl = rowsRef.current
    if (!box || !rowsEl || e.buttons) return
    const b = box.getBoundingClientRect()
    const x = e.clientX - b.left
    if (x < 0 || x >= rowsEl.clientWidth || (e.target as HTMLElement).closest('.gv-tools')) return setHover(null)
    let text: string | null = null
    const rowEl = (e.target as HTMLElement).closest<HTMLElement>('[data-row]')
    const cv = rowEl?.querySelector('canvas')
    if (rowEl && cv) {
      const r = cv.getBoundingClientRect()
      text = describers.current.get(rowEl.dataset.row!)?.(e.clientX - r.left, e.clientY - r.top) ?? null
    } else if (locus) {
      text = `${locus.chrom}:${fmtBp(Math.round(locus.start + (x / rowsEl.clientWidth) * (locus.end - locus.start)))}`
    }
    setHover({ x, y: e.clientY - b.top, text })
  }

  let message: string | null = null
  if (!ds) message = 'No dataset.'
  else if (!locus) message = 'No chromosomes to show.'
  else if (!rows.length) message = 'No rows — add one with “+ Row”.'
  const boxW = boxRef.current?.clientWidth ?? W
  return (
    <div ref={boxRef} className="genome-view gv" onPointerDown={onPointerDown} onMouseMove={onMouseMove} onMouseLeave={() => setHover(null)}>
      {message && <div className="muted pane-empty">{message}</div>}
      {trackError && <div className="error pane-error">{trackError}</div>}
      {locus && W > 0 && <AxisRuler width={W} locus={locus} />}
      <div ref={rowsRef} className="gv-rows">
        {ds &&
          locus &&
          W > 0 &&
          rows.map((r, i) => (
            <RowFrame key={r.id} row={r} height={heights[i]} ds={ds} first={i === 0} last={i === rows.length - 1} setRows={setRows}>
              {r.kind === 'matrix' && <MatrixRow row={r} height={heights[i]} ds={ds} width={W} locus={locus} focus={focus} guides={guides} register={register} />}
              {r.kind === 'track' && <TrackRow row={r} height={heights[i]} width={W} locus={locus} data={tracks} register={register} />}
              {r.kind === 'intervals' && (
                <IntervalRow row={r} height={heights[i]} width={W} locus={locus} table={r.key ? intervals[r.key] : undefined} register={register} />
              )}
            </RowFrame>
          ))}
      </div>
      {hover && <div className="gv-cross" style={{ left: hover.x }} />}
      {hover?.text && (
        <div className="embedding-tip" style={hover.x > boxW / 2 ? { right: boxW - hover.x + 12, top: hover.y + 14 } : { left: hover.x + 12, top: hover.y + 14 }}>
          {hover.text}
        </div>
      )}
      {trackCell && rows.some((r) => r.kind === 'track') && <div className="pane-badge small">tracks: cell {trackCell}</div>}
    </div>
  )
}

/** Genomic ruler along the top of the pane. */
function AxisRuler({ width, locus }: { width: number; locus: Locus }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const g = prepareCanvas(cv, width, AXIS_H)
    if (!g) return
    const span = locus.end - locus.start
    const X = (bp: number) => ((bp - locus.start) / span) * width
    g.font = CHART.font
    g.strokeStyle = CHART.axis
    g.fillStyle = CHART.text
    g.textBaseline = 'top'
    for (const t of niceTicks(locus.start, locus.end, Math.max(2, Math.floor(width / 110)))) {
      const x = Math.round(X(t)) + 0.5
      g.beginPath()
      g.moveTo(x, AXIS_H - 7)
      g.lineTo(x, AXIS_H)
      g.stroke()
      const label = fmtBp(t)
      const half = g.measureText(label).width / 2
      g.textAlign = 'center'
      g.fillText(label, Math.max(half + 2, Math.min(x, width - half - 2)), 4)
    }
    g.beginPath()
    g.moveTo(0, AXIS_H - 0.5)
    g.lineTo(width, AXIS_H - 0.5)
    g.stroke()
  }, [width, locus])
  return <canvas ref={ref} className="gv-axis" style={{ width, height: AXIS_H }} />
}

/** Row chrome: tools on hover (config, ↑ ↓ ×) and a bottom edge to drag the height. */
function RowFrame({
  row,
  height,
  ds,
  first,
  last,
  setRows,
  children,
}: {
  row: GenomeRow
  height: number
  ds: DatasetSummary
  first: boolean
  last: boolean
  setRows(f: (rows: GenomeRow[]) => GenomeRow[]): void
  children: React.ReactNode
}) {
  const upd = (p: Partial<GenomeRow>) => setRows((r) => updateRow(r, row.id, p))
  const onResize = (e: React.PointerEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const y0 = e.clientY
    const h0 = height
    const move = (ev: PointerEvent) => setRows((r) => resizeRow(r, row.id, h0 + ev.clientY - y0))
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      document.body.classList.remove('resizing-rows')
    }
    document.body.classList.add('resizing-rows')
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  return (
    <div className={`gv-row ${row.kind}`} data-row={row.id} style={{ height }}>
      {children}
      <div className="gv-tools" onPointerDown={(e) => e.stopPropagation()}>
        {row.kind === 'matrix' && <MatrixTools row={row} ds={ds} upd={upd} />}
        {row.kind === 'track' && (
          <select value={row.track ?? ''} onChange={(e) => upd({ track: e.target.value })} title="Track">
            {(ds.tracks ?? []).map((t) => (
              <option key={t.name} value={t.name}>
                {t.name}
              </option>
            ))}
          </select>
        )}
        {row.kind === 'intervals' && (
          <select value={row.key ?? ''} onChange={(e) => upd({ key: e.target.value })} title="Interval table">
            {(ds.intervals ?? []).map((t) => (
              <option key={t.key} value={t.key}>
                {t.key}
              </option>
            ))}
          </select>
        )}
        <button onClick={() => setRows((r) => moveRow(r, row.id, -1))} disabled={first} title="Move up">
          ↑
        </button>
        <button onClick={() => setRows((r) => moveRow(r, row.id, 1))} disabled={last} title="Move down">
          ↓
        </button>
        <button onClick={() => setRows((r) => removeRow(r, row.id))} title="Remove this row">
          ×
        </button>
      </div>
      <div className="gv-resize" onPointerDown={onResize} title="Drag to change the row height" />
    </div>
  )
}

function MatrixTools({ row, ds, upd }: { row: GenomeRow; ds: DatasetSummary; upd(p: Partial<GenomeRow>): void }) {
  const maps = ds.contact_maps ?? []
  const map = maps.find((m) => m.key === row.source)
  const [depth, setDepth] = useState(row.maxDist ? fmtBp(row.maxDist) : '')
  useEffect(() => setDepth(row.maxDist ? fmtBp(row.maxDist) : ''), [row.maxDist])
  const commitDepth = () => {
    if (!depth.trim()) return upd({ maxDist: null })
    try {
      const v = parseGenomicNumber(depth)
      upd({ maxDist: v > 0 ? v : null })
    } catch {
      setDepth(row.maxDist ? fmtBp(row.maxDist) : '')
    }
  }
  return (
    <>
      <select value={row.source ?? ''} onChange={(e) => upd({ source: e.target.value, resolution: null })} title="Matrix source">
        {maps.map((m) => (
          <option key={m.key} value={m.key}>
            {m.label || m.key} ({m.kind})
          </option>
        ))}
        {hasCoords(ds) && <option value="distance">3-D distance</option>}
      </select>
      {map && map.resolutions.length > 1 && (
        <select value={row.resolution ?? ''} onChange={(e) => upd({ resolution: e.target.value ? +e.target.value : null })} title="Resolution">
          <option value="">auto</option>
          {map.resolutions.map((r) => (
            <option key={r} value={r}>
              {fmtBp(r)}
            </option>
          ))}
        </select>
      )}
      {map && (
        <label className="check small" title="ICE-balanced values (if the cooler has weights)">
          <input type="checkbox" checked={row.balance ?? false} onChange={(e) => upd({ balance: e.target.checked })} /> balanced
        </label>
      )}
      {row.source === 'distance' && (
        <>
          <select value={row.stat ?? 'median'} onChange={(e) => upd({ stat: e.target.value as DistanceStat })} title="Statistic over traces">
            <option value="median">median</option>
            <option value="mean">mean</option>
            <option value="contact">contact freq.</option>
          </select>
          <label className="check small" title="Only the focused cell's traces">
            <input type="checkbox" checked={row.followFocus ?? true} onChange={(e) => upd({ followFocus: e.target.checked })} /> focused cell
          </label>
        </>
      )}
      <input
        className="num"
        value={depth}
        placeholder="max dist"
        title="Deepest genomic separation shown over the row height (e.g. 5M); empty = true 45°"
        onChange={(e) => setDepth(e.target.value)}
        onBlur={commitDepth}
        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
      />
      <button className={row.flip ? 'active' : ''} onClick={() => upd({ flip: !row.flip })} title="Flip: diagonal at the top / bottom of the row">
        ⇅
      </button>
    </>
  )
}

/** Canvas of one row (CSS size width × height at devicePixelRatio). */
function useRowCanvas(width: number, height: number) {
  const ref = useRef<HTMLCanvasElement>(null)
  return { ref, style: { width, height } }
}

function useRegister(register: (id: string, f: Describe | null) => void, id: string, describe: Describe) {
  const f = useRef(describe)
  f.current = describe
  useEffect(() => {
    register(id, (x, y) => f.current(x, y))
    return () => register(id, null)
  }, [register, id])
}

/** Upper triangle of a contact / distance matrix rotated 45° onto the axis. */
function MatrixRow({
  row,
  height,
  ds,
  width,
  locus,
  focus,
  guides,
  register,
}: {
  row: GenomeRow
  height: number
  ds: DatasetSummary
  width: number
  locus: Locus
  focus: string | null
  guides: number[]
  register(id: string, f: Describe | null): void
}) {
  const { ref, style } = useRowCanvas(width, height)
  const map = (ds.contact_maps ?? []).find((m) => m.key === row.source)
  const isDist = row.source === 'distance'
  const valid = isDist ? hasCoords(ds) : !!map
  const needsCell = !!map?.per_cell
  const cell = needsCell ? focus : isDist && (row.followFocus ?? true) ? focus : null
  const waiting = needsCell && !focus
  const stat = row.stat ?? 'median'
  const [mat, setMat] = useState<MatrixData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!valid || waiting) {
      setMat(null)
      setError(null)
      return
    }
    const key = [ds.id, row.source, locus.chrom, locus.start, locus.end, row.resolution ?? '', row.balance ? 1 : 0, cell ?? '', stat, row.threshold ?? ''].join('|')
    let live = true
    const load = () =>
      isDist
        ? fetchDistance(ds.id, locus, { cellId: cell, stat, threshold: row.threshold ?? null })
        : fetchContacts(ds.id, row.source!, locus, { resolution: row.resolution ?? null, balance: row.balance ?? false, cell })
    // cached → at once; else debounced (pan / zoom move the locus continuously)
    const t = setTimeout(
      () => {
        setLoading(true)
        cachedMatrix(key, load)
          .then((m) => live && (setMat(m), setError(null)))
          .catch((e: Error) => live && setError(e.message))
          .finally(() => live && setLoading(false))
      },
      matrixCache.has(key) ? 0 : 200,
    )
    return () => {
      live = false
      clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ds.id, row.source, locus.chrom, locus.start, locus.end, row.resolution, row.balance, cell, stat, row.threshold, valid, waiting])

  // a stale matrix of another chromosome must not be drawn on this axis
  const shown = mat && mat.header.chrom === locus.chrom && !waiting && valid ? mat : null
  const scale = shown ? scaleFor(shown.header.value) : 'contacts'
  const range = useMemo<[number, number]>(() => (shown ? matrixRange(shown.data, scale) : [0, 1]), [shown, scale])
  const colors = useMemo(() => (shown ? matrixPixels(shown, scale, range) : null), [shown, scale, range])
  const k = depthScale(row.maxDist, (locus.end - locus.start) / width, height)
  const geom: TriangleGeom = { start: locus.start, bpPerPx: (locus.end - locus.start) / width, height, k, flip: !!row.flip, maxDist: row.maxDist ?? null }
  const title = isDist ? `3-D distance · ${STAT_LABEL[stat]}` : map ? map.label || map.key : `unknown source “${row.source}”`
  const note = [cell ? `cell ${cell}` : null, shown?.header.resolution ? `${fmtBp(shown.header.resolution)} bins` : null, shown?.header.n_traces ? `${shown.header.n_traces} traces` : null]
    .filter(Boolean)
    .join(' · ')

  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const g = prepareCanvas(cv, width, height)
    if (!g) return
    const dpr = cv.width / width
    if (shown && colors) {
      // pixel-accurate: inverse-map every device pixel to its bin pair
      const dg: TriangleGeom = { ...geom, bpPerPx: geom.bpPerPx / dpr, height: cv.height }
      const px = rasterTriangle(cv.width, cv.height, dg, shown.header.bin_starts, shown.header.bin_ends, colors)
      g.putImageData(new ImageData(px as unknown as Uint8ClampedArray<ArrayBuffer>, cv.width, cv.height), 0, 0)
    }
    // interval boundaries as faint guides
    if (guides.length) {
      g.strokeStyle = GUIDE
      g.lineWidth = 1
      g.setLineDash([3, 3])
      for (const bp of guides) {
        const x = Math.round(((bp - locus.start) / (locus.end - locus.start)) * width) + 0.5
        g.beginPath()
        g.moveTo(x, 0)
        g.lineTo(x, height)
        g.stroke()
      }
      g.setLineDash([])
    }
    // label + colour bar in the empty corner (top for ▲, bottom for ▼)
    const top = row.flip ? height - 44 : 4
    g.font = CHART.font
    g.textAlign = 'left'
    g.textBaseline = 'top'
    g.fillStyle = CHART.text
    g.fillText(title, 6, top)
    if (note) {
      g.fillStyle = CHART.muted
      g.fillText(note, 6, top + 14)
    }
    if (shown && height >= 70) {
      const lo = scale === 'contacts' ? '0' : fmtAxis(range[0])
      const hi = scale === 'contacts' ? `≥${fmtAxis(Math.expm1(range[1]))}` : fmtAxis(range[1])
      const color = (t: number) => rgb(matrixColor(scale === 'contacts' ? Math.expm1(t * range[1]) : range[0] + t * (range[1] - range[0]), scale, range))
      const rw = 70
      g.save()
      g.textAlign = 'right'
      drawColorRamp(g, { x: width - rw - 8, y: row.flip ? height - 22 : 8, w: rw, h: 6 }, color, lo, hi)
      g.restore()
    }
    const msg = !valid
      ? title
      : waiting
        ? `“${map?.label || map?.key}” holds one map per cell — select a cell (cell list, embedding or ←/→)`
        : error
    if (msg) {
      g.fillStyle = error ? '#e07a7a' : CHART.muted
      g.textAlign = 'center'
      g.textBaseline = 'middle'
      g.fillText(msg, width / 2, height / 2)
    }
    if (loading && !shown) {
      g.fillStyle = CHART.muted
      g.textAlign = 'center'
      g.textBaseline = 'middle'
      g.fillText('loading…', width / 2, height / 2)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown, colors, width, height, locus, k, row.flip, row.maxDist, guides, title, note, error, waiting, valid, loading])

  useRegister(register, row.id, (x, y) => {
    if (!shown) return null
    const h = shown.header
    const b = triangleBins(x, y, geom, h.bin_starts, h.bin_ends)
    if (!b) return null
    const [i, j] = b
    const v = shown.data[i * h.n_cols + j]
    const unit = scale === 'distance' && h.unit ? ` ${h.unit}` : ''
    return `${title} · bins ${i}, ${j} · ${h.chrom}:${fmtBp(h.bin_starts[i])} × ${fmtBp(h.bin_starts[j])} · ${Number.isFinite(v) ? fmtAxis(v) : '—'}${unit}`
  })
  return (
    <>
      <canvas ref={ref} style={style} />
      {loading && shown && <div className="gv-row-loading muted small">loading…</div>}
    </>
  )
}

/** One spot track as a bar plot (diverging colours for signed values). */
function TrackRow({
  row,
  height,
  width,
  locus,
  data,
  register,
}: {
  row: GenomeRow
  height: number
  width: number
  locus: Locus
  data: TrackData | null
  register(id: string, f: Describe | null): void
}) {
  const { ref, style } = useRowCanvas(width, height)
  const name = row.track ?? ''
  const vals = data?.chrom === locus.chrom ? data.values[name] : undefined
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const g = prepareCanvas(cv, width, height)
    if (!g) return
    const X = (bp: number) => ((bp - locus.start) / (locus.end - locus.start)) * width
    g.fillStyle = 'rgba(255,255,255,0.03)'
    g.fillRect(0, 0, width, height - 1)
    g.font = CHART.font
    if (vals && data) {
      const { lo, hi, diverging } = trackRange(vals)
      const base = height - 3
      const Y = (v: number) => base - ((v - lo) / (hi - lo || 1)) * Math.max(4, height - 16)
      const zero = Y(0)
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
        g.lineTo(width, Math.round(zero) + 0.5)
        g.stroke()
      }
      g.fillStyle = CHART.muted
      g.textAlign = 'right'
      g.textBaseline = 'top'
      g.fillText(`${fmtAxis(lo)} … ${fmtAxis(hi)}`, width - 6, 2)
    }
    g.fillStyle = CHART.text
    g.textAlign = 'left'
    g.textBaseline = 'top'
    g.fillText(name || '(no track)', 6, 2)
  }, [vals, data, width, height, locus, name]) // eslint-disable-line react-hooks/exhaustive-deps
  useRegister(register, row.id, (x) => {
    if (!vals || !data) return null
    const bp = locus.start + (x / width) * (locus.end - locus.start)
    const i = binIndexAt(data.bin_starts, data.bin_ends, bp, ((locus.end - locus.start) / width) * 2)
    if (i < 0) return null
    const v = vals[i]
    return `${name} · ${data.chrom}:${fmtBp(data.bin_starts[i])}-${fmtBp(data.bin_ends[i])} · ${v === null || v === undefined ? '—' : fmtAxis(v)} (${data.n_spots[i]} spots)`
  })
  return <canvas ref={ref} style={style} />
}

/** Interval table (TADs as boxes, loops as arcs). */
function IntervalRow({
  row,
  height,
  width,
  locus,
  table,
  register,
}: {
  row: GenomeRow
  height: number
  width: number
  locus: Locus
  table: IntervalTable | undefined
  register(id: string, f: Describe | null): void
}) {
  const { ref, style } = useRowCanvas(width, height)
  const items = useMemo(() => {
    if (!table) return []
    const c = (n: string) => table.columns.indexOf(n)
    const [cs, ce, cc, cs2, ce2] = [c('start'), c('end'), c('chrom'), c('start2'), c('end2')]
    return table.rows
      .filter((r) => cc < 0 || r[cc] === locus.chrom)
      .map((r) => ({
        s: Number(r[cs]),
        e: Number(r[ce]),
        s2: cs2 >= 0 && r[cs2] !== null ? Number(r[cs2]) : null,
        e2: ce2 >= 0 && r[ce2] !== null ? Number(r[ce2]) : null,
      }))
  }, [table, locus.chrom])
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const g = prepareCanvas(cv, width, height)
    if (!g) return
    const X = (bp: number) => ((bp - locus.start) / (locus.end - locus.start)) * width
    for (const it of items) {
      if (it.s2 !== null && it.e2 !== null) {
        const a = X((it.s + it.e) / 2)
        const b = X((it.s2 + it.e2) / 2)
        g.strokeStyle = '#d08bf0'
        g.beginPath()
        g.moveTo(a, height - 2)
        g.quadraticCurveTo((a + b) / 2, -height * 0.6, b, height - 2)
        g.stroke()
      } else {
        const x0 = X(it.s)
        const w = Math.max(1, X(it.e) - x0)
        g.fillStyle = 'rgba(92,157,237,0.35)'
        g.strokeStyle = 'rgba(92,157,237,0.9)'
        g.fillRect(x0, 3, w, height - 6)
        g.strokeRect(x0 + 0.5, 3.5, w - 1, height - 7)
      }
    }
    g.font = CHART.font
    g.fillStyle = CHART.muted
    g.textAlign = 'left'
    g.textBaseline = 'top'
    g.fillText(row.key ?? '', 6, Math.max(0, height / 2 - 7))
  }, [items, width, height, locus, row.key]) // eslint-disable-line react-hooks/exhaustive-deps
  useRegister(register, row.id, (x) => {
    const bp = locus.start + (x / width) * (locus.end - locus.start)
    const hit = items.find((it) => it.s2 === null && bp >= it.s && bp < it.e)
    return hit ? `${row.key} · ${locus.chrom}:${fmtBp(hit.s)}-${fmtBp(hit.e)}` : null
  })
  return <canvas ref={ref} style={style} />
}

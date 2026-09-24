import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchContacts, fetchDistance, fetchIntervals, fetchTracks } from '../api'
import { fmtBp } from '../filters'
import { niceTicks, panLocus, zoomLocus, type Locus } from '../genome'
import {
  addRow,
  applyRowSetting,
  setRowScope,
  defaultRows,
  depthScale,
  moveRow,
  rasterTriangle,
  removeRow,
  resizeRow,
  resolveHeights,
  ROW_HEIGHT,
  triangleBins,
  type GenomeRow,
  type RowSetting,
  type GenomeRowKind,
  type TriangleGeom,
} from '../genomeRows'
import { ALL_CELLS_REF, isMultiCell, resolveRowScope, scopeKey, scopeParams, scopeText, type GroupInfo, type Scope } from '../groups'
import { matrixColor, matrixPixels, matrixRange, scaleFor, type MatrixData } from '../matrix'
import { hasCoords, useStore } from '../store'
import { fmtAxis, trackRange } from '../stats'
import { binIndexAt } from '../tracks'
import type { DatasetSummary, IntervalTable, TrackData } from '../types'
import type { RowScopeSpec } from '../groups'
import { useLocus } from '../useLocus'
import { useFocusState, useGroupInfos, usePaneScope, useRowScope } from '../useGroups'
import { DistanceValueControls, TrackAggregateControl } from './AggregateControls'
import { ScopePicker, useNCells } from './ScopePicker'
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

export function useGenomeRows(pane: Pane) {
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

const KIND_LABEL: Record<GenomeRowKind, string> = { matrix: 'Matrix', track: 'Track', intervals: 'Intervals' }

/** Short name of a row for the inspector list. */
function rowLabel(r: GenomeRow, ds: DatasetSummary): string {
  if (r.kind === 'matrix') {
    if (r.source === 'distance') return `3-D distance · ${r.stat ?? 'median'}`
    const m = (ds.contact_maps ?? []).find((x) => x.key === r.source)
    return m ? m.label || m.key : (r.source ?? '—')
  }
  return (r.kind === 'track' ? r.track : r.key) ?? '—'
}

/**
 * Inspector of a genome pane: its rows (add / remove / reorder) with every
 * row's settings — its own cells setting (default: same as the view) and,
 * when that covers several cells, how they are aggregated.
 */
export function GenomeInspector({ pane }: { pane: Pane }) {
  const { ds, rows, setRows, resetRows, customised } = useGenomeRows(pane)
  const scope = usePaneScope(pane)
  if (!ds) return null
  const can: Record<GenomeRowKind, boolean> = {
    matrix: (ds.contact_maps?.length ?? 0) > 0 || hasCoords(ds),
    track: (ds.tracks?.length ?? 0) > 0,
    intervals: (ds.intervals?.length ?? 0) > 0,
  }
  const set = (id: string) => (setting: RowSetting, value: string | boolean) => setRows((r) => applyRowSetting(r, id, setting, value))
  return (
    <section className="insp-genome">
      <h2>
        Rows <span className="muted">{rows.length}</span>
        {customised && (
          <button className="link" onClick={resetRows} title="Back to the default rows for this dataset">
            reset
          </button>
        )}
      </h2>
      <div className="seg insp-add">
        {(['matrix', 'track', 'intervals'] as GenomeRowKind[]).map((k) => (
          <button key={k} disabled={!can[k]} onClick={() => setRows((r) => addRow(r, newRow(k, r, ds)))} title={can[k] ? `Add a ${KIND_LABEL[k].toLowerCase()} row` : 'Not available in this dataset'}>
            + {KIND_LABEL[k]}
          </button>
        ))}
      </div>
      {!rows.length && <p className="muted small">No rows — add one above.</p>}
      <ol className="row-list">
        {rows.map((r, i) => (
          <li key={r.id} className={`row-card ${r.kind}`}>
            <div className="row-card-head">
              <span className="row-kind">{KIND_LABEL[r.kind]}</span>
              <span className="row-name" title={rowLabel(r, ds)}>
                {rowLabel(r, ds)}
              </span>
              <button onClick={() => setRows((x) => moveRow(x, r.id, -1))} disabled={i === 0} title="Move up">
                ↑
              </button>
              <button onClick={() => setRows((x) => moveRow(x, r.id, 1))} disabled={i === rows.length - 1} title="Move down">
                ↓
              </button>
              <button onClick={() => setRows((x) => removeRow(x, r.id))} title="Remove this row">
                ×
              </button>
            </div>
            <RowSettings row={r} ds={ds} set={set(r.id)} view={scope} defaultAgg={pane.agg ?? 'mean'} setScope={(sc) => setRows((x) => setRowScope(x, r.id, sc))} />
          </li>
        ))}
      </ol>
      <div className="muted small">Drag a row’s bottom edge in the view to resize it; wheel zooms, drag pans.</div>
    </section>
  )
}

/** Whether a row has a cells setting: tracks, the 3-D distance and per-cell contact maps (not bulk maps / intervals). */
export function rowTakesGroup(row: GenomeRow, ds: DatasetSummary): boolean {
  if (row.kind === 'track') return true
  if (row.kind !== 'matrix') return false
  if (row.source === 'distance') return hasCoords(ds)
  return !!(ds.contact_maps ?? []).find((m) => m.key === row.source)?.per_cell
}

/** Settings of one row (by kind). */
function RowSettings({
  row,
  ds,
  set,
  view,
  defaultAgg,
  setScope,
}: {
  row: GenomeRow
  ds: DatasetSummary
  set(setting: RowSetting, value: string | boolean): void
  /** the view's resolved cells */
  view: Scope
  defaultAgg: TrackAgg
  setScope(s: RowScopeSpec): void
}) {
  const scope = useRowScope(row.scope, view)
  const multi = isMultiCell(scope)
  const perCellMap = row.kind === 'matrix' && row.source !== 'distance' && !!(ds.contact_maps ?? []).find((m) => m.key === row.source)?.per_cell
  return (
    <div className="row-card-body">
      {row.kind === 'matrix' && <MatrixTools row={row} ds={ds} set={set} multi={multi} />}
      {row.kind === 'track' && (
        <select value={row.track ?? ''} onChange={(e) => set('track', e.target.value)} title="Track">
          {(ds.tracks ?? []).map((t) => (
            <option key={t.name} value={t.name}>
              {t.name}
            </option>
          ))}
        </select>
      )}
      {rowTakesGroup(row, ds) && (
        <label className="insp-text small scope-line" title="Which cells this row shows">
          cells
          <ScopePicker value={row.scope} onChange={setScope} view={view} />
        </label>
      )}
      {row.kind === 'matrix' && !rowTakesGroup(row, ds) && row.source !== 'distance' && <div className="muted small">bulk map: all cells in the file</div>}
      {perCellMap && multi && <div className="muted small">several cells: their maps are summed (pseudo-bulk)</div>}
      {row.kind === 'track' && <TrackAggregateControl agg={row.agg ?? defaultAgg} multi={multi} onAgg={(a) => set('agg', a)} />}
      {row.kind === 'intervals' && (
        <select value={row.key ?? ''} onChange={(e) => set('key', e.target.value)} title="Interval table">
          {(ds.intervals ?? []).map((t) => (
            <option key={t.key} value={t.key}>
              {t.key}
            </option>
          ))}
        </select>
      )}
      <TextSetting label="height" value={row.height ? String(row.height) : ''} placeholder={row.kind === 'matrix' ? 'auto' : String(ROW_HEIGHT[row.kind])} onCommit={(v) => set('height', v)} title="Row height in px (empty = default)" />
    </div>
  )
}

/** Text input committed on blur / Enter (reverts when the value is refused). */
function TextSetting({ label, value, placeholder, title, onCommit }: { label: string; value: string; placeholder: string; title: string; onCommit(v: string): void }) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  return (
    <label className="insp-text small" title={title}>
      {label}
      <input
        className="num"
        value={text}
        placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          onCommit(text)
          setText(value)
        }}
        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
      />
    </label>
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
  // the pane's group, pinned cell, else the global focus (cell or group)
  const scope = usePaneScope(pane)
  const focusState = useFocusState()
  const nAll = useNCells()
  // every row's cells, resolved now ("same as view" → the pane's)
  const rowScopes = useMemo(() => rows.map((r) => resolveRowScope(r.scope, scope, focusState)), [rows, scope, focusState])
  const infos = useGroupInfos(rowScopes.map((sc) => (sc.kind === 'group' ? sc.group : null)))
  const byRef = useMemo(() => new Map(infos.filter((i): i is GroupInfo => !!i).map((i) => [i.ref, i])), [infos])
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

  // tracks: one request per scope (rows may have their own group)
  const names = useMemo(() => new Set((ds?.tracks ?? []).map((t) => t.name)), [ds])
  // one request per (cells, aggregate)
  const trackReqs = useMemo(() => {
    const m = new Map<string, { scope: Scope; agg: string; names: string[] }>()
    rows.forEach((r, i) => {
      if (r.kind !== 'track' || !r.track || !names.has(r.track)) return
      const sc = rowScopes[i]
      const agg = r.agg ?? pane.agg ?? 'mean'
      const k = `${scopeKey(sc)}|${agg}`
      const e = m.get(k) ?? { scope: sc, agg, names: [] }
      if (!e.names.includes(r.track)) e.names.push(r.track)
      m.set(k, e)
    })
    return m
  }, [rows, names, rowScopes, pane.agg])
  const trackSig = [...trackReqs].map(([k, e]) => `${k}=${e.names.join(',')}`).join('|')
  const [tracks, setTracks] = useState<Record<string, TrackData>>({})
  const [trackError, setTrackError] = useState<string | null>(null)
  useEffect(() => {
    if (!ds || !locus || !trackReqs.size) return
    let live = true
    const t = setTimeout(() => {
      for (const [k, e] of trackReqs) {
        const p = scopeParams(e.scope)
        fetchTracks(ds.id, e.names, locus, { cellId: p.cellId, group: p.group, agg: e.agg })
          .then((d) => live && (setTracks((m) => ({ ...m, [k]: d })), setTrackError(null)))
          .catch((err: Error) => live && setTrackError(err.message))
      }
    }, 180)
    return () => {
      live = false
      clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ds?.id, trackSig, locus?.chrom, locus?.start, locus?.end])

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
            <RowFrame key={r.id} row={r} height={heights[i]} setRows={setRows}>
              {r.kind === 'matrix' && (
                <MatrixRow
                  row={r}
                  height={heights[i]}
                  ds={ds}
                  width={W}
                  locus={locus}
                  scope={rowScopes[i]}
                  group={rowScopes[i].kind === 'group' ? (byRef.get((rowScopes[i] as { group: string }).group) ?? null) : null}
                  nAll={nAll}
                  guides={guides}
                  register={register}
                />
              )}
              {r.kind === 'track' && (
                <TrackRow
                  row={r}
                  height={heights[i]}
                  width={W}
                  locus={locus}
                  data={tracks[`${scopeKey(rowScopes[i])}|${r.agg ?? pane.agg ?? 'mean'}`] ?? null}
                  label={`${scopeText(rowScopes[i], rowScopes[i].kind === 'group' ? byRef.get((rowScopes[i] as { group: string }).group) : null, nAll)}${isMultiCell(rowScopes[i]) ? ` · ${r.agg ?? pane.agg ?? 'mean'}` : ''}`}
                  color={rowScopes[i].kind === 'group' ? (byRef.get((rowScopes[i] as { group: string }).group)?.color ?? null) : null}
                  register={register}
                />
              )}
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

/** Row chrome: a bottom edge to drag the height (settings live in the inspector). */
function RowFrame({
  row,
  height,
  setRows,
  children,
}: {
  row: GenomeRow
  height: number
  setRows(f: (rows: GenomeRow[]) => GenomeRow[]): void
  children: React.ReactNode
}) {
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
      <div className="gv-resize" onPointerDown={onResize} title="Drag to change the row height" />
    </div>
  )
}

function MatrixTools({ row, ds, set, multi }: { row: GenomeRow; ds: DatasetSummary; set(setting: RowSetting, value: string | boolean): void; multi: boolean }) {
  const maps = ds.contact_maps ?? []
  const map = maps.find((m) => m.key === row.source)
  return (
    <>
      <select value={row.source ?? ''} onChange={(e) => set('source', e.target.value)} title="Matrix source">
        {maps.map((m) => (
          <option key={m.key} value={m.key}>
            {m.label || m.key} ({m.kind})
          </option>
        ))}
        {hasCoords(ds) && <option value="distance">3-D distance</option>}
      </select>
      {map && map.resolutions.length > 1 && (
        <select value={row.resolution ?? ''} onChange={(e) => set('resolution', e.target.value)} title="Resolution">
          <option value="">auto resolution</option>
          {map.resolutions.map((r) => (
            <option key={r} value={r}>
              {fmtBp(r)}
            </option>
          ))}
        </select>
      )}
      {map && (
        <label className="check small" title="ICE-balanced values (if the cooler has weights)">
          <input type="checkbox" checked={row.balance ?? false} onChange={(e) => set('balance', e.target.checked)} /> balanced
        </label>
      )}
      {row.source === 'distance' && (
        <DistanceValueControls
          stat={row.stat ?? 'median'}
          multi={multi}
          onStat={(st) => set('stat', st)}
          threshold={
            <TextSetting
              label="threshold"
              value={row.threshold ? String(row.threshold) : ''}
              placeholder="default"
              title={`Contact distance threshold (${ds.xyz_unit ?? 'dataset unit'}); empty = server default`}
              onCommit={(v) => set('threshold', v)}
            />
          }
        />
      )}
      <TextSetting
        label="max dist"
        value={row.maxDist ? fmtBp(row.maxDist) : ''}
        placeholder="45°"
        title="Deepest genomic separation shown over the row height (e.g. 5M); empty = true 45°"
        onCommit={(v) => set('maxDist', v)}
      />
      <label className="check small" title="Diagonal at the top of the row (triangle pointing down)">
        <input type="checkbox" checked={!!row.flip} onChange={(e) => set('flip', e.target.checked)} /> flip
      </label>
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
  scope,
  group,
  nAll,
  guides,
  register,
}: {
  row: GenomeRow
  height: number
  ds: DatasetSummary
  width: number
  locus: Locus
  /** cells this row aggregates over (its own group, else the pane's scope) */
  scope: Scope
  /** the group in scope, resolved (name / colour) */
  group: GroupInfo | null
  /** number of cells of the dataset ("All cells · 47") */
  nAll: number
  guides: number[]
  register(id: string, f: Describe | null): void
}) {
  const { ref, style } = useRowCanvas(width, height)
  const map = (ds.contact_maps ?? []).find((m) => m.key === row.source)
  const isDist = row.source === 'distance'
  const valid = isDist ? hasCoords(ds) : !!map
  const needsCell = !!map?.per_cell
  const takesScope = needsCell || isDist
  // the row's cells: one cell, a group, or all (a per-cell map sums every cell's map)
  const cell = takesScope && scope.kind === 'cell' ? scope.cell : null
  const groupRef = takesScope && scope.kind === 'group' ? scope.group : needsCell && scope.kind === 'all' ? ALL_CELLS_REF : null
  const waiting = false
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
    const key = [ds.id, row.source, locus.chrom, locus.start, locus.end, row.resolution ?? '', row.balance ? 1 : 0, cell ?? '', groupRef ?? '', stat, row.threshold ?? ''].join('|')
    let live = true
    const load = () =>
      isDist
        ? fetchDistance(ds.id, locus, { cellId: cell, group: groupRef, stat, threshold: row.threshold ?? null })
        : fetchContacts(ds.id, row.source!, locus, { resolution: row.resolution ?? null, balance: row.balance ?? false, cell, group: groupRef })
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
  }, [ds.id, row.source, locus.chrom, locus.start, locus.end, row.resolution, row.balance, cell, groupRef, stat, row.threshold, valid, waiting])

  // a stale matrix of another chromosome must not be drawn on this axis
  const shown = mat && mat.header.chrom === locus.chrom && !waiting && valid ? mat : null
  const scale = shown ? scaleFor(shown.header.value) : 'contacts'
  const range = useMemo<[number, number]>(() => (shown ? matrixRange(shown.data, scale) : [0, 1]), [shown, scale])
  const colors = useMemo(() => (shown ? matrixPixels(shown, scale, range) : null), [shown, scale, range])
  const k = depthScale(row.maxDist, (locus.end - locus.start) / width, height)
  const geom: TriangleGeom = { start: locus.start, bpPerPx: (locus.end - locus.start) / width, height, k, flip: !!row.flip, maxDist: row.maxDist ?? null }
  const title = isDist ? `3-D distance · ${STAT_LABEL[stat]}` : map ? map.label || map.key : `unknown source “${row.source}”`
  const cellsNote = shown?.header.n_cells ? `${shown.header.n_cells} cells` : null
  const note = [
    // always say which cells: "All cells · 47", "selection · 10 cells", "cell 1_0_34"
    takesScope ? scopeText(scope, group, nAll) : 'bulk map',
    // fewer cells with data than in scope (e.g. cells without a map): say so
    takesScope && scope.kind !== 'cell' && cellsNote && shown?.header.n_cells !== (scope.kind === 'all' ? nAll : group?.cells?.length) ? `${cellsNote} with data` : null,
    shown?.header.resolution ? `${fmtBp(shown.header.resolution)} bins` : null,
    shown?.header.n_traces ? `${shown.header.n_traces} traces` : null,
    needsCell && groupRef && shown?.header.n_contacts ? `${fmtAxis(shown.header.n_contacts)} contacts (pseudo-bulk)` : null,
  ]
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
      let x = 6
      if (scope.kind === 'group' && group && takesScope) {
        g.fillStyle = group.color
        g.beginPath()
        g.arc(x + 4, top + 20, 4, 0, 2 * Math.PI)
        g.fill()
        x += 12
      }
      g.fillStyle = CHART.muted
      g.fillText(note, x, top + 14)
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
        ? `“${map?.label || map?.key}” holds one map per cell — select a cell or a group (left), or give this row a group`
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
  }, [shown, colors, width, height, locus, k, row.flip, row.maxDist, guides, title, note, error, waiting, valid, loading, group, groupRef])

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
  label,
  color,
  register,
}: {
  row: GenomeRow
  height: number
  width: number
  locus: Locus
  data: TrackData | null
  /** the row's cells ("All cells · 47", "cell 1_0_34", "Bergmann · 8 cells") */
  label: string
  /** group colour, when the cells are a group */
  color: string | null
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
    let x = 6 + g.measureText(name || '(no track)').width + 10
    if (color) {
      g.fillStyle = color
      g.beginPath()
      g.arc(x + 4, 8, 4, 0, 2 * Math.PI)
      g.fill()
      x += 12
    }
    g.fillStyle = CHART.muted
    g.fillText(label, x, 2)
  }, [vals, data, width, height, locus, name, label, color]) // eslint-disable-line react-hooks/exhaustive-deps
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

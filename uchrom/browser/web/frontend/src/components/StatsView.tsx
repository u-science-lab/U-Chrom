import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchCellValues, fetchRg, fetchScaling } from '../api'
import { cellRgb } from '../colors'
import { useFieldColors } from '../useFieldColors'
import { fmtBp } from '../filters'
import { logTicks, niceTicks } from '../genome'
import { nearestPoint } from '../render/embedding'
import { activeView, fieldKey, useStore } from '../store'
import { extent, fmtAxis, histogram, linear, logScale } from '../stats'
import type { CellField, CellValue, RgStats, ScalingStats } from '../types'
import { useLocus } from '../useLocus'
import { paneCell, updatePane, type Pane, type StatsKind } from '../workspace'
import { CHART, drawAxes, rgb, type Box } from './chart'
import { colourableFields, fieldLabel } from './format'
import { prepareCanvas, useSize } from './useSize'

const M = { left: 62, top: 14, right: 16, bottom: 44 }
const KIND_LABEL: Record<StatsKind, string> = {
  rg: 'Rg per trace',
  scaling: 'Distance vs genomic distance',
  hist: 'Cell field histogram',
  scatter: 'Field scatter',
}

function availableKinds(hasCoords: boolean, hasFields: boolean): StatsKind[] {
  return [...(hasCoords ? (['rg', 'scaling'] as StatsKind[]) : []), ...(hasFields ? (['hist', 'scatter'] as StatsKind[]) : [])]
}

export function resolveKind(pane: Pane, kinds: StatsKind[]): StatsKind | null {
  return pane.statsKind && kinds.includes(pane.statsKind) ? pane.statsKind : (kinds[0] ?? null)
}

function FieldSelect({ fields, value, onChange, title }: { fields: CellField[]; value: string; onChange(v: string): void; title: string }) {
  const groups = new Map<string, CellField[]>()
  for (const f of fields) groups.set(f.group, [...(groups.get(f.group) ?? []), f])
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} title={title}>
      {[...groups].map(([g, fs]) => (
        <optgroup key={g} label={g === 'rna' ? 'Gene' : g === 'cell' ? 'Property' : g}>
          {[...fs]
            .sort((a, b) => (g === 'cell' ? 0 : a.label.localeCompare(b.label)))
            .map((f) => (
              <option key={f.name} value={f.name}>
                {g === 'cell' ? fieldLabel(f.name) : f.label}
              </option>
            ))}
        </optgroup>
      ))}
    </select>
  )
}

function useStatsSetup(pane: Pane) {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const overviewField = useStore((s) => activeView(s).cellField)
  const hasCoords = ds?.has_coords !== false && (ds?.n_spots ?? 0) > 0
  // histogram / scatter axes are numeric: category fields colour the dots instead
  const fields = useMemo(() => colourableFields(ds?.cell_fields ?? []).filter((f) => f.kind !== 'category'), [ds])
  const kinds = availableKinds(hasCoords, fields.length > 0)
  const kind = resolveKind(pane, kinds)
  const fx = pane.fieldX && fields.some((f) => f.name === pane.fieldX) ? pane.fieldX : (overviewField && fields.some((f) => f.name === overviewField) ? overviewField : fields[0]?.name ?? null)
  const fy = pane.fieldY && fields.some((f) => f.name === pane.fieldY) ? pane.fieldY : (fields.find((f) => f.name !== fx)?.name ?? fx)
  return { ds, fields, kinds, kind, fx, fy }
}

/** Pane-header controls: which chart and its inputs. */
export function StatsControls({ pane }: { pane: Pane }) {
  const setWorkspace = useStore((s) => s.setWorkspace)
  const { fields, kinds, kind, fx, fy } = useStatsSetup(pane)
  const upd = (p: Partial<Pane>) => setWorkspace((w) => updatePane(w, pane.id, p))
  if (!kind) return null
  return (
    <>
      <select value={kind} onChange={(e) => upd({ statsKind: e.target.value as StatsKind })} title="Chart">
        {kinds.map((k) => (
          <option key={k} value={k}>
            {KIND_LABEL[k]}
          </option>
        ))}
      </select>
      {(kind === 'rg' || kind === 'scaling') && (
        <select value={pane.chromScope ?? 'all'} onChange={(e) => upd({ chromScope: e.target.value as 'all' | 'locus' })} title="Chromosomes">
          <option value="all">all chromosomes</option>
          <option value="locus">locus chromosome</option>
        </select>
      )}
      {(kind === 'hist' || kind === 'scatter') && fx && <FieldSelect fields={fields} value={fx} onChange={(v) => upd({ fieldX: v })} title="x field" />}
      {kind === 'scatter' && fy && (
        <>
          <span className="muted small">vs</span>
          <FieldSelect fields={fields} value={fy} onChange={(v) => upd({ fieldY: v })} title="y field" />
        </>
      )}
    </>
  )
}

/** Load (and cache in the store) the values of a cell field. */
function useFieldValues(datasetId: string | undefined, field: string | null): Map<string, CellValue> | null {
  const cached = useStore((s) => (datasetId && field ? s.cellValues[fieldKey(datasetId, field)] : undefined))
  const setCellValues = useStore((s) => s.setCellValues)
  useEffect(() => {
    if (!datasetId || !field || cached) return
    let live = true
    fetchCellValues(datasetId, field)
      .then((v) => live && setCellValues(datasetId, field, new Map(v.cell_ids.map((id, i) => [id, v.values[i]]))))
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [datasetId, field, cached, setCellValues])
  return cached ?? null
}

/**
 * Statistics views: Rg per trace, distance vs genomic separation, and
 * histogram / scatter of cell fields (click a scatter dot to focus the cell).
 */
export function StatsView({ pane }: { pane: Pane }) {
  const { ds, kind, fx, fy } = useStatsSetup(pane)
  const focus = useStore((s) => paneCell(pane, activeView(s).focusCell))
  const focusCell = useStore((s) => s.focusCell)
  const view = useStore(activeView)
  const cells = useStore((s) => (s.activeDatasetId ? s.cells[s.activeDatasetId] : undefined))
  const fieldColors = useFieldColors()
  const custom = useStore((s) => s.layers.find((l) => l.datasetId === s.activeDatasetId && l.parentId === null)?.style.color ?? '#ffffff')
  const { locus } = useLocus()
  const boxRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const size = useSize(boxRef)
  const chrom = (pane.chromScope ?? 'all') === 'locus' ? (locus?.chrom ?? null) : null
  const [rg, setRg] = useState<RgStats | null>(null)
  const [scaling, setScaling] = useState<{ pop: ScalingStats; cell: ScalingStats | null } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hover, setHover] = useState<{ x: number; y: number; text: string } | null>(null)
  const xs = useFieldValues(ds?.id, kind === 'hist' || kind === 'scatter' ? fx : null)
  const ys = useFieldValues(ds?.id, kind === 'scatter' ? fy : null)

  useEffect(() => {
    if (!ds || (kind !== 'rg' && kind !== 'scaling')) return
    let live = true
    setError(null)
    if (kind === 'rg') {
      fetchRg(ds.id, { chrom })
        .then((r) => live && setRg(r))
        .catch((e: Error) => live && setError(e.message))
    } else {
      Promise.all([fetchScaling(ds.id, { chrom }), focus ? fetchScaling(ds.id, { chrom, cellId: focus }).catch(() => null) : Promise.resolve(null)])
        .then(([pop, cell]) => live && setScaling({ pop, cell }))
        .catch((e: Error) => live && setError(e.message))
    }
    return () => {
      live = false
    }
  }, [ds?.id, kind, chrom, kind === 'scaling' ? focus : null]) // eslint-disable-line react-hooks/exhaustive-deps

  // scatter geometry for hit-testing
  const scatter = useMemo(() => {
    if (kind !== 'scatter' || !xs || !ys) return null
    const ids = [...xs.keys()].filter((id) => ys.has(id))
    const num = (v: CellValue | undefined) => (typeof v === 'number' ? v : null)
    const X = ids.map((id) => num(xs.get(id)))
    const Y = ids.map((id) => num(ys.get(id)))
    return { ids, X, Y }
  }, [kind, xs, ys])
  const plot: Box = { x: M.left, y: M.top, w: Math.max(10, size.w - M.left - M.right), h: Math.max(10, size.h - M.top - M.bottom) }
  const scatterPx = useMemo(() => {
    if (!scatter) return null
    const [x0, x1] = extent(scatter.X)
    const [y0, y1] = extent(scatter.Y)
    const sx = linear(x0, x1, plot.x, plot.x + plot.w)
    const sy = linear(y0, y1, plot.y + plot.h, plot.y)
    const px = new Float32Array(2 * scatter.ids.length)
    scatter.ids.forEach((_, i) => {
      const x = scatter.X[i]
      const y = scatter.Y[i]
      const ok = typeof x === 'number' && typeof y === 'number' && Number.isFinite(x) && Number.isFinite(y)
      px[2 * i] = ok ? sx(x!) : NaN
      px[2 * i + 1] = ok ? sy(y!) : NaN
    })
    return { px, x0, x1, y0, y1, sx, sy }
  }, [scatter, plot.x, plot.y, plot.w, plot.h])

  useEffect(() => {
    const cv = canvasRef.current
    if (!cv || !size.w || !size.h || !ds) return
    const g = prepareCanvas(cv, size.w, size.h)
    if (!g) return
    const unit = ds.xyz_unit ?? ''
    if (kind === 'rg' && rg) {
      const hist = histogram(rg.rg, 40)
      const top = Math.max(1, ...hist.counts)
      const sx = linear(hist.edges[0], hist.edges[hist.edges.length - 1], plot.x, plot.x + plot.w)
      const sy = linear(0, top, plot.y + plot.h, plot.y)
      g.fillStyle = 'rgba(92,157,237,0.75)'
      hist.counts.forEach((c, i) => {
        const x0 = sx(hist.edges[i])
        g.fillRect(x0 + 0.5, sy(c), Math.max(1, sx(hist.edges[i + 1]) - x0 - 1), plot.y + plot.h - sy(c))
      })
      drawAxes(g, plot, { ticks: niceTicks(hist.edges[0], hist.edges[hist.edges.length - 1]), pos: sx, fmt: fmtAxis, label: `radius of gyration${unit ? ` (${unit})` : ''}` }, { ticks: niceTicks(0, top, 4), pos: sy, fmt: fmtAxis, label: 'traces' })
      if (focus) {
        g.strokeStyle = '#ffffff'
        g.lineWidth = 2
        rg.cell_ids.forEach((c, i) => {
          const v = rg.rg[i]
          if (c !== focus || typeof v !== 'number') return
          const x = sx(v)
          g.beginPath()
          g.moveTo(x, plot.y)
          g.lineTo(x, plot.y + plot.h)
          g.stroke()
        })
        g.fillStyle = CHART.text
        g.font = CHART.font
        g.textAlign = 'right'
        g.fillText(`white: traces of cell ${focus}`, plot.x + plot.w, plot.y + 10)
      }
    } else if (kind === 'scaling' && scaling) {
      const all = [scaling.pop, ...(scaling.cell ? [scaling.cell] : [])]
      const sepAll = all.flatMap((s) => s.sep_bp).filter((v) => v > 0)
      const yAll = all.flatMap((s) => [...s.q25, ...s.q75, ...s.median]).filter((v): v is number => typeof v === 'number' && v > 0)
      if (!sepAll.length || !yAll.length) return
      const [sx0, sx1] = [Math.min(...sepAll), Math.max(...sepAll)]
      const [y0, y1] = [Math.min(...yAll), Math.max(...yAll)]
      const sx = logScale(sx0, sx1 > sx0 ? sx1 : sx0 * 10, plot.x, plot.x + plot.w)
      const sy = logScale(y0, y1 > y0 ? y1 : y0 * 10, plot.y + plot.h, plot.y)
      const line = (s: ScalingStats, color: string, band: boolean) => {
        const pts = s.sep_bp.map((x, i) => ({ x, m: s.median[i], a: s.q25[i], b: s.q75[i] })).filter((p) => p.x > 0 && typeof p.m === 'number' && p.m > 0)
        if (band) {
          g.fillStyle = 'rgba(92,157,237,0.18)'
          g.beginPath()
          pts.forEach((p, k) => (k ? g.lineTo(sx(p.x), sy(p.b ?? p.m!)) : g.moveTo(sx(p.x), sy(p.b ?? p.m!))))
          ;[...pts].reverse().forEach((p) => g.lineTo(sx(p.x), sy(p.a && p.a > 0 ? p.a : p.m!)))
          g.closePath()
          g.fill()
        }
        g.strokeStyle = color
        g.lineWidth = 2
        g.beginPath()
        pts.forEach((p, k) => (k ? g.lineTo(sx(p.x), sy(p.m!)) : g.moveTo(sx(p.x), sy(p.m!))))
        g.stroke()
      }
      line(scaling.pop, CHART.accent, true)
      if (scaling.cell) line(scaling.cell, '#ffffff', false)
      const yt = logTicks(y0, y1)
      drawAxes(
        g,
        plot,
        { ticks: logTicks(sx0, sx1), pos: sx, fmt: fmtBp, label: 'genomic separation (bp, log)' },
        { ticks: yt.length >= 2 ? yt : niceTicks(y0, y1, 4), pos: sy, fmt: fmtAxis, label: `median distance${unit ? ` (${unit})` : ''}, log` },
      )
      g.font = CHART.font
      g.textAlign = 'left'
      g.fillStyle = CHART.accent
      g.fillText('population (median, IQR band)', plot.x + 8, plot.y + 10)
      if (scaling.cell) {
        g.fillStyle = '#ffffff'
        g.fillText(`cell ${focus}`, plot.x + 8, plot.y + 24)
      }
    } else if (kind === 'hist' && xs && fx) {
      const hist = histogram(xs.values(), 40)
      const top = Math.max(1, ...hist.counts)
      const sx = linear(hist.edges[0], hist.edges[hist.edges.length - 1], plot.x, plot.x + plot.w)
      const sy = linear(0, top, plot.y + plot.h, plot.y)
      g.fillStyle = 'rgba(92,157,237,0.75)'
      hist.counts.forEach((c, i) => {
        const x0 = sx(hist.edges[i])
        g.fillRect(x0 + 0.5, sy(c), Math.max(1, sx(hist.edges[i + 1]) - x0 - 1), plot.y + plot.h - sy(c))
      })
      drawAxes(g, plot, { ticks: niceTicks(hist.edges[0], hist.edges[hist.edges.length - 1]), pos: sx, fmt: fmtAxis, label: fieldLabel(fx) }, { ticks: niceTicks(0, top, 4), pos: sy, fmt: fmtAxis, label: 'cells' })
      const fv = focus ? xs.get(focus) : undefined
      if (typeof fv === 'number') {
        g.strokeStyle = '#ffffff'
        g.lineWidth = 2
        g.beginPath()
        g.moveTo(sx(fv), plot.y)
        g.lineTo(sx(fv), plot.y + plot.h)
        g.stroke()
        g.fillStyle = CHART.text
        g.font = CHART.font
        g.textAlign = 'right'
        g.fillText(`cell ${focus}: ${fmtAxis(fv)}`, plot.x + plot.w, plot.y + 10)
      }
    } else if (kind === 'scatter' && scatter && scatterPx && fx && fy) {
      const cellIndex = new Map((cells ?? []).map((c, i) => [c.cell_id, i]))
      const opts = { cellIndex, ...fieldColors }
      const n = scatter.ids.length
      const r = n > 3000 ? 1.8 : n > 800 ? 2.6 : 3.6
      for (let i = 0; i < n; i++) {
        const x = scatterPx.px[2 * i]
        if (Number.isNaN(x)) continue
        g.globalAlpha = focus && scatter.ids[i] !== focus ? 0.6 : 0.95
        g.fillStyle = rgb(cellRgb(scatter.ids[i], view.overviewColor, custom, opts))
        g.beginPath()
        g.arc(x, scatterPx.px[2 * i + 1], r, 0, 2 * Math.PI)
        g.fill()
      }
      g.globalAlpha = 1
      const fi = focus ? scatter.ids.indexOf(focus) : -1
      if (fi >= 0 && !Number.isNaN(scatterPx.px[2 * fi])) {
        g.strokeStyle = '#ffffff'
        g.lineWidth = 2
        g.beginPath()
        g.arc(scatterPx.px[2 * fi], scatterPx.px[2 * fi + 1], r * 2 + 2, 0, 2 * Math.PI)
        g.stroke()
      }
      drawAxes(
        g,
        plot,
        { ticks: niceTicks(scatterPx.x0, scatterPx.x1), pos: scatterPx.sx, fmt: fmtAxis, label: fieldLabel(fx) },
        { ticks: niceTicks(scatterPx.y0, scatterPx.y1, 4), pos: scatterPx.sy, fmt: fmtAxis, label: fieldLabel(fy) },
      )
    }
  }, [kind, rg, scaling, xs, fx, fy, scatter, scatterPx, size.w, size.h, focus, cells, fieldColors, view.overviewColor, custom, ds]) // eslint-disable-line react-hooks/exhaustive-deps

  const hit = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!scatter || !scatterPx) return -1
    const rect = e.currentTarget.getBoundingClientRect()
    return nearestPoint(scatterPx.px, e.clientX - rect.left, e.clientY - rect.top, 8)
  }
  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const i = hit(e)
    if (i < 0 || !scatter) return setHover(null)
    const rect = e.currentTarget.getBoundingClientRect()
    setHover({ x: e.clientX - rect.left, y: e.clientY - rect.top, text: `cell ${scatter.ids[i]} · ${fmtAxis(scatter.X[i] ?? NaN)}, ${fmtAxis(scatter.Y[i] ?? NaN)}` })
  }
  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const i = hit(e)
    if (i >= 0 && scatter) focusCell(scatter.ids[i])
  }

  let message: string | null = null
  if (!kind) message = 'Nothing to chart: this dataset has neither 3-D traces nor numeric cell fields.'
  else if (kind === 'scaling' && scaling && !scaling.pop.sep_bp.length) message = 'No trace pairs to measure.'
  return (
    <div ref={boxRef} className="genome-view">
      {message && <div className="muted pane-empty">{message}</div>}
      {error && <div className="error pane-error">{error}</div>}
      <canvas ref={canvasRef} onMouseMove={onMove} onMouseLeave={() => setHover(null)} onClick={onClick} style={{ cursor: hover ? 'pointer' : 'default' }} />
      {chrom && (kind === 'rg' || kind === 'scaling') && <div className="pane-badge small">{chrom}</div>}
      {hover && (
        <div className="embedding-tip" style={{ left: Math.min(hover.x + 12, size.w - 200), top: hover.y + 12 }}>
          {hover.text}
        </div>
      )}
    </div>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchCellValues, fetchRg, fetchScaling } from '../api'
import { cellRgb } from '../colors'
import { useFieldColors } from '../useFieldColors'
import { fmtBp } from '../filters'
import { logTicks, niceTicks } from '../genome'
import { nearestPoint } from '../render/embedding'
import { scopeLabel, type GroupInfo } from '../groups'
import { activeView, fieldKey, useStore } from '../store'
import { extent, fmtAxis, histogram, linear, logScale } from '../stats'
import type { CellField, CellValue, RgStats, ScalingStats } from '../types'
import { useLocus } from '../useLocus'
import { useTheme } from '../useTheme'
import { useGroupChoices, useGroupInfos, usePaneScope } from '../useGroups'
import { updatePane, type Pane, type StatsKind } from '../workspace'
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
      {(kind === 'rg' || kind === 'scaling' || kind === 'hist') && <CompareGroups pane={pane} />}
    </>
  )
}

/** Inspector checklist: groups overlaid on the Rg / scaling chart, each in its colour. */
function CompareGroups({ pane }: { pane: Pane }) {
  const setWorkspace = useStore((s) => s.setWorkspace)
  const choices = useGroupChoices()
  const refs = [...choices.fields.flatMap((f) => f.refs), ...choices.saved]
  const infos = useGroupInfos(refs)
  const on = new Set(pane.compareGroups ?? [])
  if (!refs.length) return null
  const toggle = (r: string) =>
    setWorkspace((w) => updatePane(w, pane.id, { compareGroups: on.has(r) ? [...on].filter((x) => x !== r) : [...on, r] }))
  return (
    <div className="compare-groups">
      <div className="muted small">
        compare groups
        {on.size > 0 && (
          <button className="link" onClick={() => setWorkspace((w) => updatePane(w, pane.id, { compareGroups: [] }))}>
            none
          </button>
        )}
      </div>
      <ul className="legend-list">
        {refs.map((r, i) => {
          const info = infos[i]
          return (
            <li key={r} className={on.has(r) ? '' : 'off'} onClick={() => toggle(r)} title={on.has(r) ? 'Remove from the chart' : 'Overlay on the chart'}>
              <span className="swatch round" style={{ background: info?.color ?? '#888' }} />
              <span>{info?.name ?? r}</span>
              <span className="muted small">{info?.cells ? info.cells.length : ''}</span>
            </li>
          )
        })}
      </ul>
    </div>
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
  const scope = usePaneScope(pane)
  const focus = scope.kind === 'cell' ? scope.cell : null
  const baseGroup = scope.kind === 'group' ? scope.group : null
  const compare = useMemo(() => (pane.compareGroups ?? []).filter((g) => g !== baseGroup), [pane.compareGroups, baseGroup])
  const infos = useGroupInfos([baseGroup, ...compare])
  const baseInfo = infos[0]
  const compareInfos = useMemo(() => infos.slice(1), [infos])
  const focusCell = useStore((s) => s.focusCell)
  const view = useStore(activeView)
  const cells = useStore((s) => (s.activeDatasetId ? s.cells[s.activeDatasetId] : undefined))
  const fieldColors = useFieldColors()
  const pal = useTheme()
  const custom = useStore((s) => s.layers.find((l) => l.datasetId === s.activeDatasetId && l.parentId === null)?.style.color ?? '#ffffff')
  const { locus } = useLocus()
  const boxRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const size = useSize(boxRef)
  const chrom = (pane.chromScope ?? 'all') === 'locus' ? (locus?.chrom ?? null) : null
  const [rg, setRg] = useState<RgStats | null>(null)
  const [scaling, setScaling] = useState<{ pop: ScalingStats; cell: ScalingStats | null } | null>(null)
  // overlaid groups: ref → stats of the current kind
  const [groupRg, setGroupRg] = useState<Record<string, RgStats>>({})
  const [groupScaling, setGroupScaling] = useState<Record<string, ScalingStats>>({})
  const [error, setError] = useState<string | null>(null)
  const [hover, setHover] = useState<{ x: number; y: number; text: string } | null>(null)
  const xs = useFieldValues(ds?.id, kind === 'hist' || kind === 'scatter' ? fx : null)
  const ys = useFieldValues(ds?.id, kind === 'scatter' ? fy : null)

  useEffect(() => {
    if (!ds || (kind !== 'rg' && kind !== 'scaling')) return
    let live = true
    setError(null)
    // the base is the pane's group when it has one, else every cell
    if (kind === 'rg') {
      fetchRg(ds.id, { chrom, group: baseGroup })
        .then((r) => live && setRg(r))
        .catch((e: Error) => live && setError(e.message))
    } else {
      Promise.all([fetchScaling(ds.id, { chrom, group: baseGroup }), focus ? fetchScaling(ds.id, { chrom, cellId: focus }).catch(() => null) : Promise.resolve(null)])
        .then(([pop, cell]) => live && setScaling({ pop, cell }))
        .catch((e: Error) => live && setError(e.message))
    }
    return () => {
      live = false
    }
  }, [ds?.id, kind, chrom, baseGroup, kind === 'scaling' ? focus : null]) // eslint-disable-line react-hooks/exhaustive-deps

  const compareKey = compare.join('\u0001')
  useEffect(() => {
    if (!ds || (kind !== 'rg' && kind !== 'scaling')) return
    let live = true
    setGroupRg({})
    setGroupScaling({})
    for (const g of compare) {
      if (kind === 'rg')
        fetchRg(ds.id, { chrom, group: g })
          .then((r) => live && setGroupRg((m) => ({ ...m, [g]: r })))
          .catch((e: Error) => live && setError(e.message))
      else
        fetchScaling(ds.id, { chrom, group: g })
          .then((r) => live && setGroupScaling((m) => ({ ...m, [g]: r })))
          .catch((e: Error) => live && setError(e.message))
    }
    return () => {
      live = false
    }
  }, [ds?.id, kind, chrom, compareKey]) // eslint-disable-line react-hooks/exhaustive-deps

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
      const overlays = compare
        .map((g, i) => ({ info: compareInfos[i], data: groupRg[g] }))
        .filter((o): o is { info: GroupInfo | null; data: RgStats } => !!o.data)
      const baseLabel = baseGroup ? scopeLabel({ kind: 'group', group: baseGroup }, baseInfo) : 'all cells'
      const allVals = [...rg.rg, ...overlays.flatMap((o) => o.data.rg)]
      const lo = Math.min(...allVals.filter((v): v is number => typeof v === 'number'))
      const hi = Math.max(...allVals.filter((v): v is number => typeof v === 'number'))
      const range: [number, number] | undefined = Number.isFinite(lo) && Number.isFinite(hi) && hi > lo ? [lo, hi] : undefined
      const hist = histogram(rg.rg, 40, range)
      // with groups overlaid, every histogram is a fraction of its traces so sizes compare
      const frac = overlays.length > 0
      const norm = (h: { counts: number[] }) => {
        const total = h.counts.reduce((a, b) => a + b, 0) || 1
        return frac ? h.counts.map((c) => c / total) : h.counts
      }
      const baseCounts = norm(hist)
      const overlayHists = overlays.map((o) => ({ ...o, counts: norm(histogram(o.data.rg, 40, range ?? [hist.edges[0], hist.edges[hist.edges.length - 1]])) }))
      const top = Math.max(frac ? 1e-9 : 1, ...baseCounts, ...overlayHists.flatMap((o) => o.counts))
      const sx = linear(hist.edges[0], hist.edges[hist.edges.length - 1], plot.x, plot.x + plot.w)
      const sy = linear(0, top, plot.y + plot.h, plot.y)
      g.fillStyle = baseGroup && baseInfo ? baseInfo.color : pal.bar
      g.globalAlpha = frac ? 0.35 : baseGroup ? 0.8 : 1
      baseCounts.forEach((c, i) => {
        const x0 = sx(hist.edges[i])
        g.fillRect(x0 + 0.5, sy(c), Math.max(1, sx(hist.edges[i + 1]) - x0 - 1), plot.y + plot.h - sy(c))
      })
      g.globalAlpha = 1
      for (const o of overlayHists) {
        g.strokeStyle = o.info?.color ?? pal.strong
        g.lineWidth = 2
        g.beginPath()
        o.counts.forEach((c, i) => {
          const x0 = sx(hist.edges[i])
          const x1 = sx(hist.edges[i + 1])
          if (i === 0) g.moveTo(x0, sy(0))
          g.lineTo(x0, sy(c))
          g.lineTo(x1, sy(c))
          if (i === o.counts.length - 1) g.lineTo(x1, sy(0))
        })
        g.stroke()
      }
      drawAxes(
        g,
        plot,
        { ticks: niceTicks(hist.edges[0], hist.edges[hist.edges.length - 1]), pos: sx, fmt: fmtAxis, label: `radius of gyration${unit ? ` (${unit})` : ''}` },
        { ticks: niceTicks(0, top, 4), pos: sy, fmt: fmtAxis, label: frac ? 'fraction of traces' : 'traces' },
      )
      // legend: base + each group with n cells / traces and its median
      const med = (v: (number | null)[]) => {
        const x = v.filter((y): y is number => typeof y === 'number').sort((a, b) => a - b)
        return x.length ? x[Math.floor((x.length - 1) / 2)] : NaN
      }
      g.font = CHART.font
      g.textAlign = 'right'
      const legend = [
        { color: baseGroup && baseInfo ? baseInfo.color : CHART.accent, text: `${baseLabel}: median ${fmtAxis(med(rg.rg))} · ${rg.rg.length} traces${rg.n_cells ? ` / ${rg.n_cells} cells` : ''}` },
        ...overlays.map((o) => ({ color: o.info?.color ?? pal.strong, text: `${o.info?.name ?? o.data.group}: median ${fmtAxis(med(o.data.rg))} · ${o.data.rg.length} traces${o.data.n_cells ? ` / ${o.data.n_cells} cells` : ''}` })),
      ]
      legend.forEach((l, i) => {
        g.fillStyle = l.color
        g.fillText(l.text, plot.x + plot.w, plot.y + 10 + 14 * i)
      })
      if (focus) {
        g.strokeStyle = pal.strong
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
        g.fillText(`${pal.name === 'dark' ? 'white' : 'dark'} lines: traces of cell ${focus}`, plot.x + plot.w, plot.y + 10 + 14 * legend.length)
      }
    } else if (kind === 'scaling' && scaling) {
      const overlays = compare
        .map((gr, i) => ({ info: compareInfos[i], data: groupScaling[gr] }))
        .filter((o): o is { info: GroupInfo | null; data: ScalingStats } => !!o.data && o.data.sep_bp.length > 0)
      const all = [scaling.pop, ...(scaling.cell ? [scaling.cell] : []), ...overlays.map((o) => o.data)]
      const sepAll = all.flatMap((s) => s.sep_bp).filter((v) => v > 0)
      const yAll = all.flatMap((s) => [...s.q25, ...s.q75, ...s.median]).filter((v): v is number => typeof v === 'number' && v > 0)
      if (!sepAll.length || !yAll.length) return
      const [sx0, sx1] = [Math.min(...sepAll), Math.max(...sepAll)]
      const [y0, y1] = [Math.min(...yAll), Math.max(...yAll)]
      const sx = logScale(sx0, sx1 > sx0 ? sx1 : sx0 * 10, plot.x, plot.x + plot.w)
      const sy = logScale(y0, y1 > y0 ? y1 : y0 * 10, plot.y + plot.h, plot.y)
      const line = (s: ScalingStats, color: string, band: boolean, bandColor = pal.band) => {
        const pts = s.sep_bp.map((x, i) => ({ x, m: s.median[i], a: s.q25[i], b: s.q75[i] })).filter((p) => p.x > 0 && typeof p.m === 'number' && p.m > 0)
        if (band) {
          g.fillStyle = bandColor
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
      const baseColor = baseGroup && baseInfo ? baseInfo.color : CHART.accent
      line(scaling.pop, baseColor, true, baseGroup && baseInfo ? baseInfo.color.replace('rgb(', 'rgba(').replace(')', ', 0.18)') : undefined)
      for (const o of overlays) line(o.data, o.info?.color ?? pal.strong, false)
      if (scaling.cell) line(scaling.cell, pal.strong, false)
      const yt = logTicks(y0, y1)
      drawAxes(
        g,
        plot,
        { ticks: logTicks(sx0, sx1), pos: sx, fmt: fmtBp, label: 'genomic separation (bp, log)' },
        { ticks: yt.length >= 2 ? yt : niceTicks(y0, y1, 4), pos: sy, fmt: fmtAxis, label: `median distance${unit ? ` (${unit})` : ''}, log` },
      )
      g.font = CHART.font
      g.textAlign = 'left'
      const legend = [
        { color: baseColor, text: `${baseGroup ? scopeLabel({ kind: 'group', group: baseGroup }, baseInfo) : 'population'} (median, IQR band)` },
        ...overlays.map((o) => ({ color: o.info?.color ?? pal.strong, text: `${o.info?.name ?? o.data.group}${o.data.n_cells ? ` (${o.data.n_cells} cells)` : ''}` })),
        ...(scaling.cell ? [{ color: pal.strong, text: `cell ${focus}` }] : []),
      ]
      legend.forEach((l, i) => {
        g.fillStyle = l.color
        g.fillText(l.text, plot.x + 8, plot.y + 10 + 14 * i)
      })
    } else if (kind === 'hist' && xs && fx) {
      // the base is the pane's group when it has one, else every cell; compared groups are overlaid
      const valuesOf = (ids: readonly string[] | null) => (ids ? ids.map((id) => xs.get(id)) : [...xs.values()])
      const baseVals = valuesOf(baseGroup && baseInfo?.cells ? baseInfo.cells : null)
      const overlays = compare
        .map((_, i) => ({ info: compareInfos[i], vals: compareInfos[i]?.cells ? valuesOf(compareInfos[i]!.cells!) : null }))
        .filter((o): o is { info: GroupInfo | null; vals: CellValue[] } => !!o.vals)
      const nums = (v: readonly (CellValue | undefined)[]) => v.filter((x): x is number => typeof x === 'number' && Number.isFinite(x))
      const all = nums([...baseVals, ...overlays.flatMap((o) => o.vals)])
      const range: [number, number] | undefined = all.length ? [Math.min(...all), Math.max(...all)] : undefined
      // few cells → few bins (about 2√n, 8–40)
      const nbins = Math.max(8, Math.min(40, Math.round(2 * Math.sqrt(all.length))))
      const hist = histogram(baseVals, nbins, range)
      const frac = overlays.length > 0
      const norm = (c: number[]) => {
        const t = c.reduce((a, b) => a + b, 0) || 1
        return frac ? c.map((x) => x / t) : c
      }
      const baseCounts = norm(hist.counts)
      const overlayHists = overlays.map((o) => ({ ...o, counts: norm(histogram(o.vals, nbins, range).counts) }))
      const top = Math.max(frac ? 1e-9 : 1, ...baseCounts, ...overlayHists.flatMap((o) => o.counts))
      const sx = linear(hist.edges[0], hist.edges[hist.edges.length - 1], plot.x, plot.x + plot.w)
      const sy = linear(0, top, plot.y + plot.h, plot.y)
      g.fillStyle = baseGroup && baseInfo ? baseInfo.color : pal.bar
      g.globalAlpha = frac ? 0.35 : 1
      baseCounts.forEach((c, i) => {
        const x0 = sx(hist.edges[i])
        g.fillRect(x0 + 0.5, sy(c), Math.max(1, sx(hist.edges[i + 1]) - x0 - 1), plot.y + plot.h - sy(c))
      })
      g.globalAlpha = 1
      for (const o of overlayHists) {
        g.strokeStyle = o.info?.color ?? pal.strong
        g.lineWidth = 2
        g.beginPath()
        o.counts.forEach((c, i) => {
          const x0 = sx(hist.edges[i])
          const x1 = sx(hist.edges[i + 1])
          if (i === 0) g.moveTo(x0, sy(0))
          g.lineTo(x0, sy(c))
          g.lineTo(x1, sy(c))
          if (i === o.counts.length - 1) g.lineTo(x1, sy(0))
        })
        g.stroke()
      }
      drawAxes(g, plot, { ticks: niceTicks(hist.edges[0], hist.edges[hist.edges.length - 1]), pos: sx, fmt: fmtAxis, label: fieldLabel(fx) }, { ticks: niceTicks(0, top, 4), pos: sy, fmt: fmtAxis, label: frac ? 'fraction of cells' : 'cells' })
      if (frac) {
        const med = (v: number[]) => {
          const a = [...v].sort((x, y) => x - y)
          return a.length ? (a.length % 2 ? a[(a.length - 1) / 2] : (a[a.length / 2 - 1] + a[a.length / 2]) / 2) : NaN
        }
        const baseLabel = baseGroup ? scopeLabel({ kind: 'group', group: baseGroup }, baseInfo) : 'all cells'
        const legend = [
          { color: pal.text, text: `${baseLabel}: median ${fmtAxis(med(nums(baseVals)))} · ${nums(baseVals).length} cells` },
          ...overlays.map((o) => ({ color: o.info?.color ?? pal.strong, text: `${o.info?.name ?? 'group'}: median ${fmtAxis(med(nums(o.vals)))} · ${nums(o.vals).length} cells` })),
        ]
        g.font = `11px ${getComputedStyle(document.body).fontFamily}`
        g.textAlign = 'right'
        legend.forEach((l, i) => {
          g.fillStyle = l.color
          g.fillText(l.text, plot.x + plot.w - 4, plot.y + 10 + 14 * i)
        })
        g.textAlign = 'left'
      }
      const fv = focus ? xs.get(focus) : undefined
      if (typeof fv === 'number') {
        g.strokeStyle = pal.strong
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
        if (pal.dotRing !== 'transparent') {
          g.strokeStyle = pal.dotRing
          g.lineWidth = 0.6
          g.stroke()
        }
      }
      g.globalAlpha = 1
      const fi = focus ? scatter.ids.indexOf(focus) : -1
      if (fi >= 0 && !Number.isNaN(scatterPx.px[2 * fi])) {
        g.strokeStyle = pal.strong
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
  }, [kind, rg, scaling, xs, fx, fy, scatter, scatterPx, size.w, size.h, focus, cells, fieldColors, view.overviewColor, custom, ds, groupRg, groupScaling, baseInfo, compareInfos, pal]) // eslint-disable-line react-hooks/exhaustive-deps

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
      {(kind === 'rg' || kind === 'scaling') && (chrom || baseGroup) && (
        <div className="pane-badge small">{[chrom, baseGroup ? scopeLabel(scope, baseInfo) : null].filter(Boolean).join(' · ')}</div>
      )}
      {hover && (
        <div className="embedding-tip" style={{ left: Math.min(hover.x + 12, size.w - 200), top: hover.y + 12 }}>
          {hover.text}
        </div>
      )}
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { fetchContacts, fetchDistance } from '../api'
import { fmtBp } from '../filters'
import { clampLocus, fmtPos, isGenome, niceTicks, panLocus, queryRegion } from '../genome'
import { rasterMatrix } from '../genomeRows'
import { binAt, matrixViewport, zoomMatrixView, type MatrixData } from '../matrix'
import { ColorScaleControls, useMatrixScale } from './ColorScaleControls'
import { ALL_CELLS_REF, isMultiCell, scopeText } from '../groups'
import { DistanceValueControls } from './AggregateControls'
import { useNCells } from './ScopePicker'
import { useStore } from '../store'
import { useGroupInfo, usePaneScope } from '../useGroups'
import { fmtAxis } from '../stats'
import type { ContactMapInfo } from '../types'
import { useLocus } from '../useLocus'
import { useTheme } from '../useTheme'
import { updatePane, type Pane } from '../workspace'
import { CHART, drawColorRamp } from './chart'
import { prepareCanvas, useSize } from './useSize'
import { Select } from './Select'

/** The matrix source of a pane: a contact-map key or 'distance'. */
export function resolveSource(pane: Pane, maps: ContactMapInfo[], hasCoords: boolean): string | null {
  if (pane.source === 'distance' && hasCoords) return 'distance'
  if (pane.source && maps.some((m) => m.key === pane.source)) return pane.source
  return maps[0]?.key ?? (hasCoords ? 'distance' : null)
}

/** Pane-header controls: source, and per source balance / resolution or statistic. */
export function MatrixControls({ pane }: { pane: Pane }) {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const setWorkspace = useStore((s) => s.setWorkspace)
  const maps = ds?.contact_maps ?? []
  const hasCoords = ds?.has_coords !== false && (ds?.n_spots ?? 0) > 0
  const source = resolveSource(pane, maps, hasCoords)
  const map = maps.find((m) => m.key === source)
  const upd = (p: Partial<Pane>) => setWorkspace((w) => updatePane(w, pane.id, p))
  const scope = usePaneScope(pane)
  const auto = useStore((s) => s.matrixAuto[pane.id])
  if (!source) return null
  return (
    <>
      <Select value={source} onChange={(e) => upd({ source: e.target.value, resolution: null })} title="Matrix source">
        {maps.map((m) => (
          <option key={m.key} value={m.key}>
            {m.label || m.key} ({m.kind})
          </option>
        ))}
        {hasCoords && <option value="distance">3-D distance</option>}
      </Select>
      {map && map.resolutions.length > 1 && (
        <Select value={pane.resolution ?? ''} onChange={(e) => upd({ resolution: e.target.value ? +e.target.value : null })} title="Resolution">
          <option value="">auto</option>
          {map.resolutions.map((r) => (
            <option key={r} value={r}>
              {fmtBp(r)}
            </option>
          ))}
        </Select>
      )}
      {map && (
        <label className="check small" title="ICE-balanced values (if the cooler has weights)">
          <input type="checkbox" checked={pane.balance ?? false} onChange={(e) => upd({ balance: e.target.checked })} /> balanced
        </label>
      )}
      {source === 'distance' && (
        <DistanceValueControls
          stat={pane.stat ?? 'median'}
          multi={isMultiCell(scope)}
          onStat={(stat) => upd({ stat })}
          threshold={
            <input
              className="num"
              type="number"
              step="any"
              min={0}
              placeholder="threshold"
              value={pane.threshold ?? ''}
              onChange={(e) => upd({ threshold: e.target.value === '' ? null : Math.max(0, +e.target.value) })}
              title={`Distance threshold (${ds?.xyz_unit ?? 'dataset unit'}); empty = server default`}
            />
          }
        />
      )}
      <ColorScaleControls
        kind={source === 'distance' ? ((pane.stat ?? 'median') === 'contact' ? 'frequency' : 'distance') : 'contacts'}
        value={pane.color}
        onChange={(color) => upd({ color })}
        auto={auto}
      />
    </>
  )
}

/**
 * Heatmap of a contact map (cool / mcool / scool) or of pairwise 3-D distances filling the pane
 * (HiGlass square mode): one bp per px on both axes, x = the shared locus, y centred on it (drag
 * pans both, the wheel zooms about the pointer, double-click puts the diagonal back in the
 * middle).  Axes, colour scale and notes float over the map.
 */
export function MatrixView({ pane }: { pane: Pane }) {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const scope = usePaneScope(pane)
  const groupInfo = useGroupInfo(scope.kind === 'group' ? scope.group : null)
  const pal = useTheme()
  const { locus, ext, setLocus } = useLocus()
  const layout = isGenome(locus) ? ext?.layout : undefined
  const boxRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const size = useSize(boxRef)
  const maps = ds?.contact_maps ?? []
  const hasCoords = ds?.has_coords !== false && (ds?.n_spots ?? 0) > 0
  const source = resolveSource(pane, maps, hasCoords)
  const map = maps.find((m) => m.key === source)
  const [mat, setMat] = useState<MatrixData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [hover, setHover] = useState<{ x: number; y: number; text: string } | null>(null)
  // the pane's own vertical pan (bp from the locus centre); another chromosome: back on the diagonal
  const [yOff, setYOff] = useState(0)
  useEffect(() => setYOff(0), [locus?.chrom])

  const needsCell = !!map?.per_cell
  const takesScope = needsCell || source === 'distance'
  const nAll = useNCells()
  const cell = takesScope && scope.kind === 'cell' ? scope.cell : null
  // per-cell map + group / all cells → pseudo-bulk; distance + group → statistic over its traces
  const group = takesScope && scope.kind === 'group' ? scope.group : needsCell && scope.kind === 'all' ? ALL_CELLS_REF : null
  const W = size.w
  const H = size.h
  const vp = locus && W > 0 && H > 0 ? matrixViewport(locus, W, H, yOff) : null

  // the data behind both axes (one chromosome), or the whole genome
  const region = !locus || !vp
    ? null
    : isGenome(locus)
      ? queryRegion(locus)
      : {
          chrom: locus.chrom,
          start: Math.round(Math.max(ext?.start ?? 0, Math.min(vp.xStart, vp.yStart))),
          end: Math.round(Math.min(ext?.end ?? Infinity, Math.max(vp.xEnd, vp.yEnd))),
        }
  const rkey = region ? `${region.chrom}|${region.start ?? ''}|${region.end ?? ''}` : ''
  useEffect(() => {
    if (!ds || !region || !source) return
    let live = true
    const t = setTimeout(() => {
      setLoading(true)
      const req =
        source === 'distance'
          ? fetchDistance(ds.id, region, { cellId: cell, group, stat: pane.stat ?? 'median', threshold: pane.threshold ?? null })
          : fetchContacts(ds.id, source, region, { resolution: pane.resolution ?? null, balance: pane.balance ?? false, cell, group })
      req
        .then((m) => live && (setMat(m), setError(null)))
        .catch((e: Error) => live && (setError(e.message), setMat(null)))
        .finally(() => live && setLoading(false))
    }, 200)
    return () => {
      live = false
      clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ds?.id, source, rkey, cell, group, pane.stat, pane.threshold, pane.resolution, pane.balance])

  const cscale = useMatrixScale(mat, pane.color, pane.id)
  const scale = cscale.kind ?? 'contacts'
  // a stale map of another chromosome is not drawn on these axes
  const shown = mat && locus && mat.header.chrom === locus.chrom ? mat : null

  useEffect(() => {
    const cv = canvasRef.current
    if (!cv || !W || !H) return
    const g = prepareCanvas(cv, W, H)
    if (!g || !vp) return
    if (shown && cscale.pixels) {
      const dpr = cv.width / W
      const h = shown.header
      const px = rasterMatrix(cv.width, cv.height, { xStart: vp.xStart, yStart: vp.yStart, xBpPerPx: vp.bpPerPx / dpr, yBpPerPx: vp.bpPerPx / dpr }, h.bin_starts, h.bin_ends, cscale.pixels)
      g.putImageData(new ImageData(px as unknown as Uint8ClampedArray<ArrayBuffer>, cv.width, cv.height), 0, 0)
    }
    const X = (bp: number) => (bp - vp.xStart) / vp.bpPerPx
    const Y = (bp: number) => (bp - vp.yStart) / vp.bpPerPx
    // whole genome: the chromosome grid
    if (layout) {
      g.strokeStyle = pal.guide
      g.lineWidth = 1
      for (const c of layout) {
        if (c.offset <= 0) continue
        const x = Math.round(X(c.offset)) + 0.5
        const y = Math.round(Y(c.offset)) + 0.5
        if (x > 0 && x < W) (g.beginPath(), g.moveTo(x, 0), g.lineTo(x, H), g.stroke())
        if (y > 0 && y < H) (g.beginPath(), g.moveTo(0, y), g.lineTo(W, y), g.stroke())
      }
    }
    // axes floating over the map: a translucent band along the top and the left edge
    const band = 18
    g.save()
    g.globalAlpha = 0.78
    g.fillStyle = pal.viewportBg
    g.fillRect(0, 0, W, band)
    g.fillRect(0, band, AXIS_W, H - band)
    g.restore()
    g.font = CHART.font
    g.fillStyle = CHART.text
    const labelsX: [number, string][] = []
    const labelsY: [number, string][] = []
    if (layout) {
      for (const c of layout) {
        const mid = c.offset + c.length / 2
        labelsX.push([X(mid), c.name])
        labelsY.push([Y(mid), c.name])
      }
    } else {
      for (const t of niceTicks(vp.xStart, vp.xEnd, Math.max(2, Math.floor(W / 110)))) labelsX.push([X(t), fmtBp(t)])
      for (const t of niceTicks(vp.yStart, vp.yEnd, Math.max(2, Math.floor(H / 70)))) labelsY.push([Y(t), fmtBp(t)])
    }
    g.textBaseline = 'middle'
    g.textAlign = 'center'
    let last = -Infinity
    for (const [x, text] of labelsX) {
      const w = g.measureText(text).width
      if (x - w / 2 < AXIS_W + 2 || x + w / 2 > W - 2 || x - w / 2 < last + 6) continue
      g.fillText(text, x, band / 2)
      last = x + w / 2
    }
    g.textAlign = 'right'
    last = -Infinity
    for (const [y, text] of labelsY) {
      if (y < band + 7 || y > H - 7 || y < last + 14) continue
      g.fillText(text.length > 7 ? text.slice(0, 7) : text, AXIS_W - 4, y)
      last = y
    }
  }, [shown, cscale.pixels, W, H, vp?.xStart, vp?.yStart, vp?.bpPerPx, layout, pal]) // eslint-disable-line react-hooks/exhaustive-deps

  // pan (drag) and zoom (wheel) — both axes at one bp per px
  const cur = useRef({ locus, yOff, ext, W, H })
  cur.current = { locus, yOff, ext, W, H }
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const onWheel = (e: WheelEvent) => {
      const c = cur.current
      if (!c.locus || !c.W) return
      e.preventDefault()
      const r = cv.getBoundingClientRect()
      const z = zoomMatrixView(c.locus, c.W, c.H, c.yOff, Math.exp(e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top)
      const next = clampLocus({ chrom: c.locus.chrom, start: z.start, end: z.end }, c.ext)
      // clamping moved the x window: keep the y centre where the zoom put it
      setYOff(z.yOff + (z.start + z.end) / 2 - (next.start + next.end) / 2)
      setLocus(next)
    }
    cv.addEventListener('wheel', onWheel, { passive: false })
    return () => cv.removeEventListener('wheel', onWheel)
  }, [setLocus])
  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!locus || !vp || e.button !== 0) return
    const start = { x: e.clientX, y: e.clientY, locus, yOff, bpp: vp.bpPerPx }
    const move = (ev: PointerEvent) => {
      const next = panLocus(start.locus, -(ev.clientX - start.x) * start.bpp, ext)
      // y follows the pointer too (net of what the x clamp absorbed)
      const dx = (next.start - start.locus.start)
      setLocus(next)
      setYOff(start.yOff - (ev.clientY - start.y) * start.bpp - dx)
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
    if (!shown || !vp || e.buttons) return
    const rect = e.currentTarget.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const h = shown.header
    const bx = vp.xStart + mx * vp.bpPerPx
    const by = vp.yStart + my * vp.bpPerPx
    const i = binAt(h.bin_starts, h.bin_ends, bx)
    const j = binAt(h.bin_starts, h.bin_ends, by)
    if (i < 0 || j < 0) return setHover(null)
    const v = shown.data[j * h.n_cols + i]
    const pos = (bp: number) => fmtPos(h.chrom, bp, layout)
    setHover({ x: mx, y: my, text: `${pos(h.bin_starts[j])} × ${pos(h.bin_starts[i])} · ${Number.isFinite(v) ? fmtAxis(v) : '—'}${h.unit && scale === 'distance' ? ` ${h.unit}` : ''}` })
  }

  let message: string | null = null
  if (!source) message = 'No contact maps and no 3-D coordinates — nothing to show as a matrix.'
  else if (!locus) message = 'No chromosomes to show.'
  const note = [
    mat?.header.note,
    mat?.header.n_cells && group ? `${mat.header.n_cells} cells used` : null,
    mat?.header.n_contacts ? `${fmtAxis(mat.header.n_contacts)} contacts (pseudo-bulk)` : null,
    mat?.header.n_traces ? `${mat.header.n_traces} traces` : null,
    mat?.header.resolution ? `${fmtBp(mat.header.resolution)} bins` : null,
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <div ref={boxRef} className="genome-view matrix-view">
      {message && <div className="muted pane-empty">{message}</div>}
      {error && !message && <div className="error pane-error">{error}</div>}
      <canvas
        ref={canvasRef}
        onPointerDown={onPointerDown}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        onDoubleClick={() => setYOff(0)}
        style={{ cursor: 'grab' }}
        title="Drag to pan, wheel to zoom, double-click to centre the diagonal"
      />
      {loading && <div className="pane-loading muted small">loading…</div>}
      {shown && !message && (
        <div className="matrix-legend">
          <MatrixLegend cscale={cscale} />
          {note && <div className="muted small matrix-legend-note">{note}</div>}
        </div>
      )}
      {takesScope ? (
        <div className="pane-badge small">
          {scope.kind === 'group' && <span className="swatch round" style={{ display: 'inline-block', width: 8, height: 8, marginRight: 4, background: groupInfo?.color ?? '#888' }} />}
          {scopeText(scope, groupInfo, nAll)}
        </div>
      ) : (
        map && <div className="pane-badge small">bulk map (all cells in the file)</div>
      )}
      {hover && (
        <div className="embedding-tip" style={{ left: Math.min(hover.x + 12, W - 240), top: hover.y + 12 }}>
          {hover.text}
        </div>
      )}
    </div>
  )
}

/** Width of the floating y axis (px). */
const AXIS_W = 56

/** The colour ramp of the floating legend card. */
function MatrixLegend({ cscale }: { cscale: ReturnType<typeof useMatrixScale> }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const pal = useTheme()
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const g = prepareCanvas(cv, 180, 36)
    if (!g) return
    drawColorRamp(g, { x: 1, y: 14, w: 176, h: 8 }, (t) => cscale.ramp(t), cscale.lo, cscale.hi, cscale.title)
  }, [cscale.lo, cscale.hi, cscale.title, cscale.cs, pal]) // eslint-disable-line react-hooks/exhaustive-deps
  return <canvas ref={ref} style={{ width: 180, height: 36, display: 'block' }} />
}

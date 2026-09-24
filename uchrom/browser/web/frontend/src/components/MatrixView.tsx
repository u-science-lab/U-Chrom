import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchContacts, fetchDistance } from '../api'
import { fmtBp } from '../filters'
import { matrixColor, matrixPixels, matrixRange, scaleFor, type MatrixData } from '../matrix'
import { ALL_CELLS_REF, isMultiCell, scopeText } from '../groups'
import { DistanceValueControls } from './AggregateControls'
import { useNCells } from './ScopePicker'
import { useStore } from '../store'
import { useGroupInfo, usePaneScope } from '../useGroups'
import { fmtAxis } from '../stats'
import type { ContactMapInfo } from '../types'
import { useLocus } from '../useLocus'
import { updatePane, type Pane } from '../workspace'
import { CHART, drawColorRamp, rgb } from './chart'
import { prepareCanvas, useSize } from './useSize'

const M = { left: 64, top: 10, right: 12, bottom: 76 }

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
  if (!source) return null
  return (
    <>
      <select value={source} onChange={(e) => upd({ source: e.target.value, resolution: null })} title="Matrix source">
        {maps.map((m) => (
          <option key={m.key} value={m.key}>
            {m.label || m.key} ({m.kind})
          </option>
        ))}
        {hasCoords && <option value="distance">3-D distance</option>}
      </select>
      {map && map.resolutions.length > 1 && (
        <select value={pane.resolution ?? ''} onChange={(e) => upd({ resolution: e.target.value ? +e.target.value : null })} title="Resolution">
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
    </>
  )
}

/**
 * Heatmap of a contact map (cool / mcool / scool) or of pairwise 3-D
 * distances for the shared locus.  Drag a square to zoom into it.
 */
export function MatrixView({ pane }: { pane: Pane }) {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const scope = usePaneScope(pane)
  const groupInfo = useGroupInfo(scope.kind === 'group' ? scope.group : null)
  const { locus, setLocus } = useLocus()
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
  const [drag, setDrag] = useState<{ i0: number; i1: number } | null>(null)

  const needsCell = !!map?.per_cell
  const takesScope = needsCell || source === 'distance'
  const nAll = useNCells()
  const cell = takesScope && scope.kind === 'cell' ? scope.cell : null
  // per-cell map + group / all cells → pseudo-bulk; distance + group → statistic over its traces
  const group = takesScope && scope.kind === 'group' ? scope.group : needsCell && scope.kind === 'all' ? ALL_CELLS_REF : null
  const waitingForCell = false

  useEffect(() => {
    if (!ds || !locus || !source || waitingForCell) return
    let live = true
    const t = setTimeout(() => {
      setLoading(true)
      const req =
        source === 'distance'
          ? fetchDistance(ds.id, locus, { cellId: cell, group, stat: pane.stat ?? 'median', threshold: pane.threshold ?? null })
          : fetchContacts(ds.id, source, locus, { resolution: pane.resolution ?? null, balance: pane.balance ?? false, cell, group })
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
  }, [ds?.id, source, locus?.chrom, locus?.start, locus?.end, cell, group, pane.stat, pane.threshold, pane.resolution, pane.balance, waitingForCell])

  const scale = mat ? scaleFor(mat.header.value) : 'contacts'
  const range = useMemo<[number, number]>(() => (mat ? matrixRange(mat.data, scale) : [0, 1]), [mat, scale])
  // one pixel per bin, scaled up with nearest-neighbour sampling
  const bitmap = useMemo(() => {
    if (!mat || !mat.header.n_rows || !mat.header.n_cols) return null
    const c = document.createElement('canvas')
    c.width = mat.header.n_cols
    c.height = mat.header.n_rows
    c.getContext('2d')!.putImageData(new ImageData(matrixPixels(mat, scale, range) as unknown as Uint8ClampedArray<ArrayBuffer>, c.width, c.height), 0, 0)
    return c
  }, [mat, scale, range])

  const side = Math.max(0, Math.min(size.w - M.left - M.right, size.h - M.top - M.bottom))
  const n = mat?.header.n_cols ?? 0

  useEffect(() => {
    const cv = canvasRef.current
    if (!cv || !size.w || !size.h) return
    const g = prepareCanvas(cv, size.w, size.h)
    if (!g || !mat || !bitmap || side < 20) return
    g.imageSmoothingEnabled = false
    g.drawImage(bitmap, M.left, M.top, side, side)
    g.strokeStyle = CHART.axis
    g.strokeRect(M.left - 0.5, M.top - 0.5, side + 1, side + 1)
    // genomic ticks (bins may be gapped: label by bin index)
    const h = mat.header
    g.font = CHART.font
    g.fillStyle = CHART.text
    const nt = Math.max(2, Math.min(6, Math.floor(side / 80)))
    for (let k = 0; k <= nt; k++) {
      const i = Math.min(n - 1, Math.round((k / nt) * (n - 1)))
      const p = ((i + 0.5) / n) * side
      const label = fmtAxis(h.bin_starts[i])
      g.textAlign = 'center'
      g.textBaseline = 'top'
      // keep the last label inside the pane
      const half = g.measureText(label).width / 2
      g.fillText(label, Math.min(M.left + p, size.w - 2 - half), M.top + side + 4)
      g.textAlign = 'right'
      g.textBaseline = 'middle'
      g.fillText(label, M.left - 4, M.top + p)
    }
    // selection square
    if (drag) {
      const a = Math.min(drag.i0, drag.i1)
      const b = Math.max(drag.i0, drag.i1) + 1
      g.strokeStyle = '#ffffff'
      g.setLineDash([4, 3])
      g.strokeRect(M.left + (a / n) * side, M.top + (a / n) * side, ((b - a) / n) * side, ((b - a) / n) * side)
      g.setLineDash([])
    }
    // colour bar
    const unit = h.unit ? ` (${h.unit})` : ''
    const title = scale === 'contacts' ? `${h.value === 'balanced' ? 'balanced' : 'contacts'} (log)` : scale === 'distance' ? `distance${unit}` : 'contact frequency'
    const lo = scale === 'contacts' ? '0' : fmtAxis(range[0])
    const hi = scale === 'contacts' ? `≥${fmtAxis(Math.expm1(range[1]))}` : fmtAxis(range[1])
    const color = (t: number) => {
      const v = scale === 'contacts' ? Math.expm1(t * range[1]) : range[0] + t * (range[1] - range[0])
      return rgb(matrixColor(v, scale, range))
    }
    drawColorRamp(g, { x: M.left, y: M.top + side + 34, w: Math.min(180, side), h: 8 }, color, lo, hi, title)
  }, [mat, bitmap, side, size.w, size.h, drag, range, scale, n])

  const binOf = (e: React.MouseEvent | PointerEvent, rect: DOMRect): [number, number] => {
    const x = (e.clientX - rect.left - M.left) / side
    const y = (e.clientY - rect.top - M.top) / side
    return [Math.floor(x * n), Math.floor(y * n)]
  }
  const inside = (i: number, j: number) => i >= 0 && j >= 0 && i < n && j < n

  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!mat || e.buttons) return
    const rect = e.currentTarget.getBoundingClientRect()
    const [i, j] = binOf(e, rect)
    if (!inside(i, j)) return setHover(null)
    const h = mat.header
    const v = mat.data[j * h.n_cols + i]
    setHover({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
      text: `${h.chrom}:${fmtBp(h.bin_starts[j])} × ${fmtBp(h.bin_starts[i])} · ${Number.isFinite(v) ? fmtAxis(v) : '—'}${h.unit && scale === 'distance' ? ` ${h.unit}` : ''}`,
    })
  }
  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!mat || !locus) return
    const rect = e.currentTarget.getBoundingClientRect()
    const [i0] = binOf(e, rect)
    if (!inside(i0, i0)) return
    let cur = { i0, i1: i0 }
    setDrag(cur)
    const move = (ev: PointerEvent) => {
      const [i1] = binOf(ev, rect)
      cur = { i0, i1: Math.max(0, Math.min(n - 1, i1)) }
      setDrag(cur)
      setHover(null)
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      setDrag(null)
      const a = Math.min(cur.i0, cur.i1)
      const b = Math.max(cur.i0, cur.i1)
      if (b - a >= 1) setLocus({ chrom: mat.header.chrom, start: mat.header.bin_starts[a], end: mat.header.bin_ends[b] })
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  let message: string | null = null
  if (!source) message = 'No contact maps and no 3-D coordinates — nothing to show as a matrix.'
  else if (!locus) message = 'No chromosomes to show.'
  else if (waitingForCell) message = `“${map?.label || map?.key}” holds one contact map per cell — select a cell or a group (left), or scope this view to a group (inspector).`
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
    <div ref={boxRef} className="genome-view">
      {message && <div className="muted pane-empty">{message}</div>}
      {error && !message && <div className="error pane-error">{error}</div>}
      <canvas ref={canvasRef} onPointerDown={onPointerDown} onMouseMove={onMove} onMouseLeave={() => setHover(null)} style={{ cursor: 'crosshair' }} />
      {loading && <div className="pane-loading muted small">loading…</div>}
      {takesScope ? (
        <div className="pane-badge small">
          {scope.kind === 'group' && <span className="swatch round" style={{ display: 'inline-block', width: 8, height: 8, marginRight: 4, background: groupInfo?.color ?? '#888' }} />}
          {scopeText(scope, groupInfo, nAll)}
        </div>
      ) : (
        map && <div className="pane-badge small">bulk map (all cells in the file)</div>
      )}
      {note && !message && (
        <div className="matrix-note muted small" style={{ left: M.left, top: M.top + side + 58 }}>
          {note}
        </div>
      )}
      {hover && (
        <div className="embedding-tip" style={{ left: Math.min(hover.x + 12, size.w - 240), top: hover.y + 12 }}>
          {hover.text}
        </div>
      )}
    </div>
  )
}

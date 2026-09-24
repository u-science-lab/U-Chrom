import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchEmbedding, registerGroup } from '../api'
import { cellRgb, rgbCss } from '../colors'
import { lassoSelect, simplifyPath, type Pt } from '../groups'
import { useFieldColors } from '../useFieldColors'
import { useGroupInfo, usePaneScope, useScopeCells } from '../useGroups'
import { fitPlot, nearestPoint, project } from '../render/embedding'
import { activeView, useStore } from '../store'
import type { Embedding, EmbeddingInfo } from '../types'
import { defaultEmbeddingKey, updatePane, type Pane } from '../workspace'
import { fmtValue } from './format'

const PAD = 14

/** Resolve a pane's embedding key / dims against what the dataset offers. */
export function resolveEmbedding(list: EmbeddingInfo[], pane: Pane): { key: string | null; info?: EmbeddingInfo; dims: [number, number] } {
  const key = pane.embeddingKey && list.some((e) => e.key === pane.embeddingKey) ? pane.embeddingKey : defaultEmbeddingKey(list)
  const info = list.find((e) => e.key === key)
  const dims: [number, number] = info && Math.max(...pane.dims) < info.n_dims ? pane.dims : [0, 1]
  return { key, info, dims }
}

/** Pane-header controls of an embedding pane: which embedding and which two components. */
export function EmbeddingControls({ pane }: { pane: Pane }) {
  const list = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.embeddings) ?? []
  const setWorkspace = useStore((s) => s.setWorkspace)
  const { key, info, dims } = resolveEmbedding(list, pane)
  if (!list.length) return null
  const dimOptions = info ? Array.from({ length: info.n_dims }, (_, i) => i) : []
  const dimLabel = (i: number) => (info?.method === 'pca' ? `PC${i + 1}` : `${info?.method?.toUpperCase() ?? 'D'}${i + 1}`)
  return (
    <>
      <select value={key ?? ''} onChange={(e) => setWorkspace((ws) => updatePane(ws, pane.id, { embeddingKey: e.target.value, dims: [0, 1] }))}>
        {list.map((e) => (
          <option key={e.key} value={e.key}>
            {e.label}
          </option>
        ))}
      </select>
      {info &&
        info.n_dims > 2 &&
        [0, 1].map((k) => (
          <select
            key={k}
            className="dim"
            value={dims[k]}
            onChange={(e) => {
              const d: [number, number] = [...dims]
              d[k] = +e.target.value
              setWorkspace((ws) => updatePane(ws, pane.id, { dims: d }))
            }}
          >
            {dimOptions.map((i) => (
              <option key={i} value={i}>
                {dimLabel(i)}
              </option>
            ))}
          </select>
        ))}
    </>
  )
}

/**
 * 2-D scatter of a cell embedding (UMAP / t-SNE / PCA) filling its pane,
 * coloured like the 3-D overview.  Click a dot to focus that cell (every
 * 3-D pane flies there).  Shift-drag (or the ◌ lasso tool) selects cells:
 * the selection becomes the focused group, and can be saved by name.
 */
export function EmbeddingView({ pane }: { pane: Pane }) {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const view = useStore(activeView)
  const focusCell = useStore((s) => s.focusCell)
  const cells = useStore((s) => (s.activeDatasetId ? s.cells[s.activeDatasetId] : undefined))
  const fieldColors = useFieldColors()
  const fieldValues = fieldColors.cellValues
  const custom = useStore((s) => s.layers.find((l) => l.datasetId === s.activeDatasetId && l.parentId === null)?.style.color ?? '#ffffff')
  const list = ds?.embeddings ?? []
  const { key, dims } = resolveEmbedding(list, pane)
  // a group in scope (the pane's, or the focused one): its dots stand out
  const scope = usePaneScope(pane)
  const scopeCells = useScopeCells(scope)
  const groupSet = scope.kind === 'group' ? scopeCells : null
  const groupInfo = useGroupInfo(scope.kind === 'group' ? scope.group : null)
  const selection = useStore((s) => activeView(s).selection)
  const setSelection = useStore((s) => s.setSelection)
  const saveSelection = useStore((s) => s.saveSelection)
  const setAppError = useStore((s) => s.setError)
  const [lassoTool, setLassoTool] = useState(false)
  const [selName, setSelName] = useState('')
  const lassoRef = useRef<HTMLCanvasElement>(null)
  const path = useRef<Pt[] | null>(null)
  const suppressClick = useRef(false)

  const [size, setSize] = useState({ w: 340, h: 340 })
  const boxRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    setSize({ w: el.clientWidth, h: el.clientHeight })
    return () => ro.disconnect()
  }, [])
  const [emb, setEmb] = useState<Embedding | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!ds || !key) {
      setEmb(null) // another dataset without embeddings: no stale dots
      return
    }
    let live = true
    setError(null)
    fetchEmbedding(ds.id, key, dims)
      .then((e) => live && setEmb(e))
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ds?.id, key, dims[0], dims[1]])

  // a new embedding / size invalidates the hovered dot's position
  useEffect(() => setHover(null), [emb, size.w, size.h])

  const plotH = Math.max(40, size.h - 24) // axis labels below
  const px = useMemo(() => {
    if (!emb) return null
    return project(emb.x, emb.y, fitPlot(emb.x, emb.y, size.w, plotH, PAD))
  }, [emb, size.w, plotH])

  // per-dot colours = the 3-D overview colouring
  const colors = useMemo(() => {
    if (!emb) return []
    const cellIndex = new Map((cells ?? []).map((c, i) => [c.cell_id, i]))
    const opts = {
      cellIndex,
      ...fieldColors,
    }
    return emb.cell_ids.map((id) => rgbCss(cellRgb(id, view.overviewColor, custom, opts)))
  }, [emb, cells, fieldColors, view.overviewColor, custom])

  // draw
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv || !px || !emb) return
    const dpr = window.devicePixelRatio || 1
    cv.width = Math.round(size.w * dpr)
    cv.height = Math.round(plotH * dpr)
    const g = cv.getContext('2d')
    if (!g) return
    g.setTransform(dpr, 0, 0, dpr, 0, 0)
    g.clearRect(0, 0, size.w, plotH)
    const n = emb.cell_ids.length
    // dots grow a little with the panel (full-size tab / split pane)
    const grow = Math.min(2, Math.max(1, Math.min(size.w, plotH) / 340))
    const r = (n > 3000 ? 1.6 : n > 800 ? 2.4 : 3.4) * grow
    const focus = view.focusCell
    // group in scope: members on top at full opacity, the rest faint
    const order = groupSet ? [...Array(n).keys()].sort((a, b) => +groupSet.has(emb.cell_ids[a]) - +groupSet.has(emb.cell_ids[b])) : null
    for (let k = 0; k < n; k++) {
      const i = order ? order[k] : k
      const x = px[2 * i]
      const y = px[2 * i + 1]
      if (Number.isNaN(x)) continue
      const member = groupSet?.has(emb.cell_ids[i])
      g.globalAlpha = groupSet ? (member ? 0.95 : 0.14) : focus && emb.cell_ids[i] !== focus ? 0.55 : 0.95
      g.fillStyle = colors[i]
      g.beginPath()
      g.arc(x, y, member ? r * 1.15 : r, 0, 2 * Math.PI)
      g.fill()
    }
    g.globalAlpha = 1
    const ring = (i: number, rad: number, color: string, width: number) => {
      const x = px[2 * i]
      const y = px[2 * i + 1]
      if (Number.isNaN(x)) return
      g.strokeStyle = color
      g.lineWidth = width
      g.beginPath()
      g.arc(x, y, rad, 0, 2 * Math.PI)
      g.stroke()
    }
    if (focus) {
      const fi = emb.cell_ids.indexOf(focus)
      if (fi >= 0) {
        g.fillStyle = colors[fi]
        g.beginPath()
        g.arc(px[2 * fi], px[2 * fi + 1], r * 2, 0, 2 * Math.PI)
        g.fill()
        ring(fi, r * 2 + 2, '#ffffff', 2)
      }
    }
    // this pane's pinned cell: accent ring + label, in addition to the focus
    const pi = pane.cell ? emb.cell_ids.indexOf(pane.cell) : -1
    if (pi >= 0) {
      ring(pi, r * 2 + 5, '#5c9ded', 2.5)
      g.fillStyle = '#5c9ded'
      g.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
      g.textAlign = 'left'
      g.textBaseline = 'middle'
      if (!Number.isNaN(px[2 * pi])) g.fillText(`📌 ${pane.cell}`, px[2 * pi] + r * 2 + 9, px[2 * pi + 1])
    }
    if (hover) ring(hover.i, r + 4, 'rgba(255,255,255,0.8)', 1.5)
    if (groupSet && groupInfo) {
      g.globalAlpha = 1
      g.fillStyle = groupInfo.color
      g.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
      g.textAlign = 'right'
      g.textBaseline = 'top'
      g.fillText(`${groupInfo.name} · ${groupSet.size} cells`, size.w - 8, 8)
    }
  }, [px, colors, emb, size.w, plotH, view.focusCell, hover, pane.cell, groupSet, groupInfo])

  // ---- lasso ----------------------------------------------------------------
  const drawLasso = () => {
    const cv = lassoRef.current
    if (!cv) return
    const dpr = window.devicePixelRatio || 1
    cv.width = Math.round(size.w * dpr)
    cv.height = Math.round(plotH * dpr)
    cv.style.width = `${size.w}px`
    cv.style.height = `${plotH}px`
    const g = cv.getContext('2d')
    if (!g) return
    g.setTransform(dpr, 0, 0, dpr, 0, 0)
    g.clearRect(0, 0, size.w, plotH)
    const p = path.current
    if (!p || p.length < 2) return
    g.strokeStyle = '#ffffff'
    g.fillStyle = 'rgba(255,255,255,0.08)'
    g.lineWidth = 1.5
    g.setLineDash([5, 4])
    g.beginPath()
    p.forEach(([x, y], k) => (k ? g.lineTo(x, y) : g.moveTo(x, y)))
    g.closePath()
    g.fill()
    g.stroke()
  }
  const local = (e: React.PointerEvent<HTMLCanvasElement>): Pt => {
    const rect = e.currentTarget.getBoundingClientRect()
    return [e.clientX - rect.left, e.clientY - rect.top]
  }
  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.button !== 0 || !(lassoTool || e.shiftKey) || !px) return
    e.preventDefault()
    try {
      e.currentTarget.setPointerCapture(e.pointerId) // keep the lasso when the pointer leaves the canvas
    } catch {
      /* synthetic / already released pointer: capture is only a convenience */
    }
    path.current = [local(e)]
    setHover(null)
  }
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!path.current) return
    path.current.push(local(e))
    drawLasso()
  }
  const onPointerUp = () => {
    const p = path.current
    path.current = null
    drawLasso()
    if (!p || !px || !emb || !ds) return
    const poly = simplifyPath(p)
    if (poly.length < 3) return // a click: focus a dot as usual
    suppressClick.current = true
    const cells = lassoSelect(px, emb.cell_ids, poly)
    if (!cells.length) return
    registerGroup(ds.id, cells)
      .then((r) => setSelection({ id: r.id, cells }))
      .catch((err: Error) => setAppError(`Cannot register the selection: ${err.message}`))
  }

  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!px || path.current) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const i = nearestPoint(px, x, y, 8)
    setHover(i >= 0 ? { i, x, y } : null)
  }
  // hit-test the click itself: a quick move-then-click can arrive before the
  // hover state from the mousemove has rendered
  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (suppressClick.current) {
      suppressClick.current = false
      return
    }
    if (!px || !emb) return
    const rect = e.currentTarget.getBoundingClientRect()
    const i = nearestPoint(px, e.clientX - rect.left, e.clientY - rect.top, 8)
    if (i >= 0) focusCell(emb.cell_ids[i])
  }

  const hoverId = hover && emb ? emb.cell_ids[hover.i] : null
  const hoverVal = hoverId && view.overviewColor === 'field' && fieldValues ? fieldValues.get(hoverId) : undefined
  const axis = emb?.axis_labels ?? ['', '']

  return (
    <div ref={boxRef} className="embedding-view">
      {!list.length && <div className="muted pane-empty">This dataset has no cell embeddings (see uchrom.emb.embed_cells).</div>}
      {error && <div className="error">{error}</div>}
      <canvas
        ref={canvasRef}
        style={{ width: size.w, height: plotH, cursor: lassoTool ? 'crosshair' : hover ? 'pointer' : 'default', touchAction: 'none' }}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        onClick={onClick}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      />
      <canvas ref={lassoRef} className="emb-lasso-canvas" data-capture="skip" />
      {list.length > 0 && (
        <div className="emb-tools" data-capture="skip">
          <button className={lassoTool ? 'active' : ''} onClick={() => setLassoTool(!lassoTool)} title="Lasso: drag around cells to select them (or shift-drag any time)">
            ◌ lasso
          </button>
        </div>
      )}
      {selection && (
        <div className="emb-selection" data-capture="skip">
          <span>
            <b>{selection.cells.length}</b> cells selected
          </span>
          <input
            placeholder="name…"
            value={selName}
            onChange={(e) => setSelName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                saveSelection(selName)
                setSelName('')
              }
            }}
          />
          <button
            onClick={() => {
              saveSelection(selName)
              setSelName('')
            }}
          >
            Save as group
          </button>
          <button onClick={() => setSelection(null)} title="Discard the selection">
            ×
          </button>
        </div>
      )}
      <div className="embedding-axes muted small">
        <span>{axis[0]} →</span>
        <span>↑ {axis[1]}</span>
      </div>
      {hover && hoverId && (
        <div className="embedding-tip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
          cell {hoverId}
          {hoverVal !== undefined && ` · ${fmtValue(hoverVal)}`}
        </div>
      )}
    </div>
  )
}

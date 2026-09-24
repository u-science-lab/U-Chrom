import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchEmbedding } from '../api'
import { cellRgb, rgbCss } from '../colors'
import { useFieldColors } from '../useFieldColors'
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
 * 3-D pane flies there).
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
    for (let i = 0; i < n; i++) {
      const x = px[2 * i]
      const y = px[2 * i + 1]
      if (Number.isNaN(x)) continue
      g.globalAlpha = focus && emb.cell_ids[i] !== focus ? 0.55 : 0.95
      g.fillStyle = colors[i]
      g.beginPath()
      g.arc(x, y, r, 0, 2 * Math.PI)
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
  }, [px, colors, emb, size.w, plotH, view.focusCell, hover, pane.cell])

  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!px) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const i = nearestPoint(px, x, y, 8)
    setHover(i >= 0 ? { i, x, y } : null)
  }
  // hit-test the click itself: a quick move-then-click can arrive before the
  // hover state from the mousemove has rendered
  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
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
        style={{ width: size.w, height: plotH, cursor: hover ? 'pointer' : 'default' }}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        onClick={onClick}
      />
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

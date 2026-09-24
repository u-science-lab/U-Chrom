import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchEmbedding } from '../api'
import { cellRgb, fieldRange, rgbCss } from '../colors'
import { fitPlot, nearestPoint, project } from '../render/embedding'
import { activeFieldValues, activeView, useStore } from '../store'
import type { Embedding, EmbeddingInfo } from '../types'
import { fmtNum } from './format'

const PAD = 14
const MIN_SIZE = 200

/** Preferred default: UMAP, then t-SNE, then PCA, then whatever comes first. */
function defaultKey(list: EmbeddingInfo[]): string | null {
  for (const m of ['umap', 'tsne', 'pca']) {
    const e = list.find((x) => x.method === m)
    if (e) return e.key
  }
  return list[0]?.key ?? null
}

/**
 * Docked 2-D scatter of a cell embedding (UMAP / t-SNE / PCA), coloured like
 * the 3-D overview.  Click a dot to focus that cell in 3-D.
 */
export function EmbeddingPanel() {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const view = useStore(activeView)
  const setEmbedding = useStore((s) => s.setEmbedding)
  const focusCell = useStore((s) => s.focusCell)
  const cells = useStore((s) => (s.activeDatasetId ? s.cells[s.activeDatasetId] : undefined))
  const fieldValues = useStore(activeFieldValues)
  const custom = useStore((s) => s.layers.find((l) => l.datasetId === s.activeDatasetId && l.parentId === null)?.style.color ?? '#ffffff')
  const list = ds?.embeddings ?? []
  const key = view.embeddingKey && list.some((e) => e.key === view.embeddingKey) ? view.embeddingKey : defaultKey(list)
  const info = list.find((e) => e.key === key)
  const dims: [number, number] = info && Math.max(...view.embeddingDims) < info.n_dims ? view.embeddingDims : [0, 1]

  const [emb, setEmb] = useState<Embedding | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [size, setSize] = useState({ w: 340, h: 340 })
  const [collapsed, setCollapsed] = useState(false)
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!ds || !key || !view.embeddingOpen) return
    let live = true
    setError(null)
    fetchEmbedding(ds.id, key, dims)
      .then((e) => live && setEmb(e))
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ds?.id, key, dims[0], dims[1], view.embeddingOpen])

  // a new embedding / size invalidates the hovered dot's position
  useEffect(() => setHover(null), [emb, size.w, size.h])

  const plotH = size.h - 58 // header + axis labels
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
      cellValues: fieldValues ?? undefined,
      fieldRange: fieldValues ? fieldRange(fieldValues.values()) : undefined,
    }
    return emb.cell_ids.map((id) => rgbCss(cellRgb(id, view.overviewColor, custom, opts)))
  }, [emb, cells, fieldValues, view.overviewColor, custom])

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
    const r = n > 3000 ? 1.6 : n > 800 ? 2.4 : 3.4
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
    if (hover) ring(hover.i, r + 4, 'rgba(255,255,255,0.8)', 1.5)
  }, [px, colors, emb, size.w, plotH, view.focusCell, hover])

  if (!list.length || !view.embeddingOpen) return null

  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!px) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const i = nearestPoint(px, x, y, 8)
    setHover(i >= 0 ? { i, x, y } : null)
  }
  const onClick = () => {
    if (hover && emb) focusCell(emb.cell_ids[hover.i])
  }
  // resize from the top-left corner (the panel is anchored bottom-right)
  const onResizeStart = (e: React.PointerEvent) => {
    e.preventDefault()
    const start = { x: e.clientX, y: e.clientY, ...size }
    const move = (ev: PointerEvent) =>
      setSize({ w: Math.max(MIN_SIZE, start.w - (ev.clientX - start.x)), h: Math.max(MIN_SIZE, start.h - (ev.clientY - start.y)) })
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const hoverId = hover && emb ? emb.cell_ids[hover.i] : null
  const hoverVal = hoverId && view.overviewColor === 'field' && fieldValues ? fieldValues.get(hoverId) : undefined
  const axis = emb?.axis_labels ?? ['', '']
  const dimOptions = info ? Array.from({ length: info.n_dims }, (_, i) => i) : []
  const dimLabel = (i: number) => (info?.method === 'pca' ? `PC${i + 1}` : `${info?.method.toUpperCase() ?? 'D'}${i + 1}`)

  return (
    <div className="embedding-panel" style={{ width: size.w }}>
      {!collapsed && <div className="embedding-resize" onPointerDown={onResizeStart} title="Drag to resize" />}
      <div className="embedding-head">
        <select value={key ?? ''} onChange={(e) => setEmbedding({ embeddingKey: e.target.value, embeddingDims: [0, 1] })}>
          {list.map((e) => (
            <option key={e.key} value={e.key}>
              {e.label}
            </option>
          ))}
        </select>
        {info && info.n_dims > 2 && (
          <>
            {[0, 1].map((k) => (
              <select
                key={k}
                className="dim"
                value={dims[k]}
                onChange={(e) => {
                  const d: [number, number] = [...dims]
                  d[k] = +e.target.value
                  setEmbedding({ embeddingDims: d })
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
        )}
        <span className="spacer" />
        <button onClick={() => setCollapsed(!collapsed)} title={collapsed ? 'Expand' : 'Collapse'}>
          {collapsed ? '▴' : '▾'}
        </button>
        <button onClick={() => setEmbedding({ embeddingOpen: false })} title="Close">
          ×
        </button>
      </div>
      {!collapsed && (
        <div className="embedding-body" style={{ height: size.h - 30 }}>
          {error && <div className="error">{error}</div>}
          <canvas
            ref={canvasRef}
            style={{ width: size.w, height: plotH, cursor: hover ? 'pointer' : 'default' }}
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
            onClick={onClick}
          />
          <div className="embedding-axes muted small">
            <span>
              {axis[0]} →
            </span>
            <span>
              ↑ {axis[1]}
            </span>
          </div>
          {hover && hoverId && (
            <div className="embedding-tip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
              cell {hoverId}
              {hoverVal !== undefined && ` · ${hoverVal === null ? '—' : fmtNum(hoverVal)}`}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

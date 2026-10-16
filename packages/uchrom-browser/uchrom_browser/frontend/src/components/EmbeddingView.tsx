import { useEffect, useMemo, useRef, useState } from 'react'
import { recordable, useCaptureEpoch } from '../vectorcapture'
import { fetchEmbedding, registerGroup } from '../api'
import { cmapGradient, COLORMAPS, type ColormapName } from '../colormaps'
import { cellRgb, rgbCss } from '../colors'
import {
  autoFieldRange,
  categoryDotColors,
  categoryLegend,
  defaultRangeMode,
  dotRadius,
  drawOrder,
  fieldScaleRange,
  numericDotColors,
  OPACITY_MIN,
  patchEmbStyle,
  resolveEmbStyle,
  SIZE_MAX,
  SIZE_MIN,
  solidDotColors,
  sortedFinite,
  type DotColors,
  type EmbRangeMode,
  type EmbStyle,
} from '../embeddingStyle'
import { lassoSelect, simplifyPath, type Pt } from '../groups'
import { useFieldColors } from '../useFieldColors'
import { loadFieldValues } from '../useOmicsLoader'
import { useTheme } from '../useTheme'
import { useGroupInfo, usePaneScope, useScopeCells } from '../useGroups'
import { IDENTITY_VIEW, applyView, fitPlot, fitPlotEqual, gridSpacing, isIdentity, nearestPoint, panBy, project, zoomAt, type View2D } from '../render/embedding'
import { activeView, defaultCategoryField, fieldKey, useStore } from '../store'
import type { CellField, CellValue, Embedding, EmbeddingInfo } from '../types'
import { defaultEmbeddingKey, pinnedCell, updatePane, type Pane } from '../workspace'
import { FieldPicker, groupTitle } from './FieldPicker'
import { colourableFields, fieldLabel, fmtNum, fmtValue } from './format'
import { Select } from './Select'

const PAD = 14

/** Resolve a pane's embedding key / dims against what the dataset offers. */
export function resolveEmbedding(list: EmbeddingInfo[], pane: Pane): { key: string | null; info?: EmbeddingInfo; dims: [number, number] } {
  const key = pane.embeddingKey && list.some((e) => e.key === pane.embeddingKey) ? pane.embeddingKey : defaultEmbeddingKey(list)
  const info = list.find((e) => e.key === key)
  const dims: [number, number] = info && Math.max(...pane.dims) < info.n_dims ? pane.dims : [0, 1]
  return { key, info, dims }
}

const MODALITY_ORDER = ['RNA', 'Histone/IF', 'ATAC', 'Hi-C', 'Published']
const METHOD_ORDER = ['umap', 'tsne', 'pca', 'lsi']
const METHOD_NAME: Record<string, string> = { umap: 'UMAP', tsne: 't-SNE', pca: 'PCA', lsi: 'LSI' }

/**
 * Picker entries grouped by modality ("RNA", "Histone/IF", "ATAC", "Hi-C",
 * "Published", then any other), each labelled "<modality> · <method>" —
 * or with the stored label when that is ambiguous / the method unknown.
 */
export function groupEmbeddings(list: EmbeddingInfo[]): { modality: string; items: { info: EmbeddingInfo; text: string }[] }[] {
  const mod = (e: EmbeddingInfo) => e.modality || 'Other'
  const base = (e: EmbeddingInfo) => (e.method && METHOD_NAME[e.method] ? `${mod(e)} · ${METHOD_NAME[e.method]}` : null)
  const count = new Map<string, number>()
  for (const e of list) {
    const b = base(e)
    if (b) count.set(b, (count.get(b) ?? 0) + 1)
  }
  const groups = new Map<string, { info: EmbeddingInfo; text: string }[]>()
  for (const e of list) {
    const b = base(e)
    const text = b && count.get(b) === 1 ? b : `${mod(e)} · ${e.label}`
    groups.set(mod(e), [...(groups.get(mod(e)) ?? []), { info: e, text }])
  }
  const rank = (m: string) => (MODALITY_ORDER.includes(m) ? MODALITY_ORDER.indexOf(m) : MODALITY_ORDER.length)
  const mrank = (e: EmbeddingInfo) => (e.method && METHOD_ORDER.includes(e.method) ? METHOD_ORDER.indexOf(e.method) : METHOD_ORDER.length)
  return [...groups.entries()]
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([modality, items]) => ({ modality, items: [...items].sort((a, b) => mrank(a.info) - mrank(b.info)) }))
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
      <Select value={key ?? ''} onChange={(e) => setWorkspace((ws) => updatePane(ws, pane.id, { embeddingKey: e.target.value, dims: [0, 1] }))}>
        {groupEmbeddings(list).map((g, _, all) => {
          const opts = g.items.map(({ info: e, text }) => (
            <option key={e.key} value={e.key} title={`${e.label} (${e.key})`}>
              {text}
            </option>
          ))
          return all.length > 1 ? (
            <optgroup key={g.modality} label={g.modality}>
              {opts}
            </optgroup>
          ) : (
            opts
          )
        })}
      </Select>
      {info &&
        info.n_dims > 2 &&
        [0, 1].map((k) => (
          <Select
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
          </Select>
        ))}
      <EmbeddingStyleControls pane={pane} />
    </>
  )
}

/** Group key of the categorical fields in the colour-by menu. */
const CATEGORY_GROUP = '\u0000category'

/**
 * The colouring a pane asks for, resolved against the active dataset: its
 * style, the field (loaded on demand) with its values, and — for numeric
 * fields — the sorted finite values and the colour range.  A field the
 * dataset lacks falls back to the overview colouring.
 */
export function usePaneColoring(pane: Pane) {
  const dsId = useStore((s) => s.activeDatasetId)
  const fields = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.cell_fields)
  const st = useMemo(() => resolveEmbStyle(pane.embStyle), [pane.embStyle])
  const field: CellField | null = st.colorBy === 'field' ? (fields?.find((f) => f.name === st.field) ?? null) : null
  const mode: EmbStyle['colorBy'] = st.colorBy === 'field' && !field ? 'overview' : st.colorBy
  useEffect(() => {
    if (dsId && field) loadFieldValues(dsId, field.name)
  }, [dsId, field])
  const values = useStore((s) => (dsId && field ? (s.cellValues[fieldKey(dsId, field.name)] ?? null) : null))
  const numeric = !!field && field.kind !== 'category'
  const sorted = useMemo(() => (numeric && values ? sortedFinite(values.values()) : null), [numeric, values])
  const range = useMemo<[number, number] | null>(
    () => (sorted ? fieldScaleRange(sorted, { range: st.range, lo: st.lo, hi: st.hi, field: st.field }) : null),
    [sorted, st.range, st.lo, st.hi, st.field],
  )
  return { st, mode, field, values, numeric, sorted, range }
}

/** A labelled row of the style controls. */
function Row({ label, title, children }: { label: string; title?: string; children: React.ReactNode }) {
  return (
    <div className="emb-row" title={title}>
      <span className="emb-lab">{label}</span>
      <div className="emb-ctl">{children}</div>
    </div>
  )
}

/** Segmented buttons of a small choice. */
function Seg<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange(v: T): void }) {
  return (
    <div className="seg emb-seg">
      {options.map(([v, text]) => (
        <button key={v} className={value === v ? 'active' : ''} onClick={() => onChange(v)}>
          {text}
        </button>
      ))}
    </div>
  )
}

/**
 * Point style and colouring of one Embedding pane (inspector): colour by
 * the overview colouring, a cell field of its own (categorical → legend,
 * numeric → colormap / range / log1p) or one colour; dot size, opacity,
 * shape and outline.  Stored on the pane (only the changes).
 */
export function EmbeddingStyleControls({ pane }: { pane: Pane }) {
  const setWorkspace = useStore((s) => s.setWorkspace)
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const { st, mode, field, numeric, sorted, range } = usePaneColoring(pane)
  const set = (patch: Partial<EmbStyle>) =>
    setWorkspace((ws) => updatePane(ws, pane.id, { embStyle: patchEmbStyle(ws.panes.find((p) => p.id === pane.id)?.embStyle, patch) }))
  const fields = useMemo(() => colourableFields(ds?.cell_fields ?? []), [ds?.cell_fields])
  const groups = useMemo(() => {
    const m = new Map<string, CellField[]>()
    if (fields.some((f) => f.kind === 'category')) m.set(CATEGORY_GROUP, [])
    for (const f of fields) {
      const g = f.kind === 'category' ? CATEGORY_GROUP : f.group
      m.set(g, [...(m.get(g) ?? []), f])
    }
    return m
  }, [fields])
  const titleOf = (g: string) => {
    if (g !== CATEGORY_GROUP) return groupTitle(g)
    const fs = groups.get(g) ?? []
    const one = fs.length === 1 ? fieldLabel(fs[0].name) : 'type'
    return one[0].toUpperCase() + one.slice(1)
  }
  const group = field ? (field.kind === 'category' ? CATEGORY_GROUP : field.group) : null
  const menuValue = mode === 'field' && group !== null ? `g:${group}` : mode
  const pickMenu = (v: string) => {
    if (v === 'overview' || v === 'solid') return set({ colorBy: v })
    const g = v.slice(2)
    const fs = groups.get(g) ?? []
    if (!fs.length) return
    const keep = fs.find((f) => f.name === st.field)
    const cat = g === CATEGORY_GROUP ? fs.find((f) => f.name === defaultCategoryField(ds)?.name) : undefined
    set({ colorBy: 'field', field: (keep ?? cat ?? fs[0]).name })
  }
  const auto = sorted ? autoFieldRange(sorted, (st.range ?? defaultRangeMode(st.field)) === 'quantile' ? 'quantile' : 'auto') : null
  const rangeMode: EmbRangeMode = st.range ?? defaultRangeMode(st.field)
  return (
    <div className="emb-style">
      <Row label="colour by" title="Colour of the dots in this view only">
        <Select value={menuValue} onChange={(e) => pickMenu(e.target.value)}>
          <option value="overview">same as overview</option>
          {[...groups.keys()].map((g) => (
            <option key={g} value={`g:${g}`}>
              {titleOf(g)}
            </option>
          ))}
          <option value="solid">single colour</option>
        </Select>
      </Row>
      {mode === 'field' && group !== null && (groups.get(group)?.length ?? 0) > 1 && (
        <Row label="">
          <FieldPicker
            key={group}
            fields={groups.get(group) ?? []}
            value={st.field}
            placeholder={`search ${titleOf(group).toLowerCase()}…`}
            onPick={(name) => set({ colorBy: 'field', field: name })}
          />
        </Row>
      )}
      {mode === 'solid' && (
        <Row label="colour">
          <input type="color" value={st.solid} onChange={(e) => set({ solid: e.target.value })} />
        </Row>
      )}
      {mode === 'field' && numeric && (
        <>
          <Row label="colormap">
            <Select value={st.cmap} onChange={(e) => set({ cmap: e.target.value as ColormapName })}>
              {COLORMAPS.filter((c) => !c.diverging && c.name !== 'fall').map((c) => (
                <option key={c.name} value={c.name}>
                  {c.label}
                </option>
              ))}
            </Select>
          </Row>
          <Row label="">
            <div className="cmap-preview" style={{ background: cmapGradient(st.cmap, st.reverse) }} title="low → high" />
          </Row>
          <Row label="range" title="Colour range: min–max, 1st–99th percentile (sparse data such as genes), or manual">
            <Select value={rangeMode} onChange={(e) => set({ range: e.target.value as EmbRangeMode })}>
              <option value="auto">min – max</option>
              <option value="quantile">1 – 99 %</option>
              <option value="manual">manual</option>
            </Select>
          </Row>
          {rangeMode === 'manual' && (
            <Row label="">
              <div className="emb-range">
                <NumInput value={st.lo} placeholder={auto ? fmtNum(auto[0]) : 'min'} onCommit={(v) => set({ lo: v })} title="Low end (empty = automatic)" />
                <span className="muted">–</span>
                <NumInput value={st.hi} placeholder={auto ? fmtNum(auto[1]) : 'max'} onCommit={(v) => set({ hi: v })} title="High end (empty = automatic)" />
              </div>
            </Row>
          )}
          <Row label="">
            <div className="emb-checks">
              <label className="check small" title="Swap the ends of the colormap">
                <input type="checkbox" checked={st.reverse} onChange={(e) => set({ reverse: e.target.checked })} /> reverse
              </label>
              <label className="check small" title="log1p of the offset from the range start">
                <input type="checkbox" checked={st.log} onChange={(e) => set({ log: e.target.checked })} /> log1p
              </label>
              <label className="check small" title="Draw high values last so expressing cells are not hidden (missing values always underneath)">
                <input type="checkbox" checked={st.highOnTop} onChange={(e) => set({ highOnTop: e.target.checked })} /> high on top
              </label>
            </div>
          </Row>
          {range && <div className="muted small emb-note">range {fmtNum(range[0])} – {fmtNum(range[1])}</div>}
        </>
      )}
      {mode === 'field' && (
        <Row label="legend" title={numeric ? 'Colour bar in the view' : 'Legend in the view: click an entry to grey it out here, double-click to show only it'}>
          <div className="emb-checks">
            <label className="check small">
              <input type="checkbox" checked={st.legend} onChange={(e) => set({ legend: e.target.checked })} /> show
            </label>
            {!numeric && st.hidden.length > 0 && (
              <button className="link" onClick={() => set({ hidden: [] })}>
                show all ({st.hidden.length} hidden)
              </button>
            )}
          </div>
        </Row>
      )}
      <Row label="size" title="Dot radius in pixels (auto: by cell count and view size)">
        <div className="emb-slider">
          <input
            type="range"
            min={SIZE_MIN}
            max={SIZE_MAX}
            step={0.5}
            value={st.size ?? 2}
            className={st.size === null ? 'auto' : ''}
            onChange={(e) => set({ size: +e.target.value })}
          />
          <span className="val">{st.size === null ? 'auto' : `${st.size}px`}</span>
          {st.size !== null && (
            <button className="link" onClick={() => set({ size: null })} title="Automatic size (by cell count and view size)">
              auto
            </button>
          )}
        </div>
      </Row>
      <Row label="opacity">
        <div className="emb-slider">
          <input type="range" min={OPACITY_MIN} max={1} step={0.05} value={st.opacity} onChange={(e) => set({ opacity: +e.target.value })} />
          <span className="val">{st.opacity.toFixed(2)}</span>
        </div>
      </Row>
      <Row label="shape" title="Squares draw much faster for many cells">
        <Seg
          value={st.shape}
          options={[
            ['circle', 'circle'],
            ['square', 'square'],
          ]}
          onChange={(v) => set({ shape: v })}
        />
      </Row>
      <Row label="outline" title="Thin ring around each dot (auto: on light themes only)">
        <Seg
          value={st.outline}
          options={[
            ['auto', 'auto'],
            ['on', 'on'],
            ['off', 'off'],
          ]}
          onChange={(v) => set({ outline: v })}
        />
      </Row>
      {pane.embStyle && (
        <button className="link emb-reset" onClick={() => setWorkspace((ws) => updatePane(ws, pane.id, { embStyle: undefined }))} title="Back to the default style">
          reset style
        </button>
      )}
    </div>
  )
}

/** Number input committed on blur / Enter; empty → null (automatic). */
function NumInput({ value, placeholder, title, onCommit }: { value: number | null; placeholder: string; title: string; onCommit(v: number | null): void }) {
  const [text, setText] = useState(value === null ? '' : String(value))
  useEffect(() => setText(value === null ? '' : String(value)), [value])
  const commit = () => {
    const t = text.trim()
    if (!t) return onCommit(null)
    const v = Number(t)
    if (Number.isFinite(v)) onCommit(v)
    else setText(value === null ? '' : String(value))
  }
  return (
    <input
      className="num"
      value={text}
      placeholder={placeholder}
      title={title}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
    />
  )
}

/**
 * Points given by the caller instead of a cellm embedding (the Spatial
 * view): drawn with one scale on both axes, optionally over an image.
 */
export interface ScatterSource {
  data: Embedding | null
  error: string | null
  /** y grows downwards (image pixels) */
  yDown: boolean
  /** fitted instead of the points' bounds, [x0, x1, y0, y1] in point units */
  extent: [number, number, number, number] | null
  /** drawn under the points over `extent` (row 0 at y0) */
  image: { url: string; extent: [number, number, number, number]; opacity: number } | null
  /** shown when there is nothing to draw */
  empty?: string
}

/**
 * 2-D scatter of a cell embedding (UMAP / t-SNE / PCA) filling its pane,
 * coloured like the 3-D overview.  Click a dot to focus that cell (every
 * 3-D pane flies there); click empty space to go back to all cells.  Shift-drag (or the lasso tool) selects cells:
 * the selection becomes the focused group, and can be saved by name.
 * With a `source` (Spatial view) it draws those points to scale instead.
 */
export function EmbeddingView({ pane, source }: { pane: Pane; source?: ScatterSource }) {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const view = useStore(activeView)
  const focusCell = useStore((s) => s.focusCell)
  const cells = useStore((s) => (s.activeDatasetId ? s.cells[s.activeDatasetId] : undefined))
  const fieldColors = useFieldColors()
  const pal = useTheme()
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
  const [fetched, setEmb] = useState<Embedding | null>(null)
  const [fetchError, setError] = useState<string | null>(null)
  const emb = source ? source.data : fetched
  const error = source ? source.error : fetchError
  const hasPoints = source ? !!source.data : list.length > 0
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (source) return // the caller supplies the points
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
  }, [ds?.id, key, dims[0], dims[1], !!source])

  // a new embedding / size invalidates the hovered dot's position
  useEffect(() => setHover(null), [emb, size.w, size.h])

  const plotH = Math.max(40, size.h) // the axis key floats over the plot
  const yDown = source?.yDown ?? false
  const extentKey = source?.extent?.join(',') ?? ''
  const plot = useMemo(() => {
    if (!emb) return null
    return source ? fitPlotEqual(emb.x, emb.y, size.w, plotH, PAD, { yDown, extent: source.extent }) : fitPlot(emb.x, emb.y, size.w, plotH, PAD)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emb, size.w, plotH, !!source, yDown, extentKey])
  const basePx = useMemo(() => (emb && plot ? project(emb.x, emb.y, plot) : null), [emb, plot])
  // positions to scale: automatic dots as wide as the spot spacing (touching neighbours), zoom included
  const spacing = useMemo(() => (source && emb ? gridSpacing(emb.x, emb.y) : null), [source, emb])
  // the image under the points (Spatial view)
  const imageUrl = source?.image?.url ?? null
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  useEffect(() => {
    setImg(null)
    if (!imageUrl) return
    let live = true
    const im = new Image()
    im.onload = () => live && setImg(im)
    im.src = imageUrl
    return () => {
      live = false
    }
  }, [imageUrl])
  // zoom / pan: wheel zooms at the cursor, drag pans, double-click (or ⤢) resets;
  // drawing, hover, click and lasso all use the transformed points
  const [zoom, setZoom] = useState<View2D>(IDENTITY_VIEW)
  useEffect(() => setZoom(IDENTITY_VIEW), [emb])
  const px = useMemo(() => (basePx ? applyView(basePx, zoom) : null), [basePx, zoom])
  const pan = useRef<{ x: number; y: number; v: View2D; moved: boolean } | null>(null)
  // positions (Spatial view) may zoom out beyond the spots, to the image around them
  const zoomOutRef = useRef(1)
  zoomOutRef.current = source ? 0.2 : 1
  const [panning, setPanning] = useState(false)
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault() // zoom the plot, not the page
      const rect = cv.getBoundingClientRect()
      const f = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0015))
      setZoom((v) => zoomAt(v, e.clientX - rect.left, e.clientY - rect.top, f, zoomOutRef.current))
      setHover(null)
    }
    cv.addEventListener('wheel', onWheel, { passive: false })
    return () => cv.removeEventListener('wheel', onWheel)
  }, [])

  // per-dot colours and draw keys: the pane's own colouring, else the 3-D
  // overview colouring.  Memoised apart from size / opacity / shape so that
  // dragging those sliders only redraws.
  const coloring = usePaneColoring(pane)
  const { st, mode, field: paneField, values: paneValues, range } = coloring
  const hiddenKey = st.hidden.join('\u0000')
  const dots = useMemo<DotColors | null>(() => {
    if (!emb) return null
    const ids = emb.cell_ids
    if (mode === 'solid') return solidDotColors(ids.length, st.solid)
    if (mode === 'field' && paneField) {
      if (paneField.kind === 'category') return categoryDotColors(ids, paneValues, paneField, st.hidden)
      return numericDotColors(ids, paneValues, st, range ?? [0, 1])
    }
    const cellIndex = new Map((cells ?? []).map((c, i) => [c.cell_id, i]))
    const opts = { cellIndex, ...fieldColors }
    return { css: ids.map((id) => rgbCss(cellRgb(id, view.overviewColor, custom, opts))), key: new Float64Array(ids.length) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emb, mode, paneField, paneValues, range, st.solid, st.cmap, st.reverse, st.log, st.highOnTop, hiddenKey, cells, fieldColors, view.overviewColor, custom])
  // draw order: missing / hidden underneath, high values on top, group members last
  const order = useMemo(() => {
    if (!emb || !dots) return null
    const ids = emb.cell_ids
    return drawOrder(ids.length, dots.key, groupSet ? (i) => groupSet.has(ids[i]) : null)
  }, [emb, dots, groupSet])
  const outline = st.outline === 'off' ? null : st.outline === 'on' ? (pal.dotRing !== 'transparent' ? pal.dotRing : 'rgba(0, 0, 0, 0.6)') : pal.dotRing !== 'transparent' ? pal.dotRing : null

  // draw
  const epoch = useCaptureEpoch((s) => s.epoch)
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv || !px || !emb || !dots) return
    const dpr = window.devicePixelRatio || 1
    cv.width = Math.round(size.w * dpr)
    cv.height = Math.round(plotH * dpr)
    const g0 = cv.getContext('2d')
    if (!g0) return
    const g = recordable(cv, g0)
    g.setTransform(dpr, 0, 0, dpr, 0, 0)
    g.clearRect(0, 0, size.w, plotH)
    const im = source?.image
    if (img && im && plot && im.opacity > 0) {
      // image corners → screen (plot transform, then zoom / pan); flipped when y grows up
      const [ex0, ex1, ey0, ey1] = im.extent
      const X0 = zoom.tx + zoom.k * plot.sx(ex0)
      const X1 = zoom.tx + zoom.k * plot.sx(ex1)
      const Y0 = zoom.ty + zoom.k * plot.sy(ey0)
      const Y1 = zoom.ty + zoom.k * plot.sy(ey1)
      g.save()
      g.globalAlpha = im.opacity
      g.imageSmoothingEnabled = zoom.k < 4 // pixels stay crisp when zoomed in
      if (Y1 >= Y0) g.drawImage(img, X0, Y0, X1 - X0, Y1 - Y0)
      else {
        g.translate(X0, Y0)
        g.scale(1, -1)
        g.drawImage(img, 0, 0, X1 - X0, Y0 - Y1)
      }
      g.restore()
    }
    const n = emb.cell_ids.length
    const spot = spacing && plot && st.size === null ? 0.45 * Math.abs(plot.sx(spacing) - plot.sx(0)) * zoom.k : null
    const r = spot ? Math.max(0.8, spot) : dotRadius(st, n, size.w, plotH)
    const colors = dots.css
    const focus = view.focusCell
    const base = st.opacity
    const square = st.shape === 'square'
    const lw = Math.min(0.6, r * 0.4)
    if (outline) {
      g.strokeStyle = outline
      g.lineWidth = lw
    }
    const dot = (x: number, y: number, rad: number) => {
      if (square) {
        g.fillRect(x - rad, y - rad, 2 * rad, 2 * rad)
        if (outline) g.strokeRect(x - rad, y - rad, 2 * rad, 2 * rad)
        return
      }
      g.beginPath()
      g.arc(x, y, rad, 0, 2 * Math.PI)
      g.fill()
      if (outline) g.stroke()
    }
    let alpha = -1
    let fill = ''
    for (let k = 0; k < n; k++) {
      const i = order ? order[k] : k
      const x = px[2 * i]
      const y = px[2 * i + 1]
      if (Number.isNaN(x)) continue
      const member = groupSet?.has(emb.cell_ids[i])
      // group in scope: members at full opacity, the rest faint; else the focused cell stands out
      const a = groupSet ? (member ? base : base * 0.15) : focus && emb.cell_ids[i] !== focus ? base * 0.58 : base
      if (a !== alpha) g.globalAlpha = alpha = a
      if (colors[i] !== fill) g.fillStyle = fill = colors[i]
      dot(x, y, member ? r * 1.15 : r)
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
      if (fi >= 0 && !Number.isNaN(px[2 * fi])) {
        g.fillStyle = colors[fi]
        if (outline) g.strokeStyle = outline
        dot(px[2 * fi], px[2 * fi + 1], Math.max(r * 2, 3))
        ring(fi, Math.max(r * 2, 3) * (square ? 1.42 : 1) + 2, pal.strong, 2)
      }
    }
    // this pane's pinned cell: accent ring + label, in addition to the focus
    const rr = Math.max(r * 2, 3)
    const pin = pinnedCell(pane)
    const pi = pin ? emb.cell_ids.indexOf(pin) : -1
    if (pi >= 0) {
      ring(pi, rr + 5, pal.accent, 2.5)
      g.fillStyle = pal.accent
      g.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
      g.textAlign = 'left'
      g.textBaseline = 'middle'
      if (!Number.isNaN(px[2 * pi])) g.fillText(`📌 ${pin}`, px[2 * pi] + rr + 9, px[2 * pi + 1])
    }
    if (hover) ring(hover.i, r + 4, pal.strong, 1.5)
    if (groupSet && groupInfo) {
      g.globalAlpha = 1
      g.fillStyle = groupInfo.color
      g.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
      g.textAlign = 'right'
      g.textBaseline = 'top'
      g.fillText(`${groupInfo.name} · ${groupSet.size} cells`, size.w - 8, 8)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [px, dots, order, emb, size.w, plotH, view.focusCell, hover, pane.scope, groupSet, groupInfo, pal, st.size, st.opacity, st.shape, outline, img, plot, zoom, source?.image?.opacity, spacing, epoch])

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
    g.strokeStyle = pal.strong
    g.fillStyle = pal.lassoFill
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
    if (e.button !== 0 || !px) return
    if (!(lassoTool || e.shiftKey)) {
      // plain drag: pan (a click without movement still focuses a dot)
      const [x, y] = local(e)
      pan.current = { x, y, v: zoom, moved: false }
      try {
        e.currentTarget.setPointerCapture(e.pointerId)
      } catch {
        /* capture is only a convenience */
      }
      return
    }
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
    const p0 = pan.current
    if (p0) {
      const [x, y] = local(e)
      if (!p0.moved && Math.hypot(x - p0.x, y - p0.y) < 3) return
      if (!p0.moved) {
        p0.moved = true
        setPanning(true)
        setHover(null)
      }
      setZoom(panBy(p0.v, x - p0.x, y - p0.y))
      return
    }
    if (!path.current) return
    path.current.push(local(e))
    drawLasso()
  }
  const onPointerUp = () => {
    if (pan.current) {
      if (pan.current.moved) suppressClick.current = true // a drag is not a click on a dot
      pan.current = null
      setPanning(false)
      return
    }
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
    if (!px || path.current || pan.current?.moved) return
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
    else {
      // a click on empty space: back to all cells, as the "All cells" button / Esc (an unsaved lasso
      // selection is dropped too; saved groups stay)
      if (selection) setSelection(null)
      focusCell(null)
    }
  }

  // the cells drawn here: the legend counts only these (not the whole dataset)
  const shown = useMemo(() => {
    if (!emb) return null
    const out = new Set<string>()
    emb.cell_ids.forEach((id, i) => {
      const x = emb.x[i]
      const y = emb.y[i]
      if (x !== null && y !== null && Number.isFinite(x) && Number.isFinite(y)) out.add(id)
    })
    return out
  }, [emb])
  const hoverId = hover && emb ? emb.cell_ids[hover.i] : null
  const tipField = mode === 'field' ? paneField?.name : mode === 'overview' && view.overviewColor === 'field' ? view.cellField : null
  const tipValues = mode === 'field' ? paneValues : mode === 'overview' ? fieldValues : null
  const hoverVal = hoverId && tipField && tipValues ? tipValues.get(hoverId) : undefined
  const axis = emb?.axis_labels ?? ['', '']

  return (
    <div ref={boxRef} className="embedding-view">
      {!source && !list.length && <div className="muted pane-empty">This dataset has no cell embeddings (see uchrom.emb.embed_cells).</div>}
      {source && !source.data && !source.error && source.empty && <div className="muted pane-empty">{source.empty}</div>}
      {error && <div className="error">{error}</div>}
      <canvas
        ref={canvasRef}
        style={{ width: size.w, height: plotH, cursor: lassoTool ? 'crosshair' : panning ? 'grabbing' : hover ? 'pointer' : 'grab', touchAction: 'none' }}
        onDoubleClick={() => setZoom(IDENTITY_VIEW)}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        onClick={onClick}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      />
      <canvas ref={lassoRef} className="emb-lasso-canvas" data-capture="skip" />
      {hasPoints && (
        <div className="emb-tools" data-capture="skip">
          <button
            className={`emb-tool-icon${lassoTool ? ' active' : ''}`}
            onClick={() => setLassoTool(!lassoTool)}
            title="Lasso: drag around cells to select them (or shift-drag any time)"
            aria-label="Lasso"
            aria-pressed={lassoTool}
          >
            <LassoIcon />
          </button>
          {!isIdentity(zoom) && (
            <button onClick={() => setZoom(IDENTITY_VIEW)} title="Show all cells again (or double-click the plot)">
              ⤢ {zoom.k.toFixed(zoom.k < 10 ? 1 : 0)}×
            </button>
          )}
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
            title="Save as group"
          >
            Save
          </button>
          <button onClick={() => setSelection(null)} title="Discard the selection">
            ×
          </button>
        </div>
      )}
      {mode === 'field' && paneField && st.legend && <PaneLegend pane={pane} coloring={coloring} shown={shown} />}
      <AxisKey x={axis[0]} y={axis[1]} yDown={yDown} />
      {hover && hoverId && (
        <div className="embedding-tip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
          cell {hoverId}
          {tipField && tipValues && ` · ${fieldLabel(tipField)}: ${fmtValue(hoverVal)}`}
        </div>
      )}
    </div>
  )
}

/** Legend (categorical) or colour bar (numeric) of a pane's own colouring, drawn over the plot. */
function PaneLegend({ pane, coloring, shown }: { pane: Pane; coloring: ReturnType<typeof usePaneColoring>; shown: ReadonlySet<string> | null }) {
  const setWorkspace = useStore((s) => s.setWorkspace)
  const { st, field, values, sorted, range } = coloring
  const legend = useMemo(() => (field && field.kind === 'category' ? categoryLegend(field, values, st.hidden, shown) : null), [field, values, st.hidden, shown])
  if (!field) return null
  const title = field.group === 'cell' ? fieldLabel(field.name) : `${groupTitle(field.group)} · ${field.label}`
  const setHidden = (hidden: string[]) =>
    setWorkspace((ws) => updatePane(ws, pane.id, { embStyle: patchEmbStyle(ws.panes.find((p) => p.id === pane.id)?.embStyle, { hidden }) }))
  if (legend) {
    const names = legend.rows.map((r) => r.value)
    const toggle = (v: string) => setHidden(st.hidden.includes(v) ? st.hidden.filter((h) => h !== v) : [...st.hidden, v])
    return (
      <div className="emb-legend">
        <div className="emb-legend-title">{title}</div>
        <div className="emb-legend-list">
          {legend.rows.map((r) => (
            <div
              key={r.value}
              className={`emb-legend-row${r.off ? ' off' : ''}`}
              onClick={() => toggle(r.value)}
              onDoubleClick={() => setHidden(names.filter((n) => n !== r.value))}
              title={`${r.value}: ${r.count.toLocaleString('en-US')} cells · click to grey out / restore in this view · double-click to show only this one`}
            >
              <span className="swatch" style={{ background: r.color }} />
              <span className="name">{r.value}</span>
              <span className="muted count">{r.count.toLocaleString('en-US')}</span>
            </div>
          ))}
        </div>
        {legend.missing > 0 && (
          <div className="muted small" title="Cells drawn here without a value of this field">
            {legend.rows.length ? 'grey' : 'all grey'} = no value ({legend.missing.toLocaleString('en-US')})
          </div>
        )}
      </div>
    )
  }
  if (!range || !sorted) return <div className="emb-legend emb-colorbar muted small">{title} …</div>
  const min = sorted.length ? sorted[0] : range[0]
  const max = sorted.length ? sorted[sorted.length - 1] : range[1]
  let missing = 0
  if (values)
    for (const [id, v] of values.entries() as Iterable<[string, CellValue]>)
      if ((!shown || shown.has(id)) && (typeof v !== 'number' || !Number.isFinite(v))) missing++
  return (
    <div className="emb-legend emb-colorbar">
      <div className="emb-legend-title">{title}</div>
      <div className="colorbar-ramp" style={{ background: cmapGradient(st.cmap, st.reverse) }} />
      <div className="colorbar-ticks">
        <span>{`${range[0] > min ? '≤' : ''}${fmtNum(range[0])}`}</span>
        {st.log && <span className="muted">log1p</span>}
        <span>{`${range[1] < max ? '≥' : ''}${fmtNum(range[1])}`}</span>
      </div>
      {missing > 0 && <div className="muted small">grey = missing ({missing.toLocaleString('en-US')})</div>}
    </div>
  )
}

/** A lasso: a rope loop with a knot and a trailing end. */
function LassoIcon() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
      <path d="M5.3 9.9C3 9.3 1.7 7.9 2.1 6.3 2.7 3.9 6.1 2.4 9.7 2.8c3.4.4 5.3 2.3 4.5 4.3-.8 2-4.1 3.2-7.4 2.9" />
      <circle cx="6" cy="10.2" r="1.1" />
      <path d="M5.6 11.3c-.6 1-.4 1.9.4 2.4.7.5.6 1.3-.3 1.7" />
    </svg>
  )
}

/**
 * Axis key in the bottom-left corner (as in single-cell embedding plots): two short arrows
 * from one origin, named at their tips; y points down for image coordinates.
 */
function AxisKey({ x, y, yDown }: { x: string; y: string; yDown: boolean }) {
  if (!x && !y) return null
  const L = 26
  return (
    <div className={`axis-key${yDown ? ' down' : ''}`} aria-hidden>
      {!yDown && <span className="axis-key-y">{y}</span>}
      <div className="axis-key-row">
        <svg width={L + 6} height={L + 6} viewBox={`0 0 ${L + 6} ${L + 6}`} fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
          {yDown ? (
            <>
              <path d={`M2 2H${L + 2}M${L - 2} -1l4 3-4 3`} />
              <path d={`M2 2V${L + 2}M-1 ${L - 2}l3 4 3-4`} />
            </>
          ) : (
            <>
              <path d={`M2 ${L + 3}H${L + 3}M${L - 1} ${L}l4 3-4 3`} />
              <path d={`M2 ${L + 3}V2M-1 6l3-4 3 4`} />
            </>
          )}
        </svg>
        <span className="axis-key-x">{x}</span>
      </div>
      {yDown && <span className="axis-key-y">{y}</span>}
    </div>
  )
}

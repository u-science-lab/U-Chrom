import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { parseFieldRef } from '../groups'
import { activeSavedGroups, useStore } from '../store'
import {
  addPane,
  dropUnknownGroups,
  dropUnknownPins,
  pinnedCell,
  pinnedGroup,
  handleWorkspaceKey,
  LAYOUTS,
  gridShape,
  gridSizes,
  gridSpan,
  moveGridSplitter,
  PANE_LABEL,
  removePane,
  retypePane,
  setLayout,
  supportedPaneTypes,
  type DataKind,
  type Pane,
  type PaneType,
  type WsLayout,
} from '../workspace'
import { EmbeddingView } from './EmbeddingView'
import { GenomeView } from './GenomeView'
import { LocusBar } from './LocusBar'
import { MatrixView } from './MatrixView'
import { Popover } from './Popover'
import { cellTitle, useCellTypes } from './PaneCell'
import { useGroupInfo } from '../useGroups'
import { savePane, type CaptureFormat } from '../capture'
import { StatsView } from './StatsView'
import { RegionPicker, SpatialView } from './SpatialView'
import { Viewport } from './Viewport'

const TYPE_LABEL = PANE_LABEL
/** What each view shows (menu descriptions). */
const MENU_HINT: Record<PaneType, string> = {
  '3d': '3-D chromatin structures',
  spatial: 'cells in the tissue, over its image',
  embedding: 'UMAP / t-SNE / PCA of the cells',
  genome: 'contact maps, distances and tracks along a locus',
  matrix: 'contact or distance matrix of a locus',
  stats: 'distributions and per-cell statistics',
}
const MENU_ICON: Record<PaneType, string> = { '3d': '◈', spatial: '▦', embedding: '⁘', genome: '≋', matrix: '▤', stats: '▥' }

/** What the active dataset offers, for the default views and the view menus. */
function useDataKind(): DataKind {
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  return {
    hasEmbeddings: (ds?.embeddings?.length ?? 0) > 0,
    hasCoords: !!ds && ds.has_coords !== false && ds.n_spots > 0,
    hasTracks: (ds?.tracks?.length ?? 0) > 0,
    hasContactMaps: (ds?.contact_maps?.length ?? 0) > 0,
    hasSpatial: (ds?.spatial?.length ?? 0) > 0,
    manyCells: (ds?.n_cells ?? 0) > 1,
  }
}

/**
 * Menu of view types (the + View menu and each pane's type switch): only
 * the views this dataset can fill, each with what it shows; the current
 * type is checked (and kept listed, marked, if the data lacks it).
 */
function ViewMenu({ current, onPick }: { current?: PaneType; onPick(t: PaneType): void }) {
  const supported = supportedPaneTypes(useDataKind())
  const types = current && !supported.includes(current) ? [...supported, current] : supported
  return (
    <ul className="view-menu" role="menu">
      {types.map((t) => (
        <li
          key={t}
          role="menuitemradio"
          aria-checked={t === current}
          className={`${t === current ? 'current' : ''}${supported.includes(t) ? '' : ' unsupported'}`}
          onClick={() => onPick(t)}
        >
          <span className="vm-icon" aria-hidden>
            {MENU_ICON[t]}
          </span>
          <span className="vm-text">
            <span className="vm-name">{PANE_LABEL[t]}</span>
            <span className="vm-hint">{supported.includes(t) ? MENU_HINT[t] : 'not available for this dataset'}</span>
          </span>
          <span className="vm-check" aria-hidden>
            {t === current ? '✓' : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}

/** A pane's type switch: the view name with a caret, opening the view menu. */
const SAVE_FORMATS: [CaptureFormat, string, string][] = [
  ['png', 'PNG image', 'pixels, as on screen'],
  ['svg', 'SVG (editable vectors)', 'lines, points and text you can edit in Illustrator / Inkscape'],
  ['pdf', 'PDF (editable vectors)', 'the SVG as a PDF, text kept as text'],
]

/** The camera button of a pane: save the view as PNG, SVG or PDF. */
function SaveImageMenu({ saving, onSave }: { saving: boolean; onSave(format: CaptureFormat): void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLButtonElement>(null)
  const close = useCallback(() => setOpen(false), [])
  return (
    <>
      <button ref={ref} className="pane-shot" onClick={() => setOpen(!open)} disabled={saving} title="Save image (PNG, SVG, PDF)" aria-label="Save image" aria-haspopup="menu">
        <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden>
          <path d="M2 5h2.6l1.2-1.8h4.4L11.4 5H14v8H2z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
          <circle cx="8" cy="9" r="2.3" fill="none" stroke="currentColor" strokeWidth="1.3" />
        </svg>
      </button>
      <Popover anchor={ref} open={open} onClose={close} className="menu-popup">
        <ul role="menu">
          {SAVE_FORMATS.map(([format, label, hint]) => (
            <li
              key={format}
              role="menuitem"
              title={hint}
              onClick={() => {
                setOpen(false)
                onSave(format)
              }}
            >
              {label}
            </li>
          ))}
        </ul>
      </Popover>
    </>
  )
}

function PaneTypeSwitch({ pane }: { pane: Pane }) {
  const setWorkspace = useStore((s) => s.setWorkspace)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLButtonElement>(null)
  const close = useCallback(() => setOpen(false), [])
  return (
    <>
      <button ref={ref} className={`pane-type${open ? ' open' : ''}`} onClick={() => setOpen(!open)} title="View type" aria-haspopup="menu">
        <span className="vm-icon" aria-hidden>
          {MENU_ICON[pane.type]}
        </span>
        <span className="pane-type-label">{TYPE_LABEL[pane.type]}</span>
        <span className="caret" aria-hidden>
          ▾
        </span>
      </button>
      <Popover anchor={ref} open={open} onClose={close} className="menu-popup">
        <ViewMenu
          current={pane.type}
          onPick={(t) => {
            setWorkspace((w) => retypePane(w, pane.id, t))
            setOpen(false)
          }}
        />
      </Popover>
    </>
  )
}
/** Whether a pane shows the shared genomic locus (Stats only when it looks at the locus chromosome). */
const usesLocus = (p: Pane) => p.type === 'genome' || p.type === 'matrix' || (p.type === 'stats' && p.chromScope === 'locus')
const LAYOUT_LABEL: Record<WsLayout, [string, string]> = {
  tabs: ['Tabs', 'one view at a time, switch with tabs'],
  grid: ['Grid', 'all views at once, in a grid'],
}

/** Small drawing of a layout (menu and button). */
function LayoutIcon({ layout }: { layout: WsLayout }) {
  const r = (x: number, y: number, w: number, h: number) => <rect x={x} y={y} width={w} height={h} rx="1" />
  return (
    <svg className="layout-icon" viewBox="0 0 16 12" width="16" height="12" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.2">
      {layout === 'tabs' && (
        <>
          {r(1, 3, 14, 8)}
          <path d="M1.5 3V1.5h5V3" />
        </>
      )}
      {layout === 'grid' && (
        <>
          {r(1, 1, 6.2, 4.2)}
          {r(8.8, 1, 6.2, 4.2)}
          {r(1, 6.8, 6.2, 4.2)}
          {r(8.8, 6.8, 6.2, 4.2)}
        </>
      )}
    </svg>
  )
}

/** The layout switch: the current layout as a button (like + View), the layouts in a menu. */
function LayoutMenu({ layout, onPick }: { layout: WsLayout; onPick(l: WsLayout): void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLButtonElement>(null)
  const close = useCallback(() => setOpen(false), [])
  return (
    <div className="ws-add">
      <button ref={ref} className={`ws-layout-btn${open ? ' open' : ''}`} onClick={() => setOpen(!open)} title="Layout of the views" aria-haspopup="menu">
        <LayoutIcon layout={layout} />
        {LAYOUT_LABEL[layout][0]}
        <span className="caret" aria-hidden>
          ▾
        </span>
      </button>
      <Popover anchor={ref} open={open} onClose={close} className="menu-popup">
        <ul className="view-menu" role="menu">
          {LAYOUTS.map((l) => (
            <li
              key={l}
              role="menuitemradio"
              aria-checked={l === layout}
              className={l === layout ? 'current' : ''}
              onClick={() => {
                onPick(l)
                setOpen(false)
              }}
            >
              <span className="vm-icon" aria-hidden>
                <LayoutIcon layout={l} />
              </span>
              <span className="vm-text">
                <span className="vm-name">{LAYOUT_LABEL[l][0]}</span>
                <span className="vm-hint">{LAYOUT_LABEL[l][1]}</span>
              </span>
              <span className="vm-check" aria-hidden>
                {l === layout ? '✓' : ''}
              </span>
            </li>
          ))}
        </ul>
      </Popover>
    </div>
  )
}

/**
 * Centre area: views (3-D, embedding, …) as equal panes in a tabs or grid
 * layout, plus a bar with the controls that belong to no single
 * view (cell focus, colour scale, layout, + View).
 *
 * Panes are keyed children of one container, so changing the layout moves
 * them without remounting (a 3-D pane keeps its renderer and camera).
 */
export function Workspace() {
  const ws = useStore((s) => s.workspace)
  const setWorkspace = useStore((s) => s.setWorkspace)
  const ensureDefault = useStore((s) => s.ensureDefaultWorkspace)
  const datasetId = useStore((s) => s.activeDatasetId)
  const ds = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId))
  const { hasEmbeddings, hasCoords, hasTracks, hasContactMaps, hasSpatial, manyCells } = useDataKind()
  const [resetKeys, setResetKeys] = useState<Record<string, number>>({})
  const [menu, setMenu] = useState(false)
  const addRef = useRef<HTMLButtonElement>(null)
  const closeMenu = useCallback(() => setMenu(false), [])
  const panesRef = useRef<HTMLDivElement>(null)

  // Each dataset has its own layout: switching restores the one arranged for it, else the
  // default for its data (which follows the data until the user arranges views).
  const owner = ds?.name ?? null
  useEffect(() => {
    if (datasetId && owner) ensureDefault({ hasEmbeddings, hasCoords, hasTracks, hasContactMaps, hasSpatial, manyCells }, owner)
  }, [datasetId, owner, hasEmbeddings, hasCoords, hasTracks, hasContactMaps, hasSpatial, manyCells, ensureDefault])

  // Pins to cells the active dataset doesn't have (e.g. after switching) are dropped.
  const cellList = useStore((s) => (s.activeDatasetId ? s.cells[s.activeDatasetId] : undefined))
  useEffect(() => {
    // [] = requested, still loading: every pin would look unknown
    if (!cellList?.length) return
    setWorkspace((w) => dropUnknownPins(w, new Set(cellList.map((c) => c.cell_id))))
  }, [cellList, setWorkspace])

  // A closed 3-D view takes its subsets with it (only once this layout is the active
  // dataset's — while switching, pane ids of another dataset's layout would not match).
  const wsOwner = useStore((s) => s.workspaceOwner)
  const layers = useStore((s) => s.layers)
  useEffect(() => {
    if (!ds || wsOwner !== ds.name) return
    const ids = new Set(ws.panes.map((p) => p.id))
    for (const l of layers) if (l.datasetId === ds.id && l.paneId && !ids.has(l.paneId)) useStore.getState().removeLayer(l.id)
  }, [ws.panes, layers, ds, wsOwner])

  // Group scopes the active dataset doesn't know (another dataset's lasso group) are dropped.
  const fields = ds?.cell_fields
  const savedIds = useStore((s) => activeSavedGroups(s))
  useEffect(() => {
    if (!ds) return
    const saved = new Set(savedIds.map((g) => g.id))
    const known = (ref: string) => {
      const f = parseFieldRef(ref)
      return f ? !!fields?.some((x) => x.name === f.field) : saved.has(ref)
    }
    setWorkspace((w) => dropUnknownGroups(w, known))
  }, [ds, fields, savedIds, setWorkspace])

  // Keyboard shortcuts once for the whole workspace (not per 3-D pane).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const st = useStore.getState()
      const handled = handleWorkspaceKey(e, {
        hasPick: !!st.pick,
        clearPick: () => st.setPick(null),
        clearFocus: () => st.focusCell(null),
        step: (d) => st.stepCell(d),
      })
      if (handled && e.key !== 'Escape') e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const visible = (p: Pane) =>
    ws.maximized ? p.id === ws.maximized : ws.layout === 'tabs' ? p.id === ws.activePane : true

  // grid: the boundaries between its columns / rows can be dragged
  const grid = ws.layout === 'grid' && !ws.maximized && ws.panes.length > 1
  const shape = gridShape(ws.panes.length)
  const g = gridSizes(ws)
  const onGridStart = (axis: 'cols' | 'rows', index: number) => (e: React.PointerEvent) => {
    e.preventDefault()
    const box = panesRef.current?.getBoundingClientRect()
    if (!box) return
    const n = axis === 'cols' ? shape.cols : shape.rows
    const move = (ev: PointerEvent) => {
      const [pos, len] = axis === 'cols' ? [ev.clientX - box.left, box.width] : [ev.clientY - box.top, box.height]
      const frac = (pos - GRID_PAD - index * GRID_GAP - GRID_GAP / 2) / (len - 2 * GRID_PAD - (n - 1) * GRID_GAP)
      setWorkspace((w) => moveGridSplitter(w, axis, index, frac))
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      document.body.classList.remove('resizing', 'resizing-rows')
    }
    document.body.classList.add(axis === 'cols' ? 'resizing' : 'resizing-rows')
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const add = (type: PaneType) => {
    setWorkspace((w) => addPane(w, type))
    setMenu(false)
  }

  return (
    <div className="workspace">
      <div className="ws-bar">
        <span className="spacer" />
        <div className="ws-add">
          <button ref={addRef} onClick={() => setMenu(!menu)} title="Add a view">
            + View
          </button>
          <Popover anchor={addRef} open={menu} onClose={closeMenu} className="menu-popup">
            <ViewMenu onPick={add} />
          </Popover>
        </div>
        <LayoutMenu layout={ws.layout} onPick={(l) => setWorkspace((w) => setLayout(w, l))} />
      </div>
      {ws.layout === 'tabs' && !ws.maximized && (
        <div className="ws-tabs">
          {ws.panes.map((p, i) => (
            <button key={p.id} className={p.id === ws.activePane ? 'active' : ''} onClick={() => setWorkspace((w) => ({ ...w, activePane: p.id }))}>
              {TYPE_LABEL[p.type]} {ws.panes.filter((q) => q.type === p.type).length > 1 ? i + 1 : ''}
            </button>
          ))}
        </div>
      )}
      <div
        ref={panesRef}
        className={`ws-panes layout-${ws.layout}${ws.maximized ? ' maximized' : ''}`}
        style={
          grid
            ? { gridTemplateColumns: g.cols.map((f) => `${f}fr`).join(' '), gridTemplateRows: g.rows.map((f) => `${f}fr`).join(' ') }
            : undefined
        }
      >
        {ws.panes.map((p, i) => (
          <Fragment key={p.id}>
            <PaneBox
              pane={p}
              active={p.id === ws.activePane && ws.panes.length > 1}
              hidden={!visible(p)}
              style={grid && gridSpan(i, ws.panes.length) > 1 ? { gridColumn: `span ${gridSpan(i, ws.panes.length)}` } : undefined}
              canClose={ws.panes.length > 1}
              maximized={ws.maximized === p.id}
              resetKey={resetKeys[p.id] ?? 0}
              onReset={() => setResetKeys((k) => ({ ...k, [p.id]: (k[p.id] ?? 0) + 1 }))}
            />
          </Fragment>
        ))}
        {grid && <GridSplitters cols={g.cols} rows={g.rows} n={ws.panes.length} onStart={onGridStart} />}
      </div>
    </div>
  )
}

/** Padding and gap of the grid layout (px; as in index.css `.layout-grid`). */
const GRID_PAD = 4
const GRID_GAP = 4

/** Offset of the boundary after track `k` of `fracs` inside a grid box (CSS length). */
const gridEdge = (fracs: number[], k: number) => {
  const cum = fracs.slice(0, k + 1).reduce((a, b) => a + b, 0)
  return `calc(${GRID_PAD}px + (100% - ${2 * GRID_PAD + (fracs.length - 1) * GRID_GAP}px) * ${cum} + ${k * GRID_GAP + GRID_GAP / 2}px)`
}

/**
 * Drag handles on the boundaries of the grid: one per inner column edge (over the
 * rows where that edge exists — not across a pane spanning the last row) and one
 * per inner row edge.
 */
function GridSplitters({ cols, rows, n, onStart }: { cols: number[]; rows: number[]; n: number; onStart(axis: 'cols' | 'rows', k: number): (e: React.PointerEvent) => void }) {
  const inLast = n - cols.length * (rows.length - 1) // panes in the last row
  return (
    <>
      {cols.slice(0, -1).map((_, k) => {
        const full = k < inLast - 1 || inLast === cols.length
        return (
          <div
            key={`c${k}`}
            className="ws-grid-splitter cols"
            style={{ left: gridEdge(cols, k), top: GRID_PAD, ...(full ? { bottom: GRID_PAD } : { height: `calc(${gridEdge(rows, rows.length - 2)} - ${GRID_PAD + GRID_GAP / 2}px)` }) }}
            onPointerDown={onStart('cols', k)}
            title="Drag to resize"
          />
        )
      })}
      {rows.slice(0, -1).map((_, k) => (
        <div key={`r${k}`} className="ws-grid-splitter rows" style={{ top: gridEdge(rows, k), left: GRID_PAD, right: GRID_PAD }} onPointerDown={onStart('rows', k)} title="Drag to resize" />
      ))}
    </>
  )
}

function PaneBox({
  pane,
  active,
  hidden,
  style,
  canClose,
  maximized,
  resetKey,
  onReset,
}: {
  pane: Pane
  active: boolean
  hidden: boolean
  style?: React.CSSProperties
  canClose: boolean
  maximized: boolean
  resetKey: number
  onReset(): void
}) {
  const setWorkspace = useStore((s) => s.setWorkspace)
  const activate = () => setWorkspace((w) => (w.activePane === pane.id ? w : { ...w, activePane: pane.id }))
  const types = useCellTypes()
  const groupInfo = useGroupInfo(pinnedGroup(pane))
  const cellPin = pinnedCell(pane)
  const bodyRef = useRef<HTMLDivElement>(null)
  const [saving, setSaving] = useState(false)
  const saveImage = (format: CaptureFormat) => {
    if (!bodyRef.current || saving) return
    setSaving(true)
    savePane(bodyRef.current, pane, format)
      .then(({ filename, notes }) => {
        if (!notes.length) return
        // what the vector file approximates: shown for a while in the status bar
        const msg = `Saved ${filename}: ${notes.join(' ')}`
        const st = useStore.getState()
        st.setStatus(msg)
        setTimeout(() => useStore.getState().status === msg && useStore.getState().setStatus(null), 10_000)
      })
      .catch((e: Error) => useStore.getState().setError(`Cannot save the image: ${e.message}`))
      .finally(() => setSaving(false))
  }
  return (
    <section
      className={`pane${active ? ' active' : ''}${hidden ? ' hidden' : ''}${pane.scope && pane.scope.kind !== 'focus' ? ' pinned' : ''}`}
      style={style}
      onPointerDownCapture={activate}
      onFocusCapture={activate}
    >
      <header className="pane-head">
        <PaneTypeSwitch pane={pane} />
        {pane.type === 'spatial' && <RegionPicker pane={pane} />}
        {usesLocus(pane) && <LocusBar />}
        {cellPin && (
          <button className="pin-badge" onClick={() => activate()} title="Pinned to this cell — change it in the inspector (right, “cells”)">
            📌 {cellTitle(cellPin, types)}
          </button>
        )}
        {pane.type === '3d' && pane.trace && (
          <span className="pin-badge" title={`This view shows only trace ${pane.trace}`}>
            {/* the pin badge names the cell: drop it from the trace id */}
            trace {cellPin && pane.trace.startsWith(`${cellPin}_`) ? pane.trace.slice(cellPin.length + 1) : pane.trace}
          </span>
        )}
        {pane.scope?.kind === 'all' && (
          <button className="pin-badge" onClick={() => activate()} title="Always all cells — change it in the inspector (right, “cells”)">
            All cells
          </button>
        )}
        {pane.scope?.kind === 'group' && (
          <button className="pin-badge group" onClick={() => activate()} title="This view aggregates over a group of cells — change it in the inspector (right)">
            <span className="swatch round" style={{ background: groupInfo?.color ?? '#888' }} />
            {groupInfo?.name ?? pane.scope.group}
            {groupInfo?.cells && <span className="muted"> · {groupInfo.cells.length}</span>}
          </button>
        )}
        <span className="spacer" />
        <SaveImageMenu saving={saving} onSave={saveImage} />
        {pane.type === '3d' && (
          <button onClick={onReset} title="Reset view: fit everything drawn in this view">
            ⟲
          </button>
        )}
        <button
          onClick={() => setWorkspace((w) => ({ ...w, maximized: w.maximized === pane.id ? null : pane.id, activePane: pane.id }))}
          title={maximized ? 'Restore layout' : 'Maximise this view'}
        >
          {maximized ? '⤡' : '⤢'}
        </button>
        <button onClick={() => setWorkspace((w) => removePane(w, pane.id))} disabled={!canClose} title={canClose ? 'Close this view' : 'The last view cannot be closed'}>
          ×
        </button>
      </header>
      <div className="pane-body" ref={bodyRef} data-pane={pane.id}>
        {pane.type === '3d' && <Viewport paneId={pane.id} resetKey={resetKey} scope={pane.scope} />}
        {pane.type === 'spatial' && <SpatialView pane={pane} />}
        {pane.type === 'embedding' && <EmbeddingView pane={pane} />}
        {pane.type === 'genome' && <GenomeView pane={pane} />}
        {pane.type === 'matrix' && <MatrixView pane={pane} />}
        {pane.type === 'stats' && <StatsView pane={pane} />}
      </div>
    </section>
  )
}
